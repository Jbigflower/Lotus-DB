一、总则：先锁定“关键链路”再做比对

- 锁定对象：所有「对外暴露的业务动作」：
  - 创建类：create_*
  - 更新类：update_*
  - 删除 / 恢复类：delete_* / restore_*
  - 列表 / 搜索类：list_* / search_*
- 对每个动作，明确三条链路：
  - HTTP 路由： src/routers/**.py
  - 服务层： src/services/**.py
  - Agent 工具： src/agent/tools/**.py
- 目标： 确认这三条链路在「请求模型 → 服务调用 → 返回模型」上是一致的 ，尤其是：
  - 使用的 Pydantic 模型
  - 字段名 / 默认值 / 类型
  - 业务兜底逻辑（例如 root_path / user_id / 权限）

二、针对创建库的完整对比模板（可复用到其他功能）

以 create_library 为模板，其他实体可以按同样步骤检查：

1. 比对 HTTP 路由和服务层
   
   - 路由文件： src/routers/libraries.py
     
     - 确认：
       - 请求模型： LibraryCreateRequestSchema
       - 转换模型： LibraryCreate(...)
       - 显式设置的字段： user_id 、 root_path="temp" 、 activated_plugins
     - 记录所有「由路由层填充的默认值／上下文字段」：
       - user_id
       - root_path
       - activated_plugins
   - 服务层： LibraryService.create_library
     
     - 确认注释预期： “路由层已负责转换与填充默认值，这里做稳健性补全”
     - 确认兜底逻辑：
       - payload.setdefault("user_id", current_user.id)
       - payload.setdefault("root_path", "temp")
     - 检查： 如果换成 Agent 工具传入，兜底逻辑是否仍然有效（例如 model_dump(exclude_unset=True) vs 默认 model_dump() ）
2. 比对 Agent 工具和 HTTP 路由
   
   - Agent 工具文件： src/agent/tools/library_tools.py
   - 检查项：
     - args_schema 是否只承载「对话层友好的字段名」，而真正构造业务模型时是否做了字段映射
     - 是否直接构造 LibraryCreate 而绕过了 HTTP 路由的补丁逻辑
     - 字段映射是否正确：
       - library_type → type: LibraryType
       - 是否显式设置 root_path （或让服务层兜底能生效）
       - 是否设置 activated_plugins （哪怕是空映射），保证与路由一致
   - 核心 Checklist：
     - Agent 工具使用的业务模型类型与 HTTP 路由一致（例如都用 LibraryCreate ）
     - Agent 工具传入的字段名与业务模型字段名一致（或有显式映射逻辑）
     - Agent 工具对「路由层负责填充的字段」有等价处理（直接复用或调用公共构造函数）
三、显式一条：Agent 工具路径必须复用 HTTP 路由创建逻辑

这是你特别提到的，单独点出来作为强约束：

- 为每个「对外暴露的创建 API」，抽象出一个公共的“构造业务模型”的函数 / 工具，例如：
  - _build_library_create_payload(payload_schema, current_user) 或
  - LibraryService.build_library_create_model(...)
- HTTP 路由和 Agent 工具都只做两件事：
  - 从各自的入参（HTTP Body 或 Agent args_schema）解析出「高层语义字段」（如 library_type 、 metadata_plugins 等）
  - 把这些字段交给公共构造函数，获取标准化的 LibraryCreate （含默认值和上下文字段）
- 禁止在 Agent 工具里手写一套和路由“长得差不多但不完全一样”的构造逻辑：
  - 尤其是涉及：
    - 枚举类型（ LibraryType ）
    - 默认路径（ root_path ）
    - 上下文字段（ user_id 、 activated_plugins 、租户信息等）
**目的：**保证今后你只要改 HTTP 路由的创建逻辑（比如默认 root_path 从 "temp" 改成别的），Agent 工具会自动跟着变，不会出现“HTTP 路径没问题，Agent 路径有严重 BUG”的情况。

四、模型与数据库数据的一致性排查

针对这次 root_path 报错类问题，建议对所有 InDB 模型做一次数据库自检：
PASS，已经人工核验完成，删除了受影响的数据

五、参数映射与默认值的统一检查

从这次问题抽象出一组通用检查项，可以对所有 Agent 工具使用：

- Tool 的 args_schema 字段名是否与业务模型字段名不同？若不同：
  - 是否有显式的「映射层」把 Tool 参数转换成业务模型字段？
- 对枚举字段（如 LibraryType ）：
  - Tool 提供的是字符串（'movie' / 'tv'），业务模型使用 Enum，是否进行了 LibraryType(value) 的转换？
- 对默认值：
  - 所有默认值是否在 一个地方 定义（比如路由层或公共构造函数）？
  - 服务层兜底逻辑是否对 None 情况真正生效（避免 setdefault + model_dump() 把 None 写死进去）？
    - 例如考虑用： model_dump(exclude_unset=True) + 手工补字段
- 对用户上下文字段（ user_id 、 tenant_id 等）：
  - Agent 工具是否统一从 runtime.context 里取 current_user，再走与 HTTP 路由完全一致的注入方式？
六、测试与回归验证清单

最后是如何验证这些排查/修改不再出问题：

- 单元测试 / 集成测试
  
  - 为每一个 Agent 工具编写测试，模拟：
    - 构造 Tool 输入参数
    - 构造伪造的 runtime.context["user"]
    - 调用工具函数
  - 在测试中断言：
    - 服务层收到的模型与 HTTP 路由路径下构造出的模型相同（可以比较 .model_dump() ）
    - 对应集合中写入的文档不包含必填字段为 null / 缺失的情况
- 一致性测试
  
  - 对每个创建动作，编写对比测试：
    - 用 HTTP 创建一次
    - 用 Agent 工具创建一次
    - 比较两条文档在 Mongo 中的字段（除了 id / 时间戳等）
    - 确保它们在业务字段上完全一致
- 回归验证
  
  - 清理或修复已有坏数据（如 root_path: null ），再跑一轮 list_* 或相关查询，确认不再出现 InDB 校验错误