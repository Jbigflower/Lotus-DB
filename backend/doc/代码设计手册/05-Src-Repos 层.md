```
├── repos/                # 仓储层（数据库操作封装）
│   ├── mongo_repos/      # MongoDB 仓储
│   │   ├── base_repo.py  # 核心文件，其余 mongo-repo 会继承其
│   │   ├── movie_repo.py
│   │   ├── asset_repo.py
│   │   ├── library_repo.py
│   │   ├── user_repo.py
│   │   ├── user_asset_repo.py
│   │   ├── watch_history_repo.py
│   │   ├── task_repo.py
│   │   └── log_repo.py
│   ├── embedding_repos/     # Chroma 仓储
│   │   └── chroma_repo.py
│   └── cache_repos/      # Redis 仓储
│       └── redis_repo.py
```

## 一、整体思路

`mongo_repos`:

rpos 层的主要职责是 **封装实体级的数据访问逻辑**，即：

- CRUD（Create / Read / Update / Delete）操作
- 高级查询与过滤
- 聚合、索引、分页、排序等数据库操作
- 数据库实体和业务逻辑的桥梁（调用 DB 层提供的 client/connection）

> ⚠️ 注意：Repos 层只关注 **数据操作**，不处理业务逻辑、缓存策略或接口响应，这些由 Service 层处理。

---

`chroma_repos`

封装向量操作接口：插入、更新、删除、批量操作、检索。保持与 Mongo 数据同步策略接口（但不做业务逻辑）

---

`redis_repos`

redis_base_repo.py ：提供统一、可复用的缓存操作接口，但不涉及具体业务规则，比如：

```
RedisBaseRepo
├─ get(key: str) -> Optional[Any]       # 获取缓存
├─ set(key: str, value: Any, expire: int = None)  # 设置缓存
├─ delete(key: str)                     # 删除缓存
├─ exists(key: str) -> bool             # 判断是否存在
├─ incr(key: str, amount: int = 1)      # 自增（计数器）
├─ decr(key: str, amount: int = 1)      # 自减
```

**特点**：

- 仅封装 Redis API 调用
- 可处理 JSON 序列化/反序列化
- 统一异常捕获与日志记录

## 二、`mongo_repos/Base-repo`

- 提供基础 CRUD 接口，例如

```Base-repo
├─ insert_one(obj: BaseModel)
├─ insert_many(objs: list[BaseModel])
├─ find_one(filter: dict)
├─ find_many(filter: dict, skip: int, limit: int, sort: list)
├─ update_one(filter: dict, update: dict)
├─ update_bulk(filter: dict, update: dict)
├─ delete_one(filter: dict)
├─ delete_many(filter: dict)
├─ restore_one(filter: dict)
├─ restore_many(filter: dict)
```

- 功能增强：
  - **统一输入输出**：自动 `_id <-> id` 转换，Pydantic ↔ MongoDB 文档
  - 统一的日志 & 异常 处理
  - **软删除**：`is_deleted`，支持恢复
  - **引用完整性检查（可选）**
  - **级联操作（可选）**
  - **事务封装**
  - 批量更新 / 插入不同内容支持

## 三、设计原则

- **单实体单文件**

  - 每个 Repo 对应一张表或一类业务对象
  - 例如 `movie_repo.py` 只操作 `movies` 集合
- 在mongo-repo中，**继承 BaseRepo**

  - BaseRepo 提供通用方法，统一的数据转换，统一的异常和日志处理 .etc
  - 避免重复代码
- **依赖 DB 层**

  - MongoRepo 使用 `mongo.get_db()` 获取集合
  - ChromaRepo 使用 `chroma.get_client()`
  - ……
- **依赖 Model 层**

  - 建议数据操作使用 Model 层提供的 `InDB`、`Update` 等 BaseModel 进行格式验证。
  - **禁止直接修改 Models 层的基础字段**，例如不要随意修改 `xxxInDB`。如确实需要新增字段或修改结构，必须在工作区提交申请文档（一般在 `doc-llm` 生成），经架构师审批同意后方可执行。
  - **禁止虚构 Models 层未定义的字段**，或为其随意实现方法。所有字段必须与 Models 层一致，以确保数据一致性和系统可靠性。
- **异步支持**

  - 尽量使用异步接口（MongoDB `motor`, Redis `aioredis`），保证高并发
  - 明确界限，如果一个操作是 Cpu 密集型任务，提供 同步接口
- **封装聚合 / 高级查询**

  - Repo 层可封装复杂查询逻辑，例如：

    - 根据用户 ID 查询收藏的电影列表
    - 根据电影类型和评分区间查询分页结果
  - 方便 Service 层直接调用
- **返回 Pydantic 模型**

  - 所有查询结果都应转换为对应的 `InDB` 或 `DTO` 模型
  - 避免 Service 或 Router 层直接处理原始字典
  - 如果所需的 pydantic 模型没有在 Models 层定义，请在新建 或者 在合适的文件中追加定义，不过注意普适性。
  - 严令禁止修改 Models 层的基础字段，如 InDB，如果当前确实需要添加，请在工作区，一般是 doc-llm 编写申请文档，待架构师同意后，才进行修改。
