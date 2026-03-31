## `llm_service.py`

### `get_user_history_list` 逻辑简化

```python
    async def get_user_history_list(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户历史记录"""
        self._ensure_ready()
        cursor = self._session_collection.find({"user_id": user_id}).sort("updated_at", -1)
        docs = await cursor.to_list(length=None)
        results: List[Dict[str, Any]] = []
        from src.agent.session import Session

        for doc in docs:
            session = Session.from_dict(doc)
            preview = _preview_from_messages(session.messages)
            updated_at = session.updated_at.isoformat() if session.updated_at else None
            results.append(
                {
                    "thread_id": session.session_id,
                    "last_updated": updated_at,
                    "preview": preview,
                }
            )
        return results
```
当前 get_user_history_list 实现的主要问题是 每次获取用户历史列表时，都需要从数据库中加载该用户的全部完整会话文档，然后从中提取预览信息。当用户会话数量多、每条会话的消息数量大时，会造成大量不必要的 I/O 开销和内存占用，属于典型的资源浪费。其根本原因在于存储格式设计不合理——将会话的元数据（如最后更新时间、预览）与完整的消息列表捆绑存储在同一个文档中，导致查询历史列表这一高频轻量操作不得不承受沉重的数据读取代价。

我们可以参考 Langgraph 的设计理念，采用双层存储策略：
1. 会话元数据（如用户ID、会话ID、最后更新时间、预览）存储在一个独立的文档中，与完整消息列表分离。
2. 完整消息列表则存储在一个单独的文档中，文档ID与会话ID对应。

这样设计的好处是：
- 查询历史列表时，只需要加载会话元数据文档，而无需加载完整消息列表，大大减少了 I/O 开销。
- 当需要查看具体会话详情时，再根据会话ID加载对应的完整消息列表文档。

这种分离存储的方式，不仅符合数据库的最佳实践，也更符合实际应用场景中对查询效率的要求。

另外，我们还可以进一步对完整消息列表进行拆分，将每个会话的消息列表拆分成多个子文档，每个子文档存储一部分消息。这样可以在需要查看具体会话详情时，只需要加载相关的子文档，而不是整个会话文档。

### `self._supported_versions`

`self._supported_versions` 该属性属于旧版本 Agent 设计，在重构时应该移除

`Agent_version` 同理

### `delete_chat` 逻辑层级混淆
```python
    async def delete_chat(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        """删除用户聊天记录"""
        self._ensure_ready()
        await self._session_collection.delete_one(
            {"session_id": thread_id, "user_id": user_id}
        )
        return {"status": "success", "thread_id": thread_id}
```

我们看到，`delete_chat` 是直接在服务层进行了数据库删除这种底层操作，而不是采用会话管理器的接口，这不利于后续的扩展和维护。

我们应该将删除操作委托给会话管理器处理，会话管理器负责维护会话状态和与数据库的交互。这样可以保持服务层的专注于业务逻辑，而将数据库操作抽象到会话管理器中。

修改后的 `delete_chat` 方法如下：
```python
    async def delete_chat(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        """删除用户聊天记录"""
        self._ensure_ready()
        result = await self._session_manager.delete(thread_id, user_id=user_id)
        if result is None:
            raise ValueError(f"Failed to delete chat {thread_id} for user {user_id}")
        return {"status": "success", "thread_id": thread_id}
```

### `_preview_from_messages` 函数

```python
def _preview_from_messages(messages) -> str:
    for message in reversed(messages or []):
        content = message.content if hasattr(message, "content") else ""
        if content:
            return str(content)[:200]
    return ""
```

当前的对话摘要是通过 `_preview_from_messages` 函数实现的，该函数从消息列表中提取最后一条非空消息的前 200 个字符作为预览。
对于项目初期，我们可以简单地将最后一条消息的前 200 个字符作为预览。后续可以根据实际需求和用户反馈，考虑引入更智能的预览逻辑，例如提取用户问题、模型回复等。
所以这里记录，并作为 future 优化项。

<!-- ## `agent_service_v2.py`

### 和 `llm_service.py` 冗余

`agent_service_v2.py` 与 `llm_service.py` 出现冗余，根本原因是重构过程中过度考虑对旧代码的兼容，导致“新旧并存”：

1. 两套服务都实现了“会话管理”相关接口（如 `get_user_history_list`、`delete_chat`），甚至都直接依赖同一张 Mongo 表。  
2. `agent_service_v2.py` 里为了“兼容老调用方”，把 `llm_service.py` 的代码整体拷贝一份后再做微调，结果 90 % 代码重复，仅命名或返回字段略有差异。  
3. 旧版本 Agent 的 `agent_version`、`supported_versions` 字段被原样保留，新服务不得不跟着实现一堆“废接口”，进一步加剧冗余。  
4. 调用链也因此出现“绕路”现象：外部请求 → `agent_service_v2` → 重复逻辑 → 同一 DB，既增加维护成本，又让人分不清“主入口”到底是哪个。

