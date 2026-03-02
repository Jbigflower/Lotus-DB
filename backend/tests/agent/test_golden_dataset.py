"""
测试Golden Dataset
pytest tests/agent/test_golden_dataset.py
# 指定更详细输出
pytest tests/agent/test_golden_dataset.py -vv
# 开启 LLM 评测裁判（用 DeepSeek 模型做二次打分）
pytest tests/agent/test_golden_dataset.py --llm_judge

- -k "case_id" ：只跑某些 id 的 case
- -x ：遇到第一个失败就停
- --maxfail=1 ：最多失败 1 个就停
- -vv ：更详细的输出

如果想要更换模型，请
"""

import pytest
import json
import os
import re
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from langchain_openai import ChatOpenAI

console = Console()

from src.agent.lotus_test_agent import LotusTestAgent
from src.db.mongo_db import get_mongo_client, get_mongo_db
from tests.seed_data import DataSeeder
from src.agent.utils.AsyncMongoDBSaver import AsyncMongoDBSaver
from langgraph.checkpoint.base import WRITES_IDX_MAP
from datetime import datetime, timezone
from config.setting import get_settings

logger = logging.getLogger(__name__)

# --------------------------- Patch AsyncMongoDBSaver ---------------------------
# Mongomock has issues with bulk_write UpdateOne in some versions/contexts (specifically 'sort' arg error which is weird).
# We patch aput_writes to use update_one in a loop for tests.

async def patched_aput_writes(
    self,
    config,
    writes,
    task_id: str,
    task_path: str = "",
) -> None:
    await self._ensure_setup()
    thread_id = config["configurable"]["thread_id"]
    checkpoint_ns = config["configurable"]["checkpoint_ns"]
    checkpoint_id = config["configurable"]["checkpoint_id"]
    set_method = "$set" if all(w[0] in WRITES_IDX_MAP for w in writes) else "$setOnInsert"
    now = datetime.now(tz=timezone.utc)
    for idx, (channel, value) in enumerate(writes):
        upsert_query = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "task_path": task_path,
            "idx": WRITES_IDX_MAP.get(channel, idx),
        }
        type_, serialized_value = self.serde.dumps_typed(value)
        update_doc = {
            "channel": channel,
            "type": type_,
            "value": serialized_value,
        }
        if self.ttl:
            update_doc["created_at"] = now
        
        await self.writes_collection.update_one(
            upsert_query,
            {set_method: update_doc},
            upsert=True,
        )

AsyncMongoDBSaver.aput_writes = patched_aput_writes

