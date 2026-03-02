```
├── api/                  # API 接口层
│   ├── movies_routers/   # 电影相关接口
│   │   ├── movies.py     # 核心元数据
│   │   ├── assets.py     # 多源资源、版本管理
│   │   └── libraries.py  # 媒体库配置
│   ├── users_routers/    # 用户相关接口
│   │   ├── users.py
│   │   ├── user_assets.py
│   │   └── watch_history.py
│   ├── tasks_routers/    # 任务接口
│   │   └── tasks.py
│   └── logs_routers/     # 系统日志接口
│       └── logs.py
```

明白了，你希望从 **专业后端开发视角** ，按**资源/模块（movies、users、tasks、assets…）而非前端页面**来组织接口，这样更符合 RESTful 设计、也方便权限和复用。下面我帮你重新梳理：

---

# **Lotus-DB 后端接口设计（按资源模块）**

## **1. Movies 模块（影片资源）**

 **职责** ：管理影片信息、官方/用户资产、LLM信息

 **接口设计** ：

| 方法   | 路径                                         | 描述                                         |
| ------ | -------------------------------------------- | -------------------------------------------- |
| GET    | `/api/movies`                              | 影片列表（分页 + 筛选 + 排序）               |
| POST   | `/api/movies`                              | 新建影片（可选：批量导入）                   |
| GET    | `/api/movies/{movie_id}`                   | 获取影片详细信息                             |
| PATCH  | `/api/movies/{movie_id}`                   | 编辑影片信息                                 |
| DELETE | `/api/movies/{movie_id}`                   | 删除影片                                     |
| GET    | `/api/movies/{movie_id}/assets`            | 获取影片所有资产（视频、图片、字幕、笔记等） |
| POST   | `/api/movies/{movie_id}/assets`            | 上传资产                                     |
| PATCH  | `/api/movies/{movie_id}/assets/{asset_id}` | 编辑资产信息                                 |
| DELETE | `/api/movies/{movie_id}/assets/{asset_id}` | 删除资产                                     |
| POST   | `/api/movies/{movie_id}/llm-info`          | 调用 LLM 获取影片或官方资产信息              |
| POST   | `/api/movies/batch-update`                 | 批量更新影片信息                             |
| POST   | `/api/movies/batch-delete`                 | 批量删除影片                                 |

---

## **2. Assets 模块（用户资产）**

 **职责** ：管理用户个人资产（截图、笔记、剪辑）

 **接口设计** ：

| 方法   | 路径                       | 描述                            |
| ------ | -------------------------- | ------------------------------- |
| GET    | `/api/assets`            | 用户资产列表（分页 + 类型筛选） |
| GET    | `/api/assets/{asset_id}` | 获取资产详情                    |
| POST   | `/api/assets`            | 上传用户资产                    |
| PATCH  | `/api/assets/{asset_id}` | 编辑资产信息                    |
| DELETE | `/api/assets/{asset_id}` | 删除资产                        |

---

## **3. Collections 模块（用户自定义合集）**

 **职责** ：管理用户自定义合集

 **接口设计** ：

| 方法   | 路径                                            | 描述             |
| ------ | ----------------------------------------------- | ---------------- |
| GET    | `/api/collections`                            | 获取用户合集列表 |
| GET    | `/api/collections/{collection_id}`            | 获取合集详情     |
| POST   | `/api/collections`                            | 创建合集         |
| PATCH  | `/api/collections/{collection_id}`            | 修改合集         |
| DELETE | `/api/collections/{collection_id}`            | 删除合集         |
| POST   | `/api/collections/{collection_id}/add-movies` | 批量加入影片     |

---

## **4. Users 模块（用户管理）**

 **职责** ：用户信息、角色与权限管理

 **接口设计** ：

| 方法   | 路径                          | 描述                |
| ------ | ----------------------------- | ------------------- |
| GET    | `/api/users`                | 获取用户列表        |
| GET    | `/api/users/{user_id}`      | 获取用户详情        |
| POST   | `/api/users`                | 创建用户 / 邀请用户 |
| PATCH  | `/api/users/{user_id}`      | 编辑用户信息        |
| PATCH  | `/api/users/{user_id}/role` | 设置角色权限        |
| DELETE | `/api/users/{user_id}`      | 删除用户            |

---

## **5. Tasks 模块（后台任务）**

 **职责** ：批量导入、元数据抓取、转码等耗时任务管理

 **接口设计** ：

