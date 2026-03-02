import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import Request, HTTPException
from src.core.idempotency import idempotent

# Mock Redis
class MockRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None # Redis returns None if NX fails
        self.store[key] = value
        return True

    async def delete(self, key):
        if key in self.store:
            del self.store[key]
        return 1

class MockRequest:
    def __init__(self, headers, method="POST", path="/test"):
        self.headers = headers
        self.method = method
        self.url = MagicMock()
        self.url.path = path

@pytest.mark.asyncio
async def test_idempotency_success():
    mock_redis = MockRedis()
    mock_manager = MagicMock()
    mock_manager.client = mock_redis
    mock_manager.is_connected = True
    
    with patch("src.core.idempotency.get_redis_manager", return_value=mock_manager):
        
        # Define a decorated function
        @idempotent()
        async def my_func(request: Request, current_user=None):
            return {"status": "ok", "data": "123"}
        
        # Mock request
        request = MockRequest(headers={"Idempotency-Key": "test-key-1"})
        
        current_user = MagicMock()
        current_user.id = "user1"
        
        # First call
        resp1 = await my_func(request=request, current_user=current_user)
        assert resp1 == {"status": "ok", "data": "123"}
        
        # Verify Redis state
        key_done = "idemp:user1:POST:/test:test-key-1:done"
        cached = await mock_redis.get(key_done)
        assert cached is not None
        assert json.loads(cached) == {"status": "ok", "data": "123"}
        
        # Second call
        resp2 = await my_func(request=request, current_user=current_user)
        assert resp2 == {"status": "ok", "data": "123"}

@pytest.mark.asyncio
async def test_idempotency_conflict():
    mock_redis = MockRedis()
    mock_manager = MagicMock()
    mock_manager.client = mock_redis
    mock_manager.is_connected = True
    
    with patch("src.core.idempotency.get_redis_manager", return_value=mock_manager):
        
        @idempotent()
        async def my_func(request: Request, current_user=None):
            return {"status": "ok"}
            
        request = MockRequest(headers={"Idempotency-Key": "test-key-2"})
        
        current_user = MagicMock()
        current_user.id = "user1"
        
        # Manually set lock
        key_lock = "idemp:user1:POST:/test:test-key-2:lock"
        await mock_redis.set(key_lock, "1")
        
        # Call should fail with 409
        with pytest.raises(HTTPException) as exc:
            await my_func(request=request, current_user=current_user)
        assert exc.value.status_code == 409

@pytest.mark.asyncio
async def test_idempotency_no_key():
    mock_redis = MockRedis()
    mock_manager = MagicMock()
    mock_manager.client = mock_redis
    mock_manager.is_connected = True
    
    with patch("src.core.idempotency.get_redis_manager", return_value=mock_manager):
        
        @idempotent()
        async def my_func(request: Request, current_user=None):
            return {"status": "ok", "called": True}
            
        request = MockRequest(headers={})
        
        current_user = MagicMock()
        current_user.id = "user1"
        
        # Call should succeed without idempotency check
        resp = await my_func(request=request, current_user=current_user)
        assert resp["called"] is True
        
        # Verify no redis keys
        assert len(mock_redis.store) == 0
