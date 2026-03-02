#!/bin/bash
echo "🚀 启动 FastAPI..."
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload &

echo "⚙️ 启动 Celery Worker..."  # 使用 --pool=asyncio -c 200 指定异步并发
celery -A src.celery.app worker --pool=asyncio -c 200 -l info -Q movie_queue,collection_queue,media_queue,library_queue &

# echo "⏰ 启动 Celery Beat..."
# celery -A src.celery.app beat -l info &

wait