| 方法 | 路径                              | 描述                            |
| ---- | --------------------------------- | ------------------------------- |
| GET  | `/api/tasks`                    | 获取任务列表（分页 + 状态筛选） |
| GET  | `/api/tasks/{task_id}`          | 获取任务详情                    |
| POST | `/api/tasks/{task_id}/cancel`   | 取消任务                        |
| GET  | `/api/tasks/{task_id}/progress` | 获取实时进度                    |

---

## **6. Notes 模块（笔记/书签）**

 **职责** ：Markdown笔记、快速书签、与影片或资产关联

 **接口设计** ：

| 方法   | 路径                     | 描述                            |
| ------ | ------------------------ | ------------------------------- |
| GET    | `/api/notes`           | 获取笔记列表（分页 + 类型筛选） |
| GET    | `/api/notes/{note_id}` | 获取笔记详情                    |
| POST   | `/api/notes`           | 创建笔记                        |
| PATCH  | `/api/notes/{note_id}` | 编辑笔记                        |
| DELETE | `/api/notes/{note_id}` | 删除笔记                        |
| POST   | `/api/notes/assets`    | 插入影片截图/用户资产           |

---

## **7. MediaStudio 模块（视频/图像处理）**

 **职责** ：轻量化剪辑、图像处理、AI增强

 **接口设计** ：

| 方法 | 路径                                | 描述       |
| ---- | ----------------------------------- | ---------- |
| POST | `/api/media/studio/clip`          | 视频剪辑   |
| POST | `/api/media/studio/process-image` | 图像处理   |
| POST | `/api/media/studio/batch`         | 批量处理   |
| POST | `/api/media/studio/ai-enhance`    | AI增强处理 |

---

## **8. System 模块（系统状态 & 配置）**

 **职责** ：系统监控、配置管理、Settings管理

 **接口设计** ：

| 方法    | 路径                       | 描述                          |
| ------- | -------------------------- | ----------------------------- |
| GET     | `/api/system/status`     | 系统资源状态（CPU/内存/存储） |
| GET     | `/api/system/health`     | API接口健康状态               |
| GET     | `/api/system/db`         | 数据库连接状态                |
| GET/PUT | `/api/settings/system`   | 系统配置                      |
| GET/PUT | `/api/settings/theme`    | 界面主题                      |
| GET/PUT | `/api/settings/playback` | 播放器设置                    |
| GET/PUT | `/api/settings/storage`  | 存储路径                      |
| GET/PUT | `/api/settings/database` | 数据库配置                    |
| GET/PUT | `/api/settings/models`   | LLM/Embedding模型选择         |

---

## **9. Player 模块（播放与交互）**

 **职责** ：视频播放、截图、滤镜、书签/笔记、转码

 **接口设计** ：

| 方法 | 路径                                  | 描述                                   |
| ---- | ------------------------------------- | -------------------------------------- |
| GET  | `/api/player/{movie_id}/stream`     | 获取视频播放地址（支持转码/倍速/片段） |
| POST | `/api/player/{movie_id}/screenshot` | 截图保存为用户资产                     |
| POST | `/api/player/{movie_id}/filter`     | 视频滤镜处理                           |
| POST | `/api/player/{movie_id}/bookmark`   | 添加/编辑/删除书签或快速笔记           |

---

### ✅ **总结专业设计要点**

1. **以资源为中心** ：每个模块对应核心资源（movies、assets、users、tasks…），接口和功能都围绕资源进行 CRUD + 批量 + 任务操作。
2. **统一接口风格** ：RESTful + 分页/筛选/排序 + 批量操作。
3. **异步任务支持** ：长耗时操作都返回 Task ID，前端可轮询进度。
4. **权限分层** ：Admin/User/普通用户可通过 Router 或 Depends 统一控制。
5. **扩展性** ：MediaStudio、Notes、Player 模块可以独立扩展，不影响核心电影资源接口。
6. **路由层不直接捕获业务异常，也不主动记录日志** ，而是依赖全局异常中间件 + service 层日志。
   路由层只负责参数绑定与调用。

---

如果你愿意，我可以帮你画一个  **Lotus-DB 后端资源模块接口图** ，展示各模块之间的关联（如 movies→assets、movies→notes、tasks→movies），形成完整的开发蓝图。

你希望我画吗？
