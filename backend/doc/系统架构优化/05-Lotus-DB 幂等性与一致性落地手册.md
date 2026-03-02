Lotus-DB 幂等性与一致性落地手册（按当前代码现状定制）

目标与范围

- 目标：在“客户端重试 / 多 Worker / 异步任务重试 / 缓存写回”场景下，保证不重复写、不乱序覆盖、状态机不串台，并在失败后可安全重放。
- 范围：FastAPI API 调用链（Router/Service/Logic/Repo）、Redis Streams 异步 Worker、MongoDB 数据一致性、Redis 缓存与写回。
## 1) 现状速览（从代码读到的真实行为）
- 请求链路 ：TraceId 中间件已存在（ middleware.py ），Router 装饰器做统一日志但不做幂等（ handler.py ）。
- 异步任务 ：Redis Streams + consumer group，失败会 xack 原消息并 xadd 新消息进行重试（因此同一业务任务可能被执行多次，且 msg_id 变了）（ async_worker/core.py ）。
- Mongo 索引 ：连接时会创建部分集合索引（ mongo_db.py ），但存在明显“集合名不匹配导致索引根本没建上”的风险点：
  - 代码里观看历史 Repo 用的是 watch_histories （ watch_history_repo.py ），但索引创建用的是 watch_history （单数）（ mongo_db.py ）。这会直接让“唯一约束/查询加速”失效。
  - user_custom_lists （ user_custom_list_repo.py ）没有任何索引创建逻辑覆盖。
- 任务状态机 ：TaskLogic 有状态转移校验，但实现是“先读再写”的非原子模式（ task_logic.py ），遇到重复消费/并发更新时容易出现“两个执行者都通过校验然后都写成功”的竞态。
- 片单追加/删除电影 ： append_movies/remove_movies 是读-改-写，天然存在并发丢更新风险（ collection_logic.py ）。
- 观看历史创建 ：同样是先 exists 再 insert ，且按 user_id+asset_id 查重（ watch_history_logic.py ），一旦并发/重试就会重复写；而且没有索引兜底时更危险。
- “脏集合写回”任务 ：Worker/Celery 都在调用 CollectionLogic.sync_dirty_collections_from_cache() ，但当前 logic 里没有这个方法实现（会导致任务必失败+重试风暴）（ async_worker/tasks/collection_sync_task.py ， collection_logic.py ）。
## 2) 风险地图：哪些业务最需要幂等/一致性
按“重复执行的破坏性”从高到低：

- 任务系统（高） ：重复消费/重试会导致同一 task_id 的状态被多次切换、结果被覆盖、甚至重复触发外部副作用。
  - 典型：电影批量导入任务（ movie_import_task.py ）包含 DB 写入 + 外部下载 + 文件写入，必须可安全重放。
- 片单增删（高） ：并发下读改写会丢数据（A 加入、B 删除、最后写回覆盖）。
- 观看历史（高） ：播放端上报常有乱序/重试；如果不做“单调更新”（例如 last_position 只能增加）会出现进度回退。
- 索引/唯一约束缺失（高） ：即使业务层做了 exists 检查，并发下也挡不住重复；必须靠 Mongo 唯一索引做最后一道防线。
- 库结构迁移/清理（中） ：文件操作副作用大，重放需要显式检查“是否已完成/是否已迁移”。
- 普通 CRUD（低） ：GET/列表天然幂等；简单 update 若用 $set 且字段可重复覆盖，一般问题较小。
## 3) 方案适配评估：文档里的“幂等/一致性工具箱”在本项目怎么选
推荐优先级（从“强约束+低复杂度”到“增强体验”）

- 第 0 层：让写操作本身原子化（Mongo update operators）
  - 适用：片单 add/remove、观看历史进度、计数器等。
  - 优点：不依赖 Redis，不引入新状态；并发安全。
- 第 1 层：Mongo 唯一索引 + DuplicateKey 处理
  - 适用：创建类接口（创建观看历史、创建默认片单、创建电影等）。
  - 优点：最可靠的幂等兜底；可把“重试”变成“返回已存在资源”。
  - 前提：索引必须真的建在正确集合上（目前 watch_history 存在明显问题）。
- 第 2 层：任务状态 CAS（Compare-And-Set）
  - 适用：TaskStatus 迁移必须原子，防止重复 worker 同时 start/complete。
  - 关键：用 find_one_and_update 加上 {"_id":..., "status": expected} 过滤。
