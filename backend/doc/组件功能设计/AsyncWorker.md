AsyncWorker 替代 Celery 作为项目（FastAPI / 后台任务）的轻量异步任务系统基础。

## 一、设计目标
|目标|描述|
|---|---|
|**轻量无依赖**|不依赖 Celery、Redis，仅基于 asyncio|
|**异步调度**|使用 asyncio 事件循环和优先级队列|
|**统一资源**|共用数据库连接（例如 motor / asyncpg 实例）|
|**任务优先级**|支持高/中/低优先级异步任务调度|
|**安全关闭**|优雅关闭任务与数据库连接|
|**可扩展**|可轻松支持定时任务 / 后台运行 / 持久化调度|
|**调试友好**|支持日志打印和异常回溯|

## 二、模块结构

```
src/
 └── async_worker/
      ├── __init__.py
      ├── core.py          # 核心调度器（AsyncWorker）
      ├── tasks.py         # 注册任务
      ├── priority.py      # 优先级定义
      ├── scheduler.py     # 可选：定时调度器（asyncio.create_task 实现）
      └── context.py       # 数据库 / 共享资源初始化与关闭
```


