这份指南整体质量已经很高了，但我从实操角度看到几个会让 Vibe Coder **中途卡住**的问题：

---

# 执行指南 v2.0 审查意见

## 一、会导致"做到一半才发现行不通"的问题

### 🔴 问题 1：对话历史的归属权不清晰

```
P4-S01 实现会话持久化 —— 放在了最后一个阶段
但 P1-S04 的 AgentLoop 运行时就需要管理消息列表
P2-S03 的记忆提取需要读取对话历史
P3-S01 的上下文组装需要从某个地方加载历史消息
```

**现状**：P1-P3 阶段都在用一个"不知道从哪来"的消息列表工作，直到 P4 才定义它的持久化方式。这意味着前三个阶段的所有测试都在用临时 `list[Message]`，到 P4 集成时很可能发现接口对不上。

**建议**：将 `Message` 数据模型和 `ConversationHistory`（纯内存版）提前到 **P1-S01** 定义：

```python
# P1-S01 中就应该定义
class Message(TypedDict):
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_calls: list[ToolCall] | None
    tool_call_id: str | None

class ConversationHistory:
    """内存版，P4 再加持久化"""
    messages: list[Message]
    def add(self, msg: Message) -> None: ...
    def get_recent(self, n: int) -> list[Message]: ...
    def to_llm_messages(self) -> list[dict]: ...
```

---

### 🔴 问题 2：P1-S04 的 AgentLoop 移植范围模糊

P1-S04 说"仅移植核心迭代逻辑，剥离 MessageBus/Channels/MCP"，但没有说清楚 **剥离之后用什么替代**。

```
Nanobot AgentLoop 内部依赖：
  - MessageBus → 用于向 UI 推送事件
  - Channels   → 用于工具结果回传
  - MCP        → 用于外部工具协议

剥离后：
  - 事件推送 → 改成什么？直接 yield？回调函数？
  - 工具结果回传 → 改成什么？直接函数调用返回？
  - 外部工具协议 → 不需要？还是预留接口？
```

**建议**：在 P1-S04 的具体操作中明确替代方案：

```
具体操作：
  1. 移植 Nanobot _run_agent_loop 核心迭代
  2. MessageBus 事件推送 → 替换为 AsyncGenerator[StreamEvent, None]
     定义 StreamEvent = TextDelta | ToolStart | ToolEnd | Error
  3. 工具结果回传 → 直接同步调用 registry.execute(tool_name, args)
  4. MCP → 不移植，不预留
```

---

### 🟡 问题 3：user-id 注入方式一笔带过

P1-S05 提到"user-id 是由 LangGraph 注入的，需要额外关照"，但没说 **怎么关照**。这个问题会贯穿整个重构——工具执行需要 user-id，记忆查询需要 user-id，会话管理需要 user-id。

**建议**：在 P1-S01 中定义一个贯穿全局的 `RequestContext`：

```python
# 在 P1-S01 types.py 中定义
@dataclass
class RequestContext:
    user_id: str
    session_id: str
    trace_id: str  # 用于日志追踪

# AgentLoop.__init__ 接收它
# 工具执行时通过它获取 user_id
# 记忆查询时通过它获取 user_id + session_id
```

并在每个使用 user-id 的步骤中标注 `从 RequestContext 获取`。

---

## 二、步骤粒度问题

### 🟡 问题 4：P3-S01 至少是两个步骤的工作量

```
P3-S01 要求同时做：
  1. 移植上下文组装器（从 Nanobot 适配）
  2. 实现 ContextBudget 预算制
  3. 集成 ProgressiveSummarizer
```

`ProgressiveSummarizer` 本身就需要：定义摘要 Prompt、实现摘要触发条件判断、处理摘要与原文的替换逻辑。这不是 30 分钟能完成的。

**建议拆分**：

```
P3-S01  移植上下文组装器骨架（Nanobot context.py 适配，含 Budget 计算）
P3-S01a 实现 ProgressiveSummarizer（摘要 Prompt + 触发条件 + 替换逻辑）
P3-S01b 集成 Summarizer 到 Assembler（溢出时自动触发摘要）
```

---

### 🟡 问题 5：P4-S04 "全链路验证"不是一个可执行步骤