- 第 3 层：API Idempotency-Key（Redis/DB）
  - 适用：创建任务、批量导入、涉及外部下载/文件写等“高成本副作用”接口。
  - 建议：只对少数高风险 POST/PUT 开启，不要全局强推（会增加维护与存储成本）。
- 第 4 层：Worker 侧去重/锁
  - 适用：Redis Streams 的“失败后重投递”模型下，同一 task_id 的并发执行要互斥。
  - 手段：基于 task_id 做 Redis SET key value NX EX 锁，或者把互斥做进 TaskStatus CAS（更推荐）。
## 4) 受影响代码清单（按优先级排序）
P0：必须先修（否则幂等方案无根）

- Mongo 索引创建的集合名与实际 Repo 集合名对齐
  - 索引创建： mongo_db.py
  - 观看历史集合名： watch_history_repo.py
  - 片单集合名： user_custom_list_repo.py
P0：任务状态机原子化（CAS）

- TaskLogic 的 _update_task_status/start_task/complete_task/fail_task （ task_logic.py ）
- Worker 重试机制会导致同一业务 task 重复执行（ async_worker/core.py ）
P0：片单增删改为原子操作

- append_movies/remove_movies 需要 $addToSet/$pull （ collection_logic.py ）
P0：观看历史改为“upsert + 单调更新”

- create_watch_history/update_watch_history （ watch_history_logic.py ）
P1：高成本任务幂等化

- 批量导入电影任务：需要“重复执行不重复创建电影、不重复下载/写文件、不重复覆盖错误结果”（ movie_import_task.py ）
- 库结构迁移/清理：需要检查是否已迁移/已删除（ library_migration_task.py ）
P1：API 层 Idempotency-Key（只加在少数端点）

- 入口建议放在中间件（ middleware.py ）或 Router 装饰器层（ handler.py ）。
P1：脏集合写回缺失实现（否则“最终一致性”无法成立）

- 调用方在 async_worker/tasks/collection_sync_task.py
- 但 logic 当前无实现： collection_logic.py
## 5) 可执行实现模板（贴合当前架构）
### 5.1 任务状态 CAS（推荐：把“幂等”钉死在 TaskStatus 上）
核心思想：把“校验 current_status + 更新”变成一次 Mongo 原子操作。

```
from bson import ObjectId
from datetime import datetime, timezone
from pymongo import ReturnDocument

async def transition_task_status(collection, task_id: str, expected: str, to: 
str, extra_set: dict):
    now = datetime.now(timezone.utc)
    update = {"$set": {"status": to, **extra_set, "updated_at": now}}
    doc = await collection.find_one_and_update(
        {"_id": ObjectId(task_id), "status": expected},
        update,
        return_document=ReturnDocument.AFTER,
    )
    return doc
```
落地方式（建议）：

- TaskLogic.start_task ：expected=PENDING -> RUNNING；失败则说明“已经被别的 worker 启动/完成”，直接当幂等成功返回当前任务即可。
- complete_task/fail_task ：expected=RUNNING -> COMPLETED/FAILED；如果失败则不覆盖（避免重复执行把已完成任务改回失败）。
### 5.2 片单增删：用 $addToSet / $pull 替代读改写
```
from bson import ObjectId

async def add_movies(repo_collection, collection_id: str, movie_ids: list[str]):
    await repo_collection.update_one(
        {"_id": ObjectId(collection_id)},
        {"$addToSet": {"movies": {"$each": [ObjectId(x) for x in movie_ids]}}},
    )

async def remove_movies(repo_collection, collection_id: str, movie_ids: list
[str]):
    await repo_collection.update_one(
        {"_id": ObjectId(collection_id)},
        {"$pull": {"movies": {"$in": [ObjectId(x) for x in movie_ids]}}},
    )
```
这样天然满足：

- 重试同一请求不重复添加（幂等）。
- 并发 add/remove 不会丢更新（原子）。
### 5.3 观看历史：Upsert + 单调字段（抗乱序/重试）
推荐唯一键： (user_id, asset_id, type) （因为你在逻辑里就是按这三个维度查询）（见 watch_history_logic.py ）。