如何根治：

1. 明确“唯一真相源”  
   - 路由层请求统一收敛到 `llm_service.py`，移除  `agent_service_v2.py` 
2. 旧接口一次性下线  
   - 删除 `llm_service.py` 中旧代码设计，如 `agent_version`、`supported_versions`。 -->

<!-- ## `session.py`

- 缺少索引 ：数据库索引集中创建处没有 agent_sessions ，而查询路径依赖 user_id + updated_at 、 session_id + user_id ，没有索引会退化为全表扫描（ mongo_db.py:L101-L205 , session.py:L93-L119 ）。
- 无唯一性约束 ： save 以 {session_id, user_id} 作为 upsert 查询键，但未建立唯一索引，竞争场景可能产生重复文档（ session.py:L112-L119 ）。
- 无 TTL / 清理策略 ：会话无限增长，缺少过期清理或归档策略，易导致集合膨胀，查询持续变慢（ session.py:L12-L119 ）。
- 消息体无限增长 ：每次保存都是整段 messages 数组写回，没有截断或增量写入策略，长会话成本极高（ session.py:L49-L60 , session.py:L112-L119 ）。
- 并发安全弱 ： get_or_create 与 save 间没有版本号/乐观锁（这里可以接受，因为我们场景主要是单机家庭使用），可能出现并发写回覆盖（last-write-wins）问题（ session.py:L104-L119 ）。
- last_consolidated 未形成闭环 ： get_history 依赖 last_consolidated ，但当前实现中没有更新它的逻辑，导致“只取未整合消息”的设计形同虚设（ session.py:L30-L39 ）。
- 消息时间字段缺失 ： get_thread_detail 对消息只输出 created_at=None ，会话内消息没有稳定时间戳，无法排序/审计（ llm_service.py:L91-L107 ）。
- 权限边界不强 ： SessionManager.load 允许 user_id=None ，上层若未提供 user_id，可能读到同 session_id 的其他用户会话（ session.py:L93-L103 ）。
- 存储格式设计不合理 ： 将会话的元数据（如最后更新时间、预览）与完整的消息列表捆绑存储在同一个文档中，导致查询历史列表这一高频轻量操作不得不承受沉重的数据读取代价。 -->

## `loop.py`

### 子代理的并发性问题

```python
    async def _execute_tool(
        self,
        name: str,
        args: Dict[str, Any],
        ctx: RequestContext,
    ) -> Tuple[str, Optional[str]]:
        """执行工具并返回结果与错误。"""
        try:
            if name == "delegate":
                if not self.config.can_delegate:
                    return "Error: delegate not allowed", "delegate_not_allowed"
                required_tools = args.get("required_tools") or []
                if not isinstance(required_tools, list):
                    required_tools = []
                specialist_type = args.get("specialist_type") or "general"
                result = await self.delegation_handler.handle(
                    task_description=str(args.get("task_description") or ""),
                    context=str(args.get("context") or ""),
                    expected_output=str(args.get("expected_output") or ""),
                    required_tools=required_tools,
                    specialist_type=str(specialist_type),
                    ctx=ctx,
                )
                result = self._trim_tool_result(result)
                return result, None
            result = await self.tools.execute(name, args, ctx=ctx)
            result = self._trim_tool_result(result)
            if isinstance(result, str) and result.startswith("Error"):
                return result, result
            return result, None
        except Exception as exc:
            message = f"{exc}"
            message = message[:400]
            return f"Error executing {name}: {message}", message
```

并发安全性

### context 管理器

为什么不在 `run` 中调用 `context_assembler.assemble` ？而是在更为底层的 `_call_llm` 中？

```Python
async def _call_llm(self, messages):
    messages = await self.context_assembler.fit_to_budget(messages, self.config)
    # fit_to_budget 可能返回新列表，也可能原地修改
```
返回 Tuple[..., messages] 再在外层继续用，逻辑正确但容易混乱。调用方 run() 里：

```Python
response, error_type, messages = await self._call_llm(messages)
```
如果 fit_to_budget 对 messages 做了摘要压缩，外层的 messages 变量被替换了，后续追加的 tool 消息是追加到压缩后的版本上——这是设计意图，但没有注释说明，维护者容易误解。

### 记忆管理

三层记忆系统的基础架构已经完成，但在当前的 Agent Loop 实现中还没有完全激活和集成。

个人感觉，应该在 `_build_messages` 中显式管理记忆。

### _call_llm 的无限循环风险

