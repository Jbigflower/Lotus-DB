# Lotus-DB

**Lotus-DB** 是一个现代化的个人媒体资产管理系统，集成了 LLM (大语言模型) 智能助手，旨在提供智能化的媒体库管理、检索与交互体验。

本项目采用前后端分离架构，结合了高性能的 FastAPI 后端与流畅的 Vue 3 前端，支持电影、剧集及个人视频资产的管理、播放与语义搜索。

## 🏗 架构概览

Lotus-DB 由以下核心组件构成：

*   **Frontend**: 基于 **Vue 3** + **TypeScript** + **Vite** 构建的单页应用 (SPA)，提供现代化的用户界面。
*   **Backend**: 基于 **FastAPI** (Python) 构建的高性能 RESTful API 服务，负责业务逻辑、数据持久化及任务调度。
*   **Agent**: 内置基于 **LangGraph** 的智能代理，支持通过自然语言进行媒体检索、资产管理与问答。
*   **Database**:
    *   **MongoDB**: 核心元数据存储。
    *   **Redis**: 缓存与异步任务队列。
    *   **ChromaDB / LanceDB**: 向量数据库，用于语义搜索与 RAG (检索增强生成)。

## 📂 目录结构

```
Lotus-DB/
├── lotus-db-backend-refactor/  # 后端服务源码
│   ├── src/                    # 核心业务逻辑
│   ├── config/                 # 配置文件
│   ├── scripts/                # 运维与工具脚本
│   └── run.py                  # 启动入口
├── lotus-db-frontend/          # 前端应用源码
│   ├── src/                    # Vue 组件与逻辑
│   └── vite.config.ts          # 构建配置
└── doc/                        # 项目设计文档与资源
```

## 🚀 快速开始

### 前置要求

在开始之前，请确保您的开发环境满足以下要求：

*   **Python**: 3.11 或更高版本 (推荐使用 Conda 管理环境)
*   **Node.js**: v18 或更高版本 (推荐 v20)
*   **MongoDB**: 运行在默认端口 27017
*   **Redis**: 运行在默认端口 6379
*   **Ollama** (可选): 用于本地 LLM 支持 (默认使用 Ollama 提供 Embedding 与 Chat 能力)

---

### 1. 启动后端服务

进入后端目录并配置环境：

```bash
cd lotus-db-backend-refactor

# 1. 创建并配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置数据库连接与 API 密钥（如 OMDB_API_KEY）

# 2. 安装依赖
# 方式 A: 使用 Conda (推荐)
conda create -n lotus-db python=3.11
conda activate lotus-db
pip install -r requirements.txt

# 方式 B: 使用 venv
# python -m venv venv
# source venv/bin/activate  # Windows: venv\Scripts\activate
# pip install -r requirements.txt

# 3. 启动 API 服务
python run.py
# 服务将运行在: http://localhost:8000
# API 文档: http://localhost:8000/docs

# 4. 动后台任务 Worker
# 用于处理文件扫描、元数据下载等耗时任务
python run.backtask.py
# 或者
python -m src.async_worker.main
```

### 2. 启动前端应用

进入前端目录并启动开发服务器：

```bash
cd lotus-db-frontend

# 1. 安装依赖
npm install

# 2. 配置环境变量 (可选)
# 默认连接本地后端 http://localhost:8000/api/v1
# 如需修改，请创建 .env 文件并设置 VITE_API_BASE_URL

# 3. 启动开发服务器
npm run dev
# 访问应用: http://localhost:5173
```

## ✨ 核心特性

- **智能媒体库**: 自动刮削元数据 (OMDB)，支持电影、剧集与个人视频的分类管理。
- **语义搜索**: 不仅仅是关键词匹配，支持通过自然语言描述查找影片 (例如："找一部关于太空探险的科幻片")。
- **Lotus Agent**: 内置 AI 助手，可进行多轮对话，协助管理片单、推荐电影或回答相关问题。
- **全能播放器**: 支持多种格式视频流播放，挂载外挂字幕，以及实时转码 (需配置 FFmpeg)。
- **多用户系统**: 完善的用户认证、权限管理与个人偏好设置。
- **后台任务**: 异步处理文件系统扫描、元数据更新与向量索引构建，保证前台操作流畅。

## 📝 文档

更多详细设计文档请参阅 `doc/` 目录，包含：
- 架构设计原则
- 数据库模型设计
- Agent 设计指南
- 前端页面设计稿

## 🤝 贡献

欢迎提交 Issue 与 Pull Request 帮助改进 Lotus-DB！