```
P4-S04 的具体操作：
  1. 验证 Memory 写入
  2. 验证 Delegation
  3. 验证多轮对话历史

验证方式：通过前端或脚本进行完整场景测试
```

这等于什么都没说。开发者会问：**测什么场景？期望什么结果？用什么脚本？**

**建议替换为具体的验收场景表**：

```markdown
| 场景 | 输入 | 预期行为 | 验证点 |
|------|------|----------|--------|
| 基础对话 | "你好" | Agent 回复问候 | SSE 流式输出，状态码 200 |
| 工具调用 | "搜索周杰伦的歌" | 调用 search_media | 返回结果包含歌曲列表 |
| 多轮记忆 | 第1轮："我喜欢爵士乐"<br>第2轮："推荐一些音乐" | 推荐基于爵士偏好 | 记忆表中存在偏好记录 |
| 委派 | "帮我深入研究X" | 触发子Agent | 日志中出现 delegation 事件 |
| 上下文溢出 | 连续20轮对话 | 触发摘要压缩 | Token 数不超过预算上限 |
| 会话恢复 | 重启服务后继续对话 | 历史消息从 Mongo 加载 | 第1轮的消息仍然可见 |
```

---

## 三、缺失环节

### 🔴 问题 6：没有 `StreamEvent` 协议的统一定义

全文多次提到流式输出、SSE 格式，但没有一个步骤统一定义 **流式事件的数据协议**。前端需要的 SSE 格式是什么？工具调用中间态怎么推送？

**建议**：在 P1-S03a 之前（或合并到 P1-S01）定义：

```python
class StreamEvent(TypedDict):
    type: Literal["text_delta", "tool_start", "tool_end",
                   "error", "done", "thinking"]
    data: dict
    # text_delta: {"content": "..."}
    # tool_start: {"tool_name": "...", "args": {...}}
    # tool_end:   {"tool_name": "...", "result": "..."}
    # done:       {"usage": {"input_tokens": N, "output_tokens": N}}
```

---

### 🟡 问题 7：错误处理策略缺失

整份指南没有一个步骤专门处理以下场景：

```
- LLM API 调用超时/限流 → 重试？降级？报错？
- 工具执行抛异常 → 给 LLM 返回错误信息？还是直接终止？
- Token 超限（输入就已经超了） → 强制截断？报错？
- 子 Agent 无限循环 → 如何检测和中断？
```

**建议**：在 P1-S04（AgentLoop）中新增一个错误处理策略表，并在具体操作中要求实现：

```python
ERROR_STRATEGIES = {
    "llm_timeout": "重试 2 次，间隔 2s/4s，仍失败则返回错误消息",
    "llm_rate_limit": "等待 Retry-After 头指定的时间后重试",
    "tool_exception": "将 traceback 摘要作为 tool result 返回给 LLM",
    "token_overflow": "触发 ProgressiveSummarizer，压缩后重试",
    "loop_detection": "连续 3 次相同工具调用 → 注入反思 prompt（已有）",
    "max_iterations": "硬上限 25 轮，超过后返回 '任务过于复杂' 消息",
}
```

---

## 四、修改建议汇总

```
优先级    问题    修改动作
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 P0    #1 对话历史归属     P1-S01 补充 Message + ConversationHistory 定义
🔴 P0    #2 Loop替代方案     P1-S04 明确 MessageBus/Channel 的替代实现
🔴 P0    #6 StreamEvent     P1-S01 或 P1-S03a 前定义统一协议
🟡 P1    #3 user-id注入     P1-S01 补充 RequestContext
🟡 P1    #4 P3-S01拆分      拆为 S01/S01a/S01b
🟡 P1    #5 全链路验证       P4-S04 替换为具体验收场景表
🟡 P1    #7 错误处理         P1-S04 补充错误处理策略表
🟡 P2    #8 PM文件位置       移到 .refactor/ 目录
```

> 上述问题修复后，这份指南就具备了让一个 Vibe Coder **从头走到尾不卡���**的可执行性。最关键的是前三个 P0 问题——它们不修复的话，开发者到 P3/P4 阶段大概率需要回头重构 P1 的代码。