```
from bson import ObjectId
from datetime import datetime, timezone

async def upsert_watch_progress(collection, user_id: str, asset_id: str, 
type_value: str, patch: dict):
    now = datetime.now(timezone.utc)
    await collection.update_one(
        {"user_id": ObjectId(user_id), "asset_id": ObjectId(asset_id), "type": 
        type_value},
        {
            "$setOnInsert": {
                "user_id": ObjectId(user_id),
                "asset_id": ObjectId(asset_id),
                "type": type_value,
                "created_at": now,
            },
            "$set": {
                "last_watched": now,
                **{k: v for k, v in patch.items() if k not in ("last_position", 
                "watch_count")},
            },
            "$max": {"last_position": patch.get("last_position", 0)},
            "$inc": {"watch_count": int(patch.get("inc_watch", 0))},
        },
        upsert=True,
    )
```
要点：

- last_position 用 $max 保证不回退（乱序安全）。
- 计数用 $inc ，不要读出来再加 1。
### 5.4 API Idempotency-Key（仅针对少数高风险写接口）
推荐协议：

- 客户端传 Idempotency-Key （随机 UUID）。
- 服务端用 Redis SET key NX EX ：首次处理占位；成功后把响应摘要写入同 key；重复请求直接返回缓存响应。
简化流程（伪代码）：

```
key = f"idemp:{user_id}:{request.method}:{request.url.path}:{idem_key}"
if redis.get(key + ":done"):
    return cached_response
if not redis.set(key + ":lock", "1", nx=True, ex=60):
    return 409/425  # 表示正在处理中
try:
    resp = await handler()
    redis.set(key + ":done", json(resp), ex=600)
    return resp
finally:
    redis.delete(key + ":lock")
```
适用端点建议：

- 创建任务/批量导入入口（会触发 send_task ）。
- 上传/下载触发类、库迁移触发类。
## 6) 测试用例与验证方法（基于现有 pytest 体系）
项目已配置 pytest（ pytest.ini ），且已有逻辑/Repo/路由测试目录（ tests/logic , tests/repos , tests/routers ）。

### 6.1 并发幂等测试：TaskStatus CAS（应新增/强化到 tests/logic/test_task_logic.py）
测试目标：

- 两个并发 start_task(task_id) 只能有一个成功把状态从 PENDING 改到 RUNNING。
- 并发 complete_task 不应覆盖已完成结果。
示例（思路级，贴近 asyncio）：

```
import asyncio
import pytest

@pytest.mark.asyncio
async def test_task_start_is_cas(task_logic, task_id):
    async def call():
        try:
            return await task_logic.start_task(task_id)
        except Exception as e:
            return e

    r1, r2 = await asyncio.gather(call(), call())
    # 断言：至少一个成功；另一个要么报状态不匹配，要么返回“已启动”的等价结果（按你落地策略定）
```
### 6.2 片单 add/remove 幂等：不会重复、不会丢更新（tests/logic/test_collection_logic.py）
测试目标：

- 同一 movie_id 重试 append 不产生重复元素。
- append 与 remove 并发执行后 movies 集合满足集合语义（至少不出现重复、且不会被整段覆盖回旧值）。
### 6.3 观看历史乱序上报：进度不回退（tests/logic/test_watch_history_logic.py）
测试目标：

- 先上报 last_position=100，再上报 last_position=50，最终仍应为 100（如果采用 $max ）。
### 6.4 索引验证（集成测试 / 启动时检查）
测试目标：

- 启动后 watch_histories 集合存在唯一索引 (user_id, asset_id, type) （或你选定的键）。
- user_custom_lists 至少有 (user_id, type) 唯一约束（用于默认片单），以及 (user_id, name) 唯一约束（用于自定义片单名）。
### 6.5 手工验证（API 层）
- 重试验证 ：对同一个高风险 POST 携带相同 Idempotency-Key 连续打 2 次，应返回相同结果且只产生一次副作用（只创建 1 条任务/1 次写入）。
- Worker 重试验证 ：人为让 task 函数中途抛异常，确认重试后不会重复创建 DB 记录/重复写文件（以 task_id/状态机或锁为幂等锚点）。
## 7) 一句话落地策略（推荐你按这个顺序做）
- 先把 索引建对 （集合名对齐 + 补齐 user_custom_lists/watch_histories 的唯一索引），再把 TaskStatus 做成 CAS ，随后把 片单/观看历史从读改写改成原子更新 ，最后只对少数高风险端点加 Idempotency-Key 。
如果你下一步希望我直接在仓库里把这些改造按 P0→P1 落地（含对应测试更新与跑测命令），我会从“修复索引集合名不匹配 + TaskStatus CAS”开始做。