import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from src.logic.task.task_logic import TaskLogic
from src.logic.users.collection_logic import CollectionLogic
from src.logic.users.watch_history_logic import WatchHistoryLogic
from src.models import TaskStatus, WatchType, TaskInDB, CustomListInDB, WatchHistoryInDB, CustomListType, TaskType, TaskSubType, TaskPriority
from bson import ObjectId
from datetime import datetime

@pytest.mark.asyncio
async def test_task_status_cas():
    with patch('src.repos.mongo_repos.base_repo.BaseRepo.collection', new_callable=PropertyMock) as mock_collection_prop:
        mock_collection = AsyncMock()
        mock_collection_prop.return_value = mock_collection
        
        logic = TaskLogic()
        logic.repo.find_by_id = AsyncMock()
        
        # Mock conversion return
        mock_task = MagicMock(spec=TaskInDB)
        mock_task.model_dump.return_value = {
            "id": "507f1f77bcf86cd799439011", 
            "status": TaskStatus.RUNNING.value,
            "created_at": "2023-01-01T00:00:00Z",
            "name": "Test Task",
            "task_type": TaskType.IMPORT.value,
            "sub_type": TaskSubType.MOVIE_IMPORT.value,
            "priority": 50,
            "params": {}
        }
        logic.repo.convert_dict_to_pydanticModel = MagicMock(return_value=[mock_task])
        
        # Mock DB return
        mock_doc = {"_id": ObjectId(), "status": TaskStatus.RUNNING.value}
        mock_collection.find_one_and_update.return_value = mock_doc
        
        # Call
        await logic.transition_task_status(
            "507f1f77bcf86cd799439011", 
            TaskStatus.PENDING, 
            TaskStatus.RUNNING
        )
        
        # Verify CAS query
        args, kwargs = mock_collection.find_one_and_update.call_args
        query = args[0]
        update = args[1]
        
        assert query["_id"] == ObjectId("507f1f77bcf86cd799439011")
        assert query["status"] == TaskStatus.PENDING.value
        assert "$set" in update
        assert update["$set"]["status"] == TaskStatus.RUNNING.value

@pytest.mark.asyncio
async def test_collection_append_atomicity():
    with patch('src.repos.mongo_repos.base_repo.BaseRepo.collection', new_callable=PropertyMock) as mock_collection_prop:
        mock_collection = AsyncMock()
        mock_collection_prop.return_value = mock_collection
        
        logic = CollectionLogic()
        logic.cache_repo.delete_item_list = AsyncMock()
        logic.cache_repo.cache_detail = AsyncMock()
        logic.cache_repo.delete_search_cache_all = AsyncMock()
        
        # Mock conversion
        mock_list = MagicMock(spec=CustomListInDB)
        mock_list.user_id = "507f1f77bcf86cd799439011"
        mock_list.model_dump.return_value = {
            "id": "507f1f77bcf86cd799439011", 
            "user_id": "507f1f77bcf86cd799439011",
            "movies": [],
            "name": "My List",
            "type": CustomListType.CUSTOMLIST.value,
            "is_public": False,
            "created_at": datetime.now()
        }
        logic.repo.convert_dict_to_pydanticModel = MagicMock(return_value=[mock_list])
        
        mock_doc = {"_id": ObjectId(), "user_id": ObjectId(), "movies": []}
        mock_collection.find_one_and_update.return_value = mock_doc
        
        await logic.append_movies("507f1f77bcf86cd799439011", ["507f1f77bcf86cd799439012"])
        
        args, kwargs = mock_collection.find_one_and_update.call_args
        update = args[1]
        
        assert "$addToSet" in update
        assert "movies" in update["$addToSet"]
        assert "$each" in update["$addToSet"]["movies"]

@pytest.mark.asyncio
async def test_watch_history_upsert_monotonic():
    with patch('src.repos.mongo_repos.base_repo.BaseRepo.collection', new_callable=PropertyMock) as mock_collection_prop:
        mock_collection = AsyncMock()
        mock_collection_prop.return_value = mock_collection
        
        logic = WatchHistoryLogic()
        logic.cache_repo.cache_detail = AsyncMock()
        logic.cache_repo._update_recent_list = AsyncMock()
        
        # Mock conversion
        mock_hist = MagicMock(spec=WatchHistoryInDB)
        mock_hist.model_dump.return_value = {
            "id": "507f1f77bcf86cd799439011",
            "user_id": "507f1f77bcf86cd799439011",
            "asset_id": "507f1f77bcf86cd799439012",
            "movie_id": "507f1f77bcf86cd799439013",
            "type": WatchType.Official.value,
            "last_position": 100,
            "watch_count": 1,
            "total_duration": 200,
            "last_watched": datetime.now(),
            "created_at": datetime.now()
        }
        logic.repo.convert_dict_to_pydanticModel = MagicMock(return_value=[mock_hist])
        
        mock_doc = {"_id": ObjectId(), "user_id": ObjectId()}
        mock_collection.find_one_and_update.return_value = mock_doc
        
        update_patch = {"last_position": 100, "inc_watch": 1}
        await logic.upsert_watch_progress("507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012", WatchType.Official, update_patch)
        
        args, kwargs = mock_collection.find_one_and_update.call_args
        update = args[1]
        
        assert "$max" in update
        assert update["$max"]["last_position"] == 100
        assert "$inc" in update
        assert update["$inc"]["watch_count"] == 1
        assert kwargs["upsert"] is True
