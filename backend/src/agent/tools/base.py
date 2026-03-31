from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Awaitable, Callable, Dict, List

from ..types import ToolResult
import asyncio


ToolHandler = Callable[..., Any]


@dataclass
class ToolDefinition:
    """工具定义对象，兼容 OpenAI tools schema 并封装执行逻辑。"""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: ToolHandler
    category: str
    requires_confirmation: bool = False
    max_execution_time: int = 15  # 单位秒

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具处理函数。

        Args:
            **kwargs: 工具参数。

        Returns:
            工具执行结果字符串。
        """
        try:
            timeout = getattr(self, "max_execution_time", 15)
            result = self.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=timeout)
            else:
                # 同步函数也统一用线程池防止阻塞，并加超时
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, self.handler, **kwargs),
                    timeout=timeout
                )

            if isinstance(result, ToolResult):
                return result
            if isinstance(result, str):
                return ToolResult(output=result)
            return ToolResult(output=str(result))

        except asyncio.TimeoutError:
            return ToolResult(
                output=f"Tool execution timeout after {timeout}s",
                error="tool_timeout",
            )
        except Exception as e:
            return ToolResult(
                output=f"Tool execution error: {e}",
                error="tool_exception",
            )

# ------  参数类型转换  -------
# cast_params → _cast_object → _cast_value
# LLM 返回的 tool_call.arguments 经过 JSON parse 后，类型可能与 schema 不一致（如把 integer 返回成 "42" 字符串）。这组函数根据 schema 定义做宽容的类型修正。
# cast_params(params)          # 入口：检查顶层 schema 是 object 类型
#   └─ _cast_object(obj, schema)   # 遍历 dict 的每个 key，按 properties 分发
#        └─ _cast_value(val, schema)  # 对单个值按 type 做转换
#             ├─ "integer" + str → int()
#             ├─ "number"  + str → float()
#             ├─ "string"  + 非None → str()
#             ├─ "boolean" + str → True/False
#             ├─ "array"   → 递归每个 item
#             └─ "object"  → 递归 _cast_object

    def cast_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """按 schema 对参数进行安全类型转换。

        Args:
            params: 原始参数。

        Returns:
            转换后的参数。
        """
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            return params
        casted = self._cast_object(params, schema)
        return self._apply_defaults(casted, schema)

    def _cast_object(self, obj: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
        """对对象类型的参数进行转换。

        Args:
            obj: 参数对象。
            schema: 对象 schema。

        Returns:
            转换后的对象参数。
        """
        if not isinstance(obj, dict):
            return obj
        props = schema.get("properties", {})
        result: Dict[str, Any] = {}
        for key, value in obj.items():
            if key in props:
                result[key] = self._cast_value(value, props[key])
            else:
                result[key] = value
        return result

    def _cast_value(self, val: Any, schema: Dict[str, Any]) -> Any:
        """对单个值进行转换。

        Args:
            val: 原始值。
            schema: schema 定义。

        Returns:
            转换后的值。
        """
        target_type = schema.get("type")

        if target_type == "boolean" and isinstance(val, bool):
            return val
        if target_type == "integer" and isinstance(val, int) and not isinstance(val, bool):
            return val
        if target_type in self._TYPE_MAP and target_type not in ("boolean", "integer", "array", "object"):
            expected = self._TYPE_MAP[target_type]
            if isinstance(val, expected):
                return val

        if target_type == "integer" and isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return val

        if target_type == "number" and isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return val

        if target_type == "string":
            return val if val is None else str(val)

        if target_type == "boolean" and isinstance(val, str):
            val_lower = val.lower()
            if val_lower in ("true", "1", "yes"):
                return True
            if val_lower in ("false", "0", "no"):
                return False
            return val

        if target_type == "array" and isinstance(val, list):
            item_schema = schema.get("items")
            return [self._cast_value(item, item_schema) for item in val] if item_schema else val

        if target_type == "object" and isinstance(val, dict):
            return self._cast_object(val, schema)

        return val

    def _apply_defaults(self, obj: Any, schema: Dict[str, Any]) -> Any:
        if not isinstance(obj, dict):
            return obj
        props = schema.get("properties", {})
        result = dict(obj)
        for key, prop_schema in props.items():
            if key not in result and "default" in prop_schema:
                result[key] = prop_schema["default"]
                continue
            if key in result:
                value = result[key]
                if prop_schema.get("type") == "object" and isinstance(value, dict):
                    result[key] = self._apply_defaults(value, prop_schema)
                elif prop_schema.get("type") == "array" and isinstance(value, list):
                    item_schema = prop_schema.get("items")
                    if isinstance(item_schema, dict) and item_schema.get("type") == "object":
                        result[key] = [
                            self._apply_defaults(item, item_schema) if isinstance(item, dict) else item
                            for item in value
                        ]
        return result


# ---------- validate_params → _validate
# validate_params(params)          # 入口：检查顶层 schema 是 object 类型
#   └─ _validate(val, schema, "")  # 递归校验每个字段


    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """校验参数是否符合 JSON Schema。

        Args:
            params: 待校验参数。

        Returns:
            错误信息列表，空列表表示校验通过。
        """
        if not isinstance(params, dict):
            return [f"parameters must be an object, got {type(params).__name__}"]
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: Dict[str, Any], path: str) -> List[str]:
        """递归校验参数。

        Args:
            val: 待校验值。
            schema: schema 定义。
            path: 当前字段路径。

        Returns:
            错误信息列表。
        """
        t, label = schema.get("type"), path or "parameter"
        if val is None:
            if schema.get("nullable") is True:
                return []
            if "default" in schema and schema.get("default") is None:
                return []
            return [f"{label} should be {t}"]
        if t == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
            return [f"{label} should be integer"]
        if t == "number" and (not isinstance(val, self._TYPE_MAP[t]) or isinstance(val, bool)):
            return [f"{label} should be number"]
        if t in self._TYPE_MAP and t not in ("integer", "number") and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors: List[str] = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + "." + k if path else k))
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]")
                )
        return errors

    def to_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI tools schema。

        Returns:
            OpenAI 工具 schema 字典。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
