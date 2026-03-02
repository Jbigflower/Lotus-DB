```
├── services/             # 业务逻辑层（解耦 API 与 Repos）
│   ├── movies/
│   │   ├── movie_service.py
│   │   ├── asset_service.py
│   │   └── library_service.py
│   ├── users/
│   │   ├── user_service.py
│   │   ├── user_asset_service.py
│   │   └── watch_history_service.py
│   ├── tasks/
│   │   └── task_service.py
│   └── logs/
│       └── log_service.py
```

## 一、整体思路

- **职责单一**：Service 层只处理业务逻辑，不直接依赖前端，也不处理 HTTP 请求/响应。
- **Repo 调用**：所有数据访问操作通过 Repo 层完成。Service 层负责业务聚合、缓存策略、权限控制、任务触发等。且服务层可以组合多个 Repo 或 外部客户端。
- **异步/同步**：尽量使用异步接口处理高并发IO请求，例如批量查询、向量检索、任务队列。
- **统一返回**：Service 层返回标准化数据模型（Pydantic DTO），供 Router 层直接使用。
- 事务一致性：跨多个 Repo 操作时，Service 层负责保证事务一致性。
- **可扩展**：支持 LLM、Agent 调用、异步任务、缓存等插件式扩展。
- 粗细粒度：**粗粒度**：对外暴露给 Router/Controller 的方法，通常是一个业务动作；**细粒度**：内部可拆分为多个私有方法，用于复用和逻辑拆分。

## Movies 相关服务

### **movie_service.py**

- **核心职责**：处理电影元数据业务逻辑
    
- **功能示例**：
    
    - 创建/更新/删除电影元数据
    - 检查重复电影（基于 title/release_data）
    - 聚合查询电影信息（如带资源、评分、向量等）
    - 触发异步任务（生成 embedding、抓取封面）
    - 与 Chroma 同步向量索引
        
- **方法示例**：
    
    `create_movie_with_assets(movie_data, assets) get_movie_detail(movie_id) update_movie(movie_id, data) delete_movie(movie_id) search_movies_advanced(filters)`
    

### **asset_service.py**

- **核心职责**：管理多源资源、版本控制、衍生资源
    
- **功能示例**：
    - 为电影添加/更新/删除资源
    - 校验资源唯一性（movie_id + path）
    - 生成资源缩略图、视频转码等异步任务
    - 聚合资源信息给前端展示
        
- **方法示例**：
    
    `add_assets(movie_id, asset_list) update_asset(asset_id, data) remove_asset(asset_id) get_assets_by_movie(movie_id)`
    

### **library_service.py**

- **核心职责**：管理媒体库配置与规则
    
- **功能示例**：
    - 新建/更新/删除媒体库
    - 配置库的存储路径、命名规则、导入策略
    - 聚合库统计信息（影片数量、空间占用）
        
- **方法示例**：
    
    `create_library(library_data) update_library(library_id, data) get_library(library_id) delete_library(library_id) list_libraries()`
    

---

## 2️⃣ Users 相关服务

### **user_service.py**

- **核心职责**：管理用户基础信息、权限、账号安全
    
- **功能示例**：
    - 用户注册、登录、密码修改
    - 用户信息更新（profile）
    - 用户查询和列表（后台管理）
    - 用户最爱、片单功能实现
        
- **方法示例**：
    
    `create_user(user_data) update_user(user_id, data) get_user(user_id) authenticate_user(username, password)`
    

### **user_asset_service.py**

- **核心职责**：管理用户上传的个人创作内容
    
- **功能示例**：
    - 创建/更新/删除用户创作资源
    - 校验资源归属（user_id + asset_id）
    - 查询用户个人资源列表
        
- **方法示例**：
    
    `add_user_asset(user_id, asset_data) update_user_asset(asset_id, data) remove_user_asset(asset_id) get_user_assets(user_id)`
    

### **watch_history_service.py**

- **核心职责**：管理用户观看历史、播放行为
    
- **功能示例**：
    - 新增观看记录
    - 查询历史记录（分页、按日期/电影聚合）
    - 清理过期记录（TTL）
        
- **方法示例**：
    
    `add_watch_record(user_id, movie_id, timestamp) get_watch_history(user_id, limit=50) delete_watch_record(record_id)`
    

---

## 3️⃣ Tasks 相关服务

### **task_service.py**

- **核心职责**：管理后台任务调度、状态、结果
    
- **功能示例**：
    - 创建异步任务（抓取封面、生成 embedding、数据迁移）
    - 查询任务状态（pending/running/success/failure）
    - 任务取消或重试
        
- **方法示例**：
    
    `create_task(task_type, params) get_task(task_id) list_tasks(filter) cancel_task(task_id) retry_task(task_id)`
    

---

## 4️⃣ Logs 相关服务

### **log_service.py**

- **核心职责**：系统日志管理与聚合
    
- **功能示例**：
    - 查询日志（按时间、等级、模块）
    - 支持分页和过滤（error/warning/info）
    - 可用于审计和异常追踪
        
- **方法示例**：
    
    `query_logs(level=None, start_time=None, end_time=None) get_log(log_id) delete_old_logs(retention_days)`
    

---

## 5️⃣ Service 层的一些通用设计模式

- **跨 Repo 聚合**：
    - `MovieService.create_movie_with_assets` 调用 `movie_repo + asset_repo + vector_repo`
        
- **外部服务调用**：
    - `MovieService` 调用 `embedding_client` 生成向量
        
- **权限与安全**：
    - `UserService` 和 `UserAssetService` 校验操作权限
        
- **事务处理**：
    - 对电影 + 资源操作，用 MongoDB 事务或 try/except 回滚
        
- 缓存处理：
	- 使用 self.cache_repo = cache_repo 实现：查询缓存、任务队列、限流、分布式锁、短期状态存储等功能。