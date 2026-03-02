## 1️⃣ Celery 在 Lotus-DB 的定位

在个人媒体管理系统中，Celery 常用于：

1. **后台异步任务**
   * 批量导入电影、笔记、字幕
   * 媒体文件处理（截图、转码、压缩）
   * 向量化处理（调用 OpenAI / Ollama 生成 embeddings）
   * 数据同步（MongoDB ↔ FAISS / Redis）
2. **定时任务 / 周期性任务**
   * 数据统计与分析（播放量、标签热度）
   * 缓存刷新
   * 自动化通知 / 提醒
3. **任务状态管理**
   * 支持任务进度查询
   * 错误重试 / 异常捕获
   * 支持前端实时反馈（配合 Redis 或数据库存储任务状态）

---

## 2️⃣ 各层职责分析

| 层级                                             | Celery 职责                               | 开发者实现内容                                                                                                                             |
| ------------------------------------------------ | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Router（FastAPI 路由层）**               | 接收用户请求触发异步任务                  | - 提供触发任务的接口，如 `/import_movies`、`/generate_embeddings` ``- 返回 Celery task_id 或状态信息给前端                      |
| **Service（业务逻辑层）**                  | 封装业务逻辑，将同步操作拆解为任务提交    | - 根据请求生成 Celery 任务``- 可组合多个任务（链式 / 分组 / 回调）``- 定义任务输入参数和处理逻辑的上下文                     |
| **Repo（仓储层）**                         | 任务相关数据操作（Mongo / FAISS / Redis） | - 处理任务涉及的数据 CRUD``- 提供任务结果存储接口（如导入结果、处理后的向量数据）``- 可结合 Redis 保存临时进度               |
| **DB（Celery Worker / Broker / Backend）** | 执行异步任务，管理消息队列和结果存储      | - Celery Worker 执行实际任务函数``- Broker（Redis / RabbitMQ）分发消息``- Backend（Redis / MongoDB / RDB）保存任务状态和结果 |

---

## 3️⃣ 开发者需要实现的 Celery 功能清单

### 3.1 Celery 配置

* Broker 选择（推荐 Redis，已在 Lotus-DB 使用）
* Backend 选择（保存任务结果）
* Worker 配置（并发数、队列、任务超时）
* 重试策略、异常捕获

### 3.2 任务定义

* 异步任务函数（@celery.task）
* 支持任务链、组、回调
* 异常处理与日志记录

### 3.3 任务触发

* Service 层调用 apply_async 或 delay 提交任务
* 支持任务参数序列化
* 返回 task_id 给前端

### 3.4 任务状态管理

* 前端轮询 / WebSocket 获取任务状态
* 可存储任务进度到 Redis 或 MongoDB
* 支持任务取消 / 超时处理

### 3.5 任务结果处理

* 成功结果写入 MongoDB / FAISS / Redis
* 异常或失败记录日志
* 可触发通知（邮件 / Telegram / 本地消息）

---

## 4️⃣ 调用链示意（文字版）

<pre class="overflow-visible!" data-start="1578" data-end="1744"><div class="contain-inline-size rounded-2xl relative bg-token-sidebar-surface-primary"><div class="sticky top-9"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre! language-text"><span><span>[前端请求] --> Router --> Service --> Repo --> Celery.apply_async --> Broker --> Worker --> 执行任务 --> Backend保存状态
             <-- Router返回task_id --> 前端轮询任务状态
</span></span></code></div></div></pre>

* **Router** ：只负责任务提交接口
* **Service** ：封装业务逻辑 + 任务生成
* **Repo** ：提供数据读写接口（MongoDB/FAISS/Redis）
* **Worker** ：执行异步任务，写回数据和状态
* **Broker/Backend** ：管理队列和任务结果
