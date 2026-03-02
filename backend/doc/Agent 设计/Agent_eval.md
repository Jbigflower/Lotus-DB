本指南详细说明如何使用 pytest 和 golden_dataset.jsonl 文件为 LotusDBAgent 实现一套健壮的测试运行器。

1. 架构概述

LotusTestAgent：LotusDBAgent 的子类，覆盖了连接属性，确保所有数据库操作（包括 LangGraph 检查点）都在模拟的 mongomock 环境中执行，使测试与真实数据库隔离。
测试运行器：一个 pytest 测试文件（例如 tests/agent/test_golden_dataset.py），负责加载 JSONL 文件、参数化测试用例并执行测试。
占位符解析器：一个工具函数，用于将数据集中 ${world.users.xxx.id} 这类占位符动态替换为 test_seeder 生成的真实 ObjectID。
模型评估器：一个工具函数，用于比较测试运行器生成的输出与数据集中的预期输出，判断测试是否通过。评估指标包括：

2. 背景

lotus-db-backend-refactor/tests/conftest.py 测试环境
lotus-db-backend-refactor/tests/seed_data.py 仿真数据
lotus-db-backend-refactor/data/test_data/golden_dataset.jsonl 测试数据集
lotus-db-backend-refactor/src/agent Agent 入口

## 一、LotusTestAgent

.src/agent/lotus_test_agent.py，该类确保代理使用测试环境的基础设施。LotusTestAgent 是为了避免直接修改 LotusAgent（比如返回格式不兼容）而设计的，它继承自 LotusAgent 并覆盖了连接属性，将数据库操作指向 mongomock 环境，使用真实的 LLM API 进行推理。
注意：当前 LotusAgent 的两个可供测试的 Agent 分别是 React base & React Augment。但是他们似乎没有拿到全部的工具，请修复lotus-db-backend-refactor/src/agent/tools/factory.py 将所有工具给 React base & React Augment。

## 二、测试运行器

新建 tests/agent/test_golden_dataset.py 文件，测试 JSONL 文件中的每一行测试用例，通过 eval 脚本生成评估结果。

## 三、占位符解析器

tests/agent/test_golden_dataset.py 内置，用于将数据集中 ${world.users.xxx.id} 这类占位符动态替换为 test_seeder 生成的真实 ObjectID。
注意：JSONL 文件中使用 ${world.movies.Red_Sorghum.id} 这类键，但 DataSeeder.movies 字典的键是影片标题（如 “红高粱”），而非英文别名键。需更新 tests/seed_data.py，维护 “别名键 → 数据库对象” 的健壮映射关系。建议在 seeder 中新增 self.alias_map 属性，将 “Red_Sorghum” 映射到实际插入的 ID。

## 四、模型评估

1.  **Success Rate（SR）**：满足 `expected_state_change` 的用例比例。
2.  **Tool Accuracy（TA）**：工具名与关键参数命中率，允许模型执行多余的动作，只要关键调用匹配正确即可，参数匹配不要求完全一致。
3.  **Step Metrics**：
    - `tool_calls_per_case`：每条用例工具调用次数
    - `max_step_violation_rate`：超过上限的比例
4.  **Latency**：
    - `latency_ms_p50/p95`：每条用例耗时分位数
5.  **Safety**：
    - `guardrail_trigger_rate`：高风险用例是否触发确认
    - `forbidden_operation_block_rate`：越权用例被正确拒绝的比例

每次评测需输出一份 JSON 报告（保存在 `logs/agent_eval/<model_name>_<timestamp>` 下，避免污染仓库根目录）：

- 文件名：eval_summary.json + 各个测试用例的完整对话（可以参考服务层的 LLM service 如何获取对话历史）
- eval_summary.json 最小字段：
  - `git_like_version`（手动传入或用日期版本）
  - `metrics`（整体指标）
  - `by_intent`（分桶指标）
  - `failures[]`（失败用例列表，含失败类型与关键上下文）

失败分类（必须记录，便于后续优化）：

- `INTENT_WRONG`：意图识别错误
- `TOOL_NOT_FOUND`：不存在的工具或路由错误
- `ARGUMENT_INVALID`：参数格式/字段错误
- `PERMISSION_FORBIDDEN`：越权被拦截（对负样本可能是正确结果）
- `STATE_NOT_CHANGED`：执行了工具但状态未达预期
- `TIMEOUT`：超时
