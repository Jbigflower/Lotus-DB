import functools
import json
from typing import Callable, Optional, Any
from fastapi import Request, HTTPException, status
from fastapi.encoders import jsonable_encoder
from config.logging import get_router_logger
from src.db.redis_db import get_redis_manager

logger = get_router_logger("idempotency")

def idempotent(expire: int = 600, lock_expire: int = 60):
    """
    幂等性装饰器
    
    :param expire: 结果缓存过期时间（秒），默认 600
    :param lock_expire: 处理锁过期时间（秒），默认 60
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # 1. 获取 Request 对象
                request: Optional[Request] = next(
                    (a for a in args if isinstance(a, Request)), 
                    kwargs.get("request")
                )
                
                # 如果没有 Request 对象，无法获取 header，直接执行
                if not request:
                    return await func(*args, **kwargs)
                
                # 2. 获取 Idempotency-Key
                idem_key = request.headers.get("Idempotency-Key")
                if not idem_key:
                    return await func(*args, **kwargs)
                
                # 3. 获取 User ID
                current_user = kwargs.get("current_user")
                user_id = getattr(current_user, "id", "anonymous")
                
                # 4. 构造 Redis Key
                path = request.url.path
                method = request.method
                key = f"idemp:{user_id}:{method}:{path}:{idem_key}"
                key_done = f"{key}:done"
                key_lock = f"{key}:lock"
                
                redis_manager = None
                try:
                    redis_manager = get_redis_manager()
                except Exception as e:
                    logger.warning(f"Failed to get redis manager: {e}")
                    pass
                
                if not redis_manager or not getattr(redis_manager, "is_connected", False):
                    logger.warning("Redis not connected, skipping idempotency check")
                    return await func(*args, **kwargs)
                
                redis = redis_manager.client
                
                # 5. 检查是否已处理完成
                cached_resp = await redis.get(key_done)
                if cached_resp:
                    logger.info(f"Idempotency hit for key: {key}")
                    try:
                        return json.loads(cached_resp)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode cached response for key: {key}")
                        pass
                
                # 6. 尝试获取锁
                is_locked = await redis.set(key_lock, "1", nx=True, ex=lock_expire)
                if not is_locked:
                    logger.warning(f"Idempotency conflict (processing) for key: {key}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Request is already being processed"
                    )
                
                try:
                    # 7. 执行业务逻辑
                    response = await func(*args, **kwargs)
                    
                    # 8. 缓存结果
                    encoded_response = jsonable_encoder(response)
                    await redis.set(key_done, json.dumps(encoded_response), ex=expire)
                    
                    return response
                finally:
                    # 9. 释放锁
                    # 锁可以自然过期
                    pass
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Idempotency wrapper error: {e}", exc_info=True)
                # 降级：出错时直接执行业务逻辑
                return await func(*args, **kwargs)

        return wrapper
    return decorator