# --------------------------- Dataset Loading ---------------------------
# Load at module level for parametrize
dataset_path = os.path.join(os.path.dirname(__file__), "../../data/test_data/golden_dataset.jsonl")
cases = []
if os.path.exists(dataset_path):
    with open(dataset_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("//"):
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
else:
    logger.warning(f"Dataset not found at {dataset_path}")

# --------------------------- Placeholder Resolver ---------------------------

class PlaceholderResolver:
    def __init__(self, alias_map: Dict[str, Any]):
        self.alias_map = alias_map

    def resolve(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        
        # Regex to match ${...}
        pattern = r"\$\{([^\}]+)\}"
        
        def repl(match):
            key = match.group(1)
            val = self.alias_map.get(key)
            if val is None:
                logger.warning(f"Placeholder key not found: {key}")
                return match.group(0) # Return original if not found
            return str(val)
            
        return re.sub(pattern, repl, text)

    def resolve_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.resolve(obj)
        elif isinstance(obj, list):
            return [self.resolve_obj(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self.resolve_obj(v) for k, v in obj.items()}
        return obj

# --------------------------- Model Evaluator ---------------------------

def _truncate_text(text: Any, limit: int = 4000) -> Any:
    if not isinstance(text, str):
        return text
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"

async def run_llm_judge(case: Dict[str, Any], expected_tool_calls: List[Dict[str, Any]], expected_state_change: Optional[Dict[str, Any]], actual_tool_calls: List[Dict[str, Any]], final_response: str, last_tool_name: Optional[str], last_tool_output: Any) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.llm.deepseek_api_key:
        return {"pass": None, "reason": "missing_llm_api_key"}
    llm = ChatOpenAI(
        model=settings.llm.deepseek_model,
        base_url=settings.llm.deepseek_base_url,
        api_key=settings.llm.deepseek_api_key,
        temperature=0,
        max_tokens=512,
        timeout=settings.llm.request_timeout,
    )
    payload = {
        "case": {
            "id": case.get("id"),
            "intent": case.get("intent"),
            "query": case.get("query"),
        },
        "expected_tool_calls": expected_tool_calls,
        "expected_state_change": expected_state_change,
        "actual_tool_calls": actual_tool_calls,
        "agent_output": {
            "final_response": _truncate_text(final_response, 2000),
            "last_tool_name": last_tool_name,
            "last_tool_output": _truncate_text(last_tool_output, 4000),
        },
    }
    system_prompt = "你是审慎且不过度严格的评测裁判。以用户意图是否被满足为主要判断标准。若实际工具调用包含预期关键工具且最终结果正确，允许存在额外工具调用或多一步查询，不应因此判失败；仅在额外调用导致结果错误、遗漏关键步骤或明显引入不相关结果时判失败。只输出 JSON，格式为 {\"pass\": true/false, \"reason\": \"不超过30字的说明\"}。"
    human_prompt = json.dumps(payload, ensure_ascii=False)
    response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])
    content = getattr(response, "content", "") or ""
    usage_metadata = getattr(response, "usage_metadata", None)
    token_usage = None
    if isinstance(usage_metadata, dict):
        token_usage = {
            "input_tokens": usage_metadata.get("input_tokens"),
            "output_tokens": usage_metadata.get("output_tokens"),
            "total_tokens": usage_metadata.get("total_tokens"),
        }
    try:
        parsed = json.loads(content)
        result = {"pass": parsed.get("pass"), "reason": parsed.get("reason", "")}
        if token_usage is not None:
            result["token_usage"] = token_usage
        return result
    except Exception:
        lowered = str(content).lower()
        if "true" in lowered and "false" not in lowered:
            result = {"pass": True, "reason": _truncate_text(content, 120)}
        elif "false" in lowered and "true" not in lowered:
            result = {"pass": False, "reason": _truncate_text(content, 120)}
        else:
            result = {"pass": None, "reason": _truncate_text(content, 120)}
        if token_usage is not None:
            result["token_usage"] = token_usage
        return result

class ModelEvaluator:
    def __init__(self):
        self.results = []
        self.failures = []
        self.details = [] # Store detailed traces
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def record_detail(self, case_id: str, query: str, trace: List[Dict], result: Dict):
        """Record detailed execution trace for a case"""
        detail = {
            "id": case_id,
            "query": query,
            "success": result["success"],
            "latency_ms": result["latency_ms"],
            "failure_reason": result.get("failure_reason"),
            "trace": trace
        }
        self.details.append(detail)

    def evaluate_case(self, case_id: str, intent: str, expected_tool_calls: List[Dict], 
                      actual_tool_calls: List[Dict], expected_state_change: Optional[Dict],
                      final_db_state: Any, latency_ms: float, error: Optional[str] = None,
                      llm_judge_result: Optional[Dict[str, Any]] = None,
                      agent_token_usage: Optional[Dict[str, Any]] = None):
        
        result = {
            "id": case_id,
            "intent": intent,
            "latency_ms": latency_ms,
            "success": False,
            "failure_reason": None,
            "metrics": {
                "tool_accuracy": 0.0,
                "tool_calls_count": len(actual_tool_calls)
            }
        }
        
        # 1. Check Error
        if error:
            result["success"] = False
            result["failure_reason"] = f"Runtime Error: {error}"
            self.failures.append(result)
            self.results.append(result)
            return result

        # 2. Tool Accuracy (TA)
        matched_tools = 0
        total_expected = len(expected_tool_calls)
        
        if total_expected > 0:
            for exp_tool in expected_tool_calls:
                exp_name = exp_tool["tool_name"]
                exp_args = exp_tool.get("arguments", {})
                
                found = False
                for act_tool in actual_tool_calls:
                    act_name = act_tool.get("name")
                    act_args = act_tool.get("args", {})
                    
                    if act_name == exp_name:
                        # Check args
                        args_match = True
                        for k, v in exp_args.items():
                            if k not in act_args or str(act_args[k]) != str(v):
                                args_match = False
                                break
                        if args_match:
                            found = True
                            break
                if found:
                    matched_tools += 1
            
            result["metrics"]["tool_accuracy"] = matched_tools / total_expected
        else:
            if not actual_tool_calls:
                result["metrics"]["tool_accuracy"] = 1.0
            else:
                result["metrics"]["tool_accuracy"] = 0.0 

        # 3. Success Rate (SR) - State Change
        state_success = True
        failure_msg = ""
        
        if expected_state_change:
            assertions = expected_state_change.get("assertions", [])
            for assertion in assertions:
                op = assertion.get("op")
                field = assertion.get("field") 
                value = assertion.get("value")
                
                actual_val = self._get_field_value(final_db_state, field)
                
                if op == "count_gte":
                    if not (isinstance(actual_val, list) and len(actual_val) >= value):
                        state_success = False
                        failure_msg += f"Assertion failed: {field} count {len(actual_val) if isinstance(actual_val, list) else 'N/A'} < {value}. "
                elif op == "field_equals":
                    if str(actual_val) != str(value):
                        state_success = False
                        failure_msg += f"Assertion failed: {field} {actual_val} != {value}. "
                elif op == "contains":
                    if isinstance(actual_val, list):
                        if value not in actual_val:
                            state_success = False
                            failure_msg += f"Assertion failed: {field} list does not contain {value}. "
                    elif isinstance(actual_val, str):
                         if str(value) not in actual_val:
                            state_success = False
                            failure_msg += f"Assertion failed: {field} string does not contain {value}. "
                    else:
                        state_success = False
                        failure_msg += f"Assertion failed: {field} type mismatch for contains. "
                elif op == "not_contains":
                    if isinstance(actual_val, list):
                        if value in actual_val:
                            state_success = False
                            failure_msg += f"Assertion failed: {field} list contains {value}. "
                elif op == "update" or op == "create":
                     if str(actual_val) != str(value) and op != "create": # For create, sometimes we check existence not value equals if value is dynamic? No, usually value is known.
                         # Exception: value_not
                         pass
                elif op == "delete":
                    if actual_val is not None and not getattr(actual_val, "is_deleted", False): # Check if really deleted or soft deleted
                         # If soft delete, check is_deleted=True
                         state_success = False
                         failure_msg += f"Assertion failed: Object {assertion.get('id')} still exists. "
                
                # Handle value_not
                if assertion.get("value_not") is not None:
                    val_not = assertion.get("value_not")
                    if str(actual_val) == str(val_not):
                        state_success = False
                        failure_msg += f"Assertion failed: {field} {actual_val} == {val_not} (should not be). "

        if expected_state_change and not state_success:
            result["success"] = False
            result["failure_reason"] = f"State Not Changed: {failure_msg}"
        elif expected_state_change is None and expected_tool_calls and result["metrics"]["tool_accuracy"] < 1.0:
             if result["metrics"]["tool_accuracy"] < 1.0:
                 result["success"] = False
                 result["failure_reason"] = "Key Tool Calls Missing"
             else:
                 result["success"] = True
        else:
             result["success"] = True
             
        rule_based_success = result["success"]
        result["metrics"]["rule_based_success"] = 1.0 if rule_based_success else 0.0
        if agent_token_usage is not None:
            result["metrics"]["agent_input_tokens"] = agent_token_usage.get("input_tokens")
            result["metrics"]["agent_output_tokens"] = agent_token_usage.get("output_tokens")
            result["metrics"]["agent_total_tokens"] = agent_token_usage.get("total_tokens")
        if llm_judge_result is not None:
            result["llm_judge"] = llm_judge_result
            judge_pass = llm_judge_result.get("pass")
            if judge_pass is True:
                result["success"] = True
                result["failure_reason"] = None
                result["metrics"]["llm_judge_pass"] = 1.0
            elif judge_pass is False:
                result["success"] = False
                reason = llm_judge_result.get("reason") or ""
                result["failure_reason"] = f"LLM Judge: {reason}".strip()
                result["metrics"]["llm_judge_pass"] = 0.0
            else:
                result["metrics"]["llm_judge_pass"] = None
            token_usage = llm_judge_result.get("token_usage") or {}
            if token_usage:
                result["metrics"]["judge_input_tokens"] = token_usage.get("input_tokens")
                result["metrics"]["judge_output_tokens"] = token_usage.get("output_tokens")
                result["metrics"]["judge_total_tokens"] = token_usage.get("total_tokens")
        
        if not result["success"]:
            self.failures.append(result)
            
        self.results.append(result)
        return result

    def _get_field_value(self, data, field_path):
        if not field_path:
            return data
        
        parts = field_path.split('.')
        current = data
        for part in parts:
            if '[' in part and ']' in part:
                key = part.split('[')[0]
                idx = int(part.split('[')[1].replace(']', ''))
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    return None
                
                if isinstance(current, list) and len(current) > idx:
                    current = current[idx]
                else:
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return None
        return current

    def generate_report(self):
        total = len(self.results)
        success = sum(1 for r in self.results if r["success"])
        sr = success / total if total > 0 else 0
        avg_latency = sum(r["latency_ms"] for r in self.results) / total if total > 0 else 0
        judge_token_cases = 0
        judge_input_tokens = 0
        judge_output_tokens = 0
        judge_total_tokens = 0
        agent_token_cases = 0
        agent_input_tokens = 0
        agent_output_tokens = 0
        agent_total_tokens = 0
        for r in self.results:
            metrics = r.get("metrics", {})
            if metrics.get("judge_total_tokens") is not None:
                judge_token_cases += 1
                judge_input_tokens += metrics.get("judge_input_tokens") or 0
                judge_output_tokens += metrics.get("judge_output_tokens") or 0
                judge_total_tokens += metrics.get("judge_total_tokens") or 0
            if metrics.get("agent_total_tokens") is not None:
                agent_token_cases += 1
                agent_input_tokens += metrics.get("agent_input_tokens") or 0
                agent_output_tokens += metrics.get("agent_output_tokens") or 0
                agent_total_tokens += metrics.get("agent_total_tokens") or 0
        avg_judge_input_tokens = judge_input_tokens / judge_token_cases if judge_token_cases > 0 else 0
        avg_judge_output_tokens = judge_output_tokens / judge_token_cases if judge_token_cases > 0 else 0
        avg_judge_total_tokens = judge_total_tokens / judge_token_cases if judge_token_cases > 0 else 0
        avg_agent_input_tokens = agent_input_tokens / agent_token_cases if agent_token_cases > 0 else 0
        avg_agent_output_tokens = agent_output_tokens / agent_token_cases if agent_token_cases > 0 else 0
        avg_agent_total_tokens = agent_total_tokens / agent_token_cases if agent_token_cases > 0 else 0
        
        return {
            "timestamp": self.timestamp,
            "git_like_version": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "metrics": {
                "success_rate": sr,
                "total_cases": total,
                "success_cases": success,
                "avg_latency_ms": avg_latency,
                "avg_judge_input_tokens": avg_judge_input_tokens,
                "avg_judge_output_tokens": avg_judge_output_tokens,
                "avg_judge_total_tokens": avg_judge_total_tokens,
                "avg_agent_input_tokens": avg_agent_input_tokens,
                "avg_agent_output_tokens": avg_agent_output_tokens,
                "avg_agent_total_tokens": avg_agent_total_tokens,
            },
            "failures": self.failures
        }

    def save_logs(self, log_dir):
        """Save both summary and details logs"""
        os.makedirs(log_dir, exist_ok=True)
        
        # 1. Summary
        report = self.generate_report()
        summary_path = os.path.join(log_dir, f"eval_summary_{self.timestamp}.json")
        with open(summary_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        # 2. Details (JSONL)
        details_path = os.path.join(log_dir, f"eval_details_{self.timestamp}.jsonl")
        with open(details_path, "w") as f:
            for detail in self.details:
                f.write(json.dumps(detail, ensure_ascii=False) + "\n")
                
        return summary_path, details_path

# --------------------------- Fixtures ---------------------------

@pytest.fixture(scope="session")
def evaluator():
    return ModelEvaluator()

@pytest.fixture(scope="session")
def resolver(test_seeder):
    return PlaceholderResolver(test_seeder.alias_map)

@pytest.fixture(autouse=True)
def patch_redis_for_repos(monkeypatch):
    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis()

    # 用于 BaseRedisRepo 等同步获取 Redis 客户端的场景
    monkeypatch.setattr("src.db.redis_db.get_redis_client", lambda: fake)
    monkeypatch.setattr("src.repos.cache_repos.base_redis_repo.get_redis_client", lambda: fake)

    # 用于 async_worker.core.send_task 中的异步获取客户端
    async def async_get_fake_redis():
        return fake

    monkeypatch.setattr("src.async_worker.core.get_redis_client", async_get_fake_redis)

    return fake

@pytest.fixture
def shared_agent(mongo_connection, patch_redis_for_repos):
    # Ensure mongo_connection is initialized
    from src.db.mongo_db import get_mongo_client
    return LotusTestAgent(client=get_mongo_client())

@pytest.fixture(scope="session", autouse=True)
def report_generator(evaluator):
    # Setup rich progress
    # We can't easily hook into pytest collection count here without hooks, 
    # but we can print summary at the end.
    yield
    
    # Save report
    log_dir = os.path.join(os.path.dirname(__file__), "../../logs/agent_eval")
    summary_path, details_path = evaluator.save_logs(log_dir)
    
    console.print(Panel(f"[bold green]Evaluation Report saved to:[/bold green]\n"
                        f"  Summary: [blue]{summary_path}[/blue]\n"
                        f"  Details: [blue]{details_path}[/blue]", 
                        title="Evaluation Complete"))
    
    # Calculate SR for printing
    report = evaluator.generate_report()
    sr = report['metrics']['success_rate']
    color = "green" if sr == 1.0 else "yellow" if sr > 0.8 else "red"
    console.print(f"Success Rate: [{color}]{sr:.2%}[/{color}]")

# --------------------------- Test Logic ---------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("case", cases, ids=[c.get("id", "unknown") for c in cases])
async def test_golden_dataset(case, shared_agent, resolver, evaluator, llm_judge_enabled, agent_arch):
    case_id = case.get("id")
    intent = case.get("intent")
    query = case.get("query")
    context = case.get("context", {})
    
    # Resolve Placeholders
    user_id = resolver.resolve(context.get("user_id"))
    logger.info(f"Resolved User ID: {user_id}")
    
    expected_tools = resolver.resolve_obj(case.get("expected_tool_calls", []))
    expected_state_change = resolver.resolve_obj(case.get("expected_state_change"))
    
    logger.info(f"Running Case {case_id}: {query}")
    
    thread_id = f"test_{case_id}_{datetime.now().timestamp()}"
    
    history = context.get("history")
    agent_query = query
    if history:
        history_lines = []
        for h in history:
            role = h.get("role")
            content = h.get("content", "")
            if role == "user":
                prefix = "用户"
            elif role == "assistant":
                prefix = "助手"
            else:
                prefix = role or ""
            history_lines.append(f"{prefix}: {content}")
        if history_lines:
            history_text = "\n".join(history_lines)
            agent_query = f"{history_text}\n\n当前问题：{query}"
    
    # Execute Agent
    start_time = datetime.now()
    error = None
    
    # Verify user exists in DB before running
    db = get_mongo_db()
    if user_id:
        try:
            u = await db.users.find_one({"_id": ObjectId(user_id)})
            logger.info(f"User found in DB: {u is not None}")
        except:
            logger.info(f"User ID invalid format: {user_id}")

    try:
        await shared_agent.ainvoke(agent_query, user_id=user_id, thread_id=thread_id, agent_selection=agent_arch)
    except Exception as e:
        error = str(e)
        logger.error(f"Case {case_id} failed: {e}")
        
    latency = (datetime.now() - start_time).total_seconds() * 1000
    
    # Inspect State
    config = {"configurable": {"thread_id": thread_id}}
    state = await shared_agent.graph.aget_state(config)
    messages = state.values.get("messages", [])
    
    # Extract Trace for Logging
    trace = []
    actual_tool_calls = []
    final_response = ""
    last_tool_name = None
    last_tool_output = None
    
    for msg in messages:
        role = "unknown"
        content = getattr(msg, "content", "")
        msg_trace = {"content": content}
        
        if isinstance(msg, HumanMessage):
            role = "user"
            msg_trace["role"] = role
            trace.append(msg_trace)
        elif isinstance(msg, AIMessage):
            role = "assistant"
            msg_trace["role"] = role
            if msg.tool_calls:
                msg_trace["tool_calls"] = []
                for tc in msg.tool_calls:
                    msg_trace["tool_calls"].append({
                        "name": tc.get("name"),
                        "args": tc.get("args"),
                        "id": tc.get("id")
                    })
                    actual_tool_calls.append(tc)
            else:
                 final_response = content
            trace.append(msg_trace)
        elif isinstance(msg, ToolMessage):
            role = "tool"
            msg_trace["role"] = role
            msg_trace["tool_name"] = msg.name
            msg_trace["tool_call_id"] = msg.tool_call_id
            last_tool_name = msg.name
            last_tool_output = msg.content
            trace.append(msg_trace)
                
    # State Verification
    final_db_state = None
    if expected_state_change:
        sc_type = expected_state_change.get("type")
        if sc_type == "response":
            last_tool_msg = None
            for msg in reversed(messages):
                if isinstance(msg, ToolMessage):
                    last_tool_msg = msg
                    break
            
            if last_tool_msg:
                try:
                    content = last_tool_msg.content
                    if isinstance(content, str):
                        # Try parsing as is
                        try:
                            final_db_state = json.loads(content)
                        except json.JSONDecodeError:
                            # Try finding JSON substring
                            match = re.search(r"(\{.*\})", content, re.DOTALL)
                            if match:
                                try:
                                    final_db_state = json.loads(match.group(1))
                                except:
                                    final_db_state = content
                            else:
                                final_db_state = content
                    else:
                        final_db_state = content
                except:
                    final_db_state = {}
            else:
                final_db_state = {}

        elif sc_type == "database":
            assertions = expected_state_change.get("assertions", [])
            if assertions:
                first_ass = assertions[0]
                model = first_ass.get("model")
                oid = resolver.resolve(first_ass.get("id"))
                
                db = get_mongo_db()
                fetched_obj = None
                
                if oid and not oid.startswith("placeholder_"):
                     try:
                        oid_obj = ObjectId(oid)
                        if model == "Library":
                             fetched_obj = await db.libraries.find_one({"_id": oid_obj})
                        elif model == "Movie":
                             fetched_obj = await db.movies.find_one({"_id": oid_obj})
                        elif model == "Collection":
                             fetched_obj = await db.user_custom_lists.find_one({"_id": oid_obj})
                        elif model == "Asset":
                             fetched_obj = await db.assets.find_one({"_id": oid_obj})
                        elif model == "UserAsset":
                             fetched_obj = await db.user_assets.find_one({"_id": oid_obj})
                        elif model == "WatchHistory":
                             fetched_obj = await db.watch_histories.find_one({"_id": oid_obj})
                        elif model == "Task":
                             fetched_obj = await db.tasks.find_one({"_id": oid_obj})
                     except:
                        pass
                elif first_ass.get("op") == "create":
                    field = first_ass.get("field")
                    val = first_ass.get("value")
                    if model == "Library":
                        fetched_obj = await db.libraries.find_one({field: val})
                    elif model == "Movie":
                        fetched_obj = await db.movies.find_one({field: val})
                    elif model == "Collection":
                        fetched_obj = await db.user_custom_lists.find_one({field: val})
                    elif model == "UserAsset":
                         fetched_obj = await db.user_assets.find_one({field: val})
                
                final_db_state = fetched_obj

    # Evaluate
    agent_input_tokens = 0
    agent_output_tokens = 0
    agent_total_tokens = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            usage = getattr(msg, "usage_metadata", None)
            if isinstance(usage, dict):
                agent_input_tokens += usage.get("input_tokens") or 0
                agent_output_tokens += usage.get("output_tokens") or 0
                agent_total_tokens += usage.get("total_tokens") or 0
    agent_token_usage = {
        "input_tokens": agent_input_tokens,
        "output_tokens": agent_output_tokens,
        "total_tokens": agent_total_tokens,
    }

    llm_judge_result = None
    use_llm_judge = llm_judge_enabled
    try:
        if use_llm_judge:
            llm_judge_result = await run_llm_judge(
                case,
                expected_tools,
                expected_state_change,
                actual_tool_calls,
                final_response,
                last_tool_name,
                last_tool_output,
            )
    except Exception as e:
        llm_judge_result = {"pass": None, "reason": str(e)}

    result = evaluator.evaluate_case(
        case_id,
        intent,
        expected_tools,
        actual_tool_calls,
        expected_state_change,
        final_db_state,
        latency,
        error,
        llm_judge_result,
        agent_token_usage,
    )
    
    # Record Detail
    evaluator.record_detail(case_id, query, trace, result)
    
    # Console Output (Rich)
    status = "[green]PASS[/green]" if result["success"] else f"[red]FAIL[/red] - {result['failure_reason']}"
    
    # Build trace display
    trace_text = Text()
    for item in trace:
        role = item.get("role", "unknown")
        content = item.get("content", "")
        if role == "user":
            trace_text.append(f"User: {content}\n", style="bold blue")
        elif role == "assistant":
            trace_text.append(f"Assistant: {str(content)[:100]}...\n", style="cyan")
            if item.get("tool_calls"):
                for tc in item["tool_calls"]:
                    trace_text.append(f"  Tool Call: {tc['name']}({tc['args']})\n", style="yellow")
        elif role == "tool":
             trace_text.append(f"Tool Output: {str(content)[:100]}...\n", style="dim")
             
    panel = Panel(
        trace_text,
        title=f"Case {case_id}: {query}",
        subtitle=f"Result: {status} | Latency: {latency:.2f}ms"
    )
    console.print(panel)
    
    # Assert success for pytest reporting
    # assert result["success"], f"Case {case_id} failed: {result['failure_reason']}"
