# Lotus-DB MongoDB → LanceDB 同步机制设计文档

## 1. 设计目标

在 Lotus-DB 中实现 **MongoDB 数据库与 LanceDB 向量数据库**的自动同步，保证：

1. 电影、笔记、字幕等多种数据源在 LanceDB 中保持最新状态
2. 支持 **细粒度字段同步和类型过滤**
3. 支持 **异步、批量化、软删除/硬删除**
4. 可扩展为更多集合和自定义同步逻辑

---

## 2. 同步层级设计

| 层级                 | 职责                                                     | 同步逻辑位置                                                               |
| -------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------- |
| **Repo 层**    | 提供数据操作接口（增删改查、向量化、批量 upsert/delete） | **不直接处理跨库同步**                                               |
| **Service 层** | 业务逻辑层，整合 Repo、缓存、异步任务等                  | **实现同步逻辑** （监听 MongoDB 变更 → 调用对应 Repo 更新 LanceDB） |

 **理由** ：

* Repo 层只做单一职责（CRUD + 向量化）
* Service 层负责跨库同步、批量化处理、异常重试和日志记录

---

## 3. MongoDB ChangeStream 机制

### a. 基本概念

* `collection.watch(pipeline, full_document='updateLookup')`
* `operationType`：`insert`, `update`, `replace`, `delete`
* `fullDocument`：更新后的完整文档（可选 `updateLookup`）

### b. 事件过滤示例

* 只监听笔记类型：

<pre class="overflow-visible!" data-start="838" data-end="1050"><div class="contain-inline-size rounded-2xl relative bg-token-sidebar-surface-primary"><div class="sticky top-9"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre! language-python"><span><span>pipeline = [
    {</span><span>"$match"</span><span>: {</span><span>"fullDocument.type"</span><span>: </span><span>"笔记"</span><span>}}
]
</span><span>async</span><span></span><span>with</span><span> user_assets_collection.watch(pipeline, full_document=</span><span>'updateLookup'</span><span>) </span><span>as</span><span> stream:
    </span><span>async</span><span></span><span>for</span><span> change </span><span>in</span><span> stream:
        </span><span># 处理笔记事件</span><span>
</span></span></code></div></div></pre>

* 支持字幕、电影或其他类型类似处理

---

## 4. 多表同步策略

| LanceDB 表 | MongoDB 集合 | 变更条件       | 同步动作                       |
| ---------- | ------------ | -------------- | ------------------------------ |
| movies     | movies       | 插入/更新/删除 | upsert/delete（软删除/硬删除） |
| notes      | user_assets  | type = "笔记"  | upsert/delete                  |
| subtitles  | user_assets  | type = "字幕"  | upsert/delete                  |

### a. 字段映射

* MongoDB 字段可以与 LanceDB 字段不完全一致
* 在  **Service 层做字段转换** ：
  * MovieInDB → LanceDB 电影表
  * NoteInDB → LanceDB 笔记表
  * AssetInDB → LanceDB 字幕表

### b. 插入/更新/删除映射

| MongoDB operationType     | LanceDB 操作            |
| ------------------------- | ----------------------- |
| insert / replace / update | upsert()                |
| delete                    | delete(soft=True/False) |

---

## 5. 异步批量化处理

* **批量构建文本描述 → 异步生成 embedding → 批量 upsert**
* 可使用现有 `iter_get_text_embedding` 接口
* 提升性能，降低单条操作开销

---

## 6. 软件架构示意

<pre class="overflow-visible!" data-start="1824" data-end="2058"><div class="contain-inline-size rounded-2xl relative bg-token-sidebar-surface-primary"><div class="sticky top-9"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre! language-text"><span><span>MongoDB ChangeStream
       │
       ▼
  MongoToLanceSync (Service 层)
       │
       ├─ MovieEmbeddingRepo
       ├─ NoteEmbeddingRepo
       └─ SubtitleEmbeddingRepo
       │
       ▼
  LanceDB 向量存储 (异步、批量 upsert/delete)
</span></span></code></div></div></pre>

* 每个 Repo 提供标准接口：`upsert(objs: List[T])`, `delete(ids: List[str], soft=True)`
* Service 层处理：
  * 类型过滤（type）
  * 字段映射
  * 异步批量
  * 异常日志

---

## 7. 实现注意事项

1. **初始化** ：

* Repo 层初始化 LanceDB 表
* Service 层启动 ChangeStream 监听

1. **批量处理** ：

* 可 accumulate N 条变更再一次 upsert
* 避免每条变更单独调用向量化接口

1. **错误重试** ：

* 网络异常或 embedding 超时需重试
* 记录失败事件日志

1. **软删除** ：

* 保持 `_is_deleted` 字段
* 避免删除历史数据

1. **细粒度控制** ：

* 利用 ChangeStream pipeline match
* 可按字段、类型、集合进行过滤

1. **性能优化** ：

* 异步批量 embedding
* 按集合单独启动监听任务
* LanceDB 支持批量 upsert / search / delete

---

## 8. 扩展与可维护性

* 新集合或类型：
  * 新增 Repo
  * 在 MongoToLanceSync 注册 changeStream
* 支持自定义过滤条件或字段映射
* 与现有 FastAPI 启动/关闭事件挂钩，确保同步器随服务启动