```python
async def _call_llm(self, messages) -> Tuple[...]:
    timeout_attempts = 2
    rate_limit_attempts = 2
    overflow_attempts = 1

    while True:  # ← 没有兜底退出条件
        messages = await self.context_assembler.fit_to_budget(messages, self.config)
        response = await self.llm.chat(...)

        ......
```
如果 fit_to_budget 抛异常呢？没有任何异常捕获，会导致 run() 的 async generator 直接崩溃，不会发出 done 事件。

### text_delta 事件名不副实 & 流失输出缺陷

```python
            content = response.content or ""
            if content:
                yield {"type": "text_delta", "data": {"content": content}}
            yield {"type": "done", "data": {"content": content}}
            return
```

text_delta 语义上是"增量文本块"，但这里发的是完整回复。上层 ChatService.chat_stream 用 chunks.append() 收集所有 delta 再拼接——如果将来真的实现了流式（SSE），同一段内容会在 delta 和 done 里各出现一次，导致重复。

整个 run() 方法调用 self.llm.chat() 等待完整响应后才 yield。如果 LLM 支持流式（SSE），当前架构无法利用。这不是 bug，但上层和事件类型名都暗示了流式能力，实际没有。

### 工具错误判定靠字符串前缀

```Python
if isinstance(result, str) and result.startswith("Error"):
    return result, result  # ← 把整个错误字符串当 error 标记
```

这极其脆弱：

如果工具正常返回的文本恰好以 "Error" 开头呢？
如果错误信息是中文呢？
tool_error 被赋值为完整结果字符串，但上层只检查 if tool_error: 来决定是否发 error 事件

建议修改 工具调用返回格式，从 字符串 更改为 pydantic 对象

### _truncate_messages 裁剪消息列表 过于粗暴
```Python

def _truncate_messages(self, messages):
    if len(messages) <= 6:
        return messages
    head = messages[:1]   # 只保留 system prompt
    tail = messages[-5:]  # 保留最后 5 条
    return head + tail
```

问题：

砍掉了所有中间上下文，LLM 可能完全丧失对话连贯性
tool_call 和 tool result 必须成对出现，这种粗暴截断很可能把一对拆开，导致 LLM API 报 invalid messages 错误
与 context_assembler.fit_to_budget 功能重叠，职责不清

### 工具循环检测只检查连续同名

工具循环检测只检查连续同名
```Python

def _update_tool_loop(self, last_name, count, new_name):
    if new_name == last_name:
        return new_name, count + 1
    return new_name, 1
```
只检测 A → A → A 模式，无法检测 A → B → A → B → A → B 这种交替循环。而且 LLM 单次返回多个 tool_calls 时，循环检测在内层 for 里，只检查了连续的 tool_call name，不是连续的 LLM 回合。

### context_assembler 和 delegation_handler 注入但未使用到位
```Python

self.context_assembler = context_assembler or ContextAssembler(
    token_counter=self._token_counter,  # ← 用的是 len/4 的粗估
    summarizer=ProgressiveSummarizer(llm_client=llm),
)
```
_token_counter 是 len(text) // 4，这与实际 token 数差异很大（中文尤其不准，一个中文字符约 1-2 token，但 len 返回的是字符数）。

## tools/base.py

缺失项	说明
nullable 支持	JSON Schema 的 nullable/null type 未处理
oneOf / anyOf / allOf	复合 schema 未支持
additionalProperties	未校验是否传入了 schema 中未定义的额外字段
pattern	字符串正则校验未支持
default 值填充	cast_params 未对缺失字段填充默认值
ref 引用	不支持 schema 引用
超时控制	execute() 没有超时机制，handler 可以无限阻塞
确认机制	requires_confirmation 仅声明未实现
format 校验	如 "format": "date-time" 未处理


## tools/registry.py

_handler_accepts_ctx 对 **kwargs 的处理过于宽松, 意味着任何带 **kwargs 的 handler 都会收到 ctx，即使它根本不关心 ctx。如果 handler 把 **kwargs 透传给其他函数，可能导致意外传播。

我们需要修改 ToolDefinition 类，显示添加需要的 ctx 参数名称，而不是依赖 _handler_accepts_ctx 来判断。

错误判断靠字符串前缀 "Error" 太脆弱，没有和 type.py 中定义的 ToolResponese 对齐。使用结构化返回而非字符串前缀判断。


与 delegation.py 的交互：空列表变成了“全部工具”——严重权限绕过
之前在 ToolRegistry 里你写的是：

```Python

def get_tools(self, allowed: Optional[List[str]] = None) -> Dict[str, ToolDefinition]:
    if not allowed:
        return dict(self._tools)  # allowed=[] 时也会返回所有工具
    return {n: t for n, t in self._tools.items() if n in allowed}
```
而在这里：

```Python

# general / 未知 specialist_type 时
return AgentConfig(
    ...,
    allowed_tools=tools,  # tools 可能为空列表 []
)
```
如果 required_tools 是 None 或空列表，则 tools = []
AgentConfig.allowed_tools = []
在 AgentLoop 里很可能会做类似：
Python

registry.get_tools(allowed=config.allowed_tools)
传入的就是 allowed=[]，结果 get_tools 返回“所有已注册工具”。
这意味着：

你原本想创建一个“没有任何工具”的子智能体（allowed_tools = []）
实际上却给了它“所有工具”的访问权限
如果外层 Agent 对某些工具是受限的，但它可以调用 delegate 工具，就有机会通过“创建 general 子 Agent 且不传 required_tools”来获取比自己更高的权限。

这点非常关键，强烈建议优先修复：

```Python

def get_tools(self, allowed: Optional[List[str]] = None) -> Dict[str, ToolDefinition]:
    if allowed is None:              # 只有 None 表示“不加限制”
        return dict(self._tools)
    return {n: t for n, t in self._tools.items() if n in allowed}
```
然后确保所有调用 get_tools 的地方都传 None/具体列表，而不是故意用 [] 当“全部”。

## context

### 工具和记忆 压缩混淆

工具的压缩 和 记忆的压缩 统一走的 _compress_section 方法，只是传入的参数不同。

但是，工具的压缩 和 记忆的压缩 在主流的开源项目中，都是不同的实现，简单的使用同一逻辑不利于关键信息的保留，比如：工具压缩可以检测 A-Failed -- A-Failed -- A-success，并丢弃前两个失败的，保留最后一个成功的。

##  Memory

Memory 已接入 AgentLoop 的 `_build_messages`，并通过 `memory_context` 分区进入 `ContextAssembler`，记忆压缩与摘要可生效。三层记忆的动态加载与按需召回通过 MemoryRuntime 统一管理，system_core 仅承载稳定规则摘要，细节记忆放入 memory_context。

### 记忆加载策略

Layer 1: Agent 记忆 → 启动预加载 + 按需深度召回
Agent 记忆特点：
- 全局共享，不区分用户
- 变更频率低（策略/规则/文档）
- 数据量可能很大
策略：核心规则预加载，详细文档按需召回
注入位置：System Prompt

Layer 2: 用户记忆 → 会话初始化加载 + 对话中按需补充
用户记忆特点：
- 按用户隔离
- 包含偏好、事实、历史行为模式
- 数据量中等，但随时间增长
策略：会话开始时加载用户画像摘要，对话中按需召回细节
对话中按需召回：用户说了某个话题，检索相关的用户记忆，例：用户提到「上次那个项目」→ 召回与项目相关的用户记忆

Layer 3: 会话记忆 → 始终在上下文 + 滚动窗口管理
会话记忆特点：
- 生命周期 = 单次对话
- 包含完整对话历史、临时目标、工作状态
- 数据量小但增长快
策略：始终保持在上下文中，但需要滚动管理防止溢出

### 记忆加载 & KV Cache

当前策略是将 Agent 核心规则摘要写入 system_core，其余记忆写入 memory_context 分区，避免频繁改写 system prompt 的首条内容，降低 KV Cache 失效概率。若需要进一步优化，可将稳定规则固化为独立 system 片段并减少动态拼接频率。


### extraction.py

class ConflictResolverProtocol(Protocol):
    """冲突解决器协议。"""

    async def resolve_and_store(self, item: MemoryItem) -> None:
        """处理冲突并写入存储。"""

已实现：ConflictResolver 作为冲突解决器实现该协议，并在 ExtractionPipeline 中被注入执行。


    EXTRACTION_SYSTEM_PROMPT = (
        "你是一个记忆提取助手。根据给定的对话片段，提取结构化的记忆项。\n\n"
        "每个记忆项必须包含：\n"
        '- category: "fact" | "preference" | "behavior" | "correction"\n'
        "- content: 简洁的自然语言陈述（一句话）\n"
        '- confidence: "high" | "medium" | "low"\n'
        "- source_turn_id: 从哪个对话轮次提取的\n"
        "- entities: 提到的实体列表\n\n"
        "规则：\n"
        "1. 只提取明确陈述或强烈暗示的内容。\n"
        "2. 偏好必须捕捉倾向（喜欢/不喜欢），可选强度。\n"
        "3. 如果用户更正了之前的陈述，输出一个 \"correction\" 项。\n"
        "4. 不要从问候语或闲聊中臆想偏好。\n"
        "输出格式：JSON 数组。"
    )

已对齐：ExtractionPipeline 将 "high/medium/low" 置信度映射为数值并写入 MemoryItem。

## Agent Loop 中 和 Tools 存在强耦合 + 功能重复实现，需要优化。


