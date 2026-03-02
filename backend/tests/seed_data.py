import json
import os
import random
import logging
from datetime import datetime, timedelta, timezone, date
from typing import List, Dict, Any, Optional

from src.models.users.user_models import UserInDB, UserRole
from src.models.movies.library_models import LibraryInDB, LibraryType
from src.models.movies.movie_models import MovieInDB, MovieMetadata
from src.models.movies.asset_models import AssetInDB, AssetType, AssetStoreType, VideoMetadata, SubtitleMetadata, ImageMetadata
from src.models.users.user_custom_list_models import CustomListInDB, CustomListType
from src.models.users.user_asset_models import UserAssetInDB, UserAssetType, AssetStoreType
from src.models.users.watch_history_models import WatchHistoryInDB, WatchType
from src.models.tasks.task_models import TaskInDB, TaskStatus, TaskType, TaskSubType

from src.repos.mongo_repos.users.user_repo import UserRepo
from src.repos.mongo_repos.movies.library_repo import LibraryRepo
from src.repos.mongo_repos.movies.movie_repo import MovieRepo
from src.repos.mongo_repos.movies.asset_repo import AssetRepo
from src.repos.mongo_repos.users.user_custom_list_repo import UserCustomListRepo
from src.repos.mongo_repos.users.user_asset_repo import UserAssetRepo
from src.repos.mongo_repos.users.watch_history_repo import WatchHistoryRepo
from src.repos.mongo_repos.task.task_repo import TaskRepo
from hashlib import sha256
from bson import ObjectId

def get_password_hash(password: str) -> str:
    salt = "SALT"
    return sha256((salt + password).encode("utf-8")).hexdigest()

def get_random_object_id() -> str:
    return str(ObjectId())

logger = logging.getLogger(__name__)

class DataSeeder:
    def __init__(self):
        self.user_repo = UserRepo()
        self.library_repo = LibraryRepo()
        self.movie_repo = MovieRepo()
        self.asset_repo = AssetRepo()
        self.collection_repo = UserCustomListRepo()
        self.user_asset_repo = UserAssetRepo()
        self.history_repo = WatchHistoryRepo()
        self.task_repo = TaskRepo()
        
        self.users = {}
        self.libraries = {}
        self.library_id_map = {} # id -> LibraryInDB
        self.movies = {} # title -> List[MovieInDB] (since titles might duplicate across libraries, though unlikely for same user)
        self.movie_id_map = {} # title -> MovieInDB (last one wins, mostly for lookup)
        self.alias_map = {} # Alias -> ID/Object mapping for tests

    async def _insert(self, repo, model_obj):
        doc = model_obj.model_dump()
        if "id" in doc:
            doc["_id"] = ObjectId(doc.pop("id"))

        doc = self._normalize_object_ids(repo, doc)
        
        # Convert date to datetime for MongoDB compatibility
        for key, value in doc.items():
            if isinstance(value, date) and not isinstance(value, datetime):
                doc[key] = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        
        await repo.collection.insert_one(doc)
        return model_obj

    async def _update(self, repo, model_obj):
        doc = model_obj.model_dump()
        doc_id = doc.pop("id", None)

        doc = self._normalize_object_ids(repo, doc)
        
        # Convert date to datetime for MongoDB compatibility
        for key, value in doc.items():
            if isinstance(value, date) and not isinstance(value, datetime):
                doc[key] = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
                
        if doc_id:
             await repo.collection.update_one({"_id": ObjectId(doc_id)}, {"$set": doc})
        return model_obj

    def _normalize_object_ids(self, repo, doc: Dict[str, Any]) -> Dict[str, Any]:
        for field, value in list(doc.items()):
            if field.endswith("_id") and isinstance(value, str) and ObjectId.is_valid(value):
                doc[field] = ObjectId(value)
            elif field.endswith("_ids") and isinstance(value, list):
                doc[field] = [
                    ObjectId(item) if isinstance(item, str) and ObjectId.is_valid(item) else item
                    for item in value
                ]
        if isinstance(doc.get("movies"), list):
            doc["movies"] = [
                ObjectId(item) if isinstance(item, str) and ObjectId.is_valid(item) else item
                for item in doc["movies"]
            ]
        return doc

    async def seed_all(self):
        await self.seed_users()
        await self.seed_libraries()
        await self.seed_movies()
        await self.seed_assets()
        await self.seed_user_assets()
        await self.seed_collections()
        await self.seed_history()
        await self.seed_tasks()
        await self.seed_aliases()

    async def seed_aliases(self):
        """
        Populate self.alias_map for test placeholders.
        """
        # Users
        for name, user in self.users.items():
            self.alias_map[f"world.users.{name}.id"] = user.id
            
        # Libraries
        for name, lib in self.libraries.items():
            self.alias_map[f"world.libraries.{name}.id"] = lib.id
            
        # Collections
        # We need to find collections by name and user
        # Since we inserted them, we can try to find them back or just map known ones if we tracked them.
        # But we didn't track collections in a dict in this class (except implicitly).
        # Let's just fetch them or rely on the logic that we know what we inserted.
        # But `self.collection_repo` is available.
        
        # However, for simplicity and performance in tests, we can reconstruct or fetch.
        # Or better, let's track collections in `seed_collections`.
        # For now, I'll just query them back since it's mongomock and fast.
        # Wait, `seed_collections` is async and we are inside `seed_all`.
        
        # Let's map specific collections we know we created.
        user_a_id = self.users["爱吃香菜"].id
        col_must_see_list = await self.collection_repo.find({"user_id": ObjectId(user_a_id), "name": "人生必看"})
        if col_must_see_list:
            self.alias_map["world.collections.爱吃香菜_人生必看.id"] = col_must_see_list[0].id
            
        col_memories_list = await self.collection_repo.find({"user_id": ObjectId(user_a_id), "name": "岁月时光"})
        if col_memories_list:
            self.alias_map["world.collections.爱吃香菜_岁月时光.id"] = col_memories_list[0].id
            
        # Movies
        # Map specific aliases used in golden_dataset.jsonl
        
        # Helper to find movie ID by title and user (optional)
        def find_movie_id(title, user_key=None):
            movies = self.movies.get(title, [])
            if not movies:
                return None
            if user_key:
                user_id = self.users[user_key].id
                for m in movies:
                    lib = self.library_id_map.get(m.library_id)
                    if lib and lib.user_id == user_id:
                        return m.id
            return movies[0].id # Default to first one
            
        self.alias_map["world.movies.Red_Sorghum.id"] = find_movie_id("Red Sorghum")
        self.alias_map["world.movies.Iron_Man_2.id"] = find_movie_id("Iron Man 2")
        self.alias_map["world.movies.Infernal_Affairs.id"] = find_movie_id("Infernal Affairs")
        self.alias_map["world.movies.A_Beautiful_Mind.id"] = find_movie_id("A Beautiful Mind")
        self.alias_map["world.movies.American_Beauty.id"] = find_movie_id("American Beauty")
        self.alias_map["world.movies.Green_Book.id"] = find_movie_id("Green Book")
        self.alias_map["world.movies.Gladiator.id"] = find_movie_id("Gladiator")
        self.alias_map["world.movies.Iron_Man.id"] = find_movie_id("Iron Man")
        self.alias_map["world.movies.In_the_Heat_of_the_Sun.id"] = find_movie_id("In the Heat of the Sun")
        self.alias_map["world.movies.A_Better_Tomorrow.id"] = find_movie_id("A Better Tomorrow")
        self.alias_map["world.movies.A_Chinese_Odyssey_Part_Two.id"] = find_movie_id("A Chinese Odyssey: Part 2 - Cinderella")
        self.alias_map["world.movies.Days_of_Being_Wild.id"] = find_movie_id("Days of Being Wild")
        self.alias_map["world.movies.Flirting_Scholar.id"] = find_movie_id("Flirting Scholar")
        
        # Specific User A/B distinction
        self.alias_map["world.movies.Let_the_Bullets_Fly_A.id"] = find_movie_id("Let the Bullets Fly", "爱吃香菜")
        self.alias_map["world.movies.Let_the_Bullets_Fly_B.id"] = find_movie_id("Let the Bullets Fly", "AAA建材王哥")
        
        # Vlog
        # "2024年春节海南之旅" -> "Hainan_Vlog"
        # In travel_vlog_7.json, title might be "2024年春节海南之旅" or similar.
        # Let's assume it's "2024年春节海南之旅" based on dataset query "2024 春节 海南 海口 Vlog" matching "2024年春节海南之旅".
        self.alias_map["world.movies.Hainan_Vlog.id"] = find_movie_id("2024年春节海南之旅")

    async def seed_users(self):
        # 1. Admin
        admin = UserInDB(
            id=get_random_object_id(),
            username="admin",
            email="admin@lotus.com",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        await self._insert(self.user_repo, admin)
        self.users["admin"] = admin

        # 2. User A: 爱吃香菜
        user_a = UserInDB(
            id=get_random_object_id(),
            username="爱吃香菜",
            email="cilantro@lotus.com",
            hashed_password=get_password_hash("123456"),
            role=UserRole.USER,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        await self._insert(self.user_repo, user_a)
        self.users["爱吃香菜"] = user_a

        # 3. User B: AAA建材王哥
        user_b = UserInDB(
            id=get_random_object_id(),
            username="AAA建材王哥",
            email="wangge@lotus.com",
            hashed_password=get_password_hash("123456"),
            role=UserRole.USER,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        await self._insert(self.user_repo, user_b)
        self.users["AAA建材王哥"] = user_b

    async def seed_libraries(self):
        # User A Libraries
        lib_movie_a = LibraryInDB(
            id=get_random_object_id(),
            user_id=self.users["爱吃香菜"].id,
            name="电影",
            root_path="/data/user_a/movies",
            type=LibraryType.MOVIE,
            description="那些年，我们一起追过的美好岁月",
            is_public=True
        )
        await self._insert(self.library_repo, lib_movie_a)
        self.libraries["爱吃香菜_电影"] = lib_movie_a
        self.library_id_map[lib_movie_a.id] = lib_movie_a

        lib_vlog_a = LibraryInDB(
            id=get_random_object_id(),
            user_id=self.users["爱吃香菜"].id,
            name="青葱岁月",
            root_path="/data/user_a/vlogs",
            type=LibraryType.MOVIE, 
            description="旅行 Vlog",
            is_public=False
        )
        await self._insert(self.library_repo, lib_vlog_a)
        self.libraries["爱吃香菜_青葱岁月"] = lib_vlog_a
        self.library_id_map[lib_vlog_a.id] = lib_vlog_a

        # User B Libraries
        lib_movie_b = LibraryInDB(
            id=get_random_object_id(),
            user_id=self.users["AAA建材王哥"].id,
            name="电影",
            root_path="/data/user_b/movies",
            type=LibraryType.MOVIE,
            description="",
            is_public=True
        )
        await self._insert(self.library_repo, lib_movie_b)
        self.libraries["AAA建材王哥_电影"] = lib_movie_b
        self.library_id_map[lib_movie_b.id] = lib_movie_b

        lib_learn_b = LibraryInDB(
            id=get_random_object_id(),
            user_id=self.users["AAA建材王哥"].id,
            name="大模型学习",
            root_path="/data/user_b/learning",
            type=LibraryType.MOVIE,
            description="记录大模型的转行学习路线",
            is_public=True
        )
        await self._insert(self.library_repo, lib_learn_b)
        self.libraries["AAA建材王哥_大模型学习"] = lib_learn_b
        self.library_id_map[lib_learn_b.id] = lib_learn_b

    async def seed_movies(self):
        base_path = os.path.join(os.path.dirname(__file__), "../data/test_data/movies")
        
        async def load_and_insert(filename, lib_key, special_handler=None):
            file_path = os.path.join(base_path, filename)
            if not os.path.exists(file_path):
                logger.warning(f"File not found: {file_path}")
                return

            with open(file_path, 'r') as f:
                data = json.load(f)
            
            lib_id = self.libraries[lib_key].id
            for item in data:
                if "library_id" in item:
                    del item["library_id"]
                
                item["library_id"] = lib_id
                item["id"] = get_random_object_id()
                item["created_at"] = datetime.now(timezone.utc)
                item["updated_at"] = datetime.now(timezone.utc)
                
                if item.get("release_date"):
                    try:
                        # Handle YYYY-MM-DD
                        item["release_date"] = datetime.strptime(item["release_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        item["release_date"] = None

                # Special Handling
                if item["title"] == "American Beauty":
                    item["metadata"] = MovieMetadata() 
                    item["description"] = ""
                    item["description_cn"] = ""
                    item["title_cn"] = ""
                    item["actors"] = []
                    item["directors"] = []
                    item["genres"] = []
                    item["tags"] = []
                    item["rating"] = None
                    item["release_date"] = None
                
                if filename == "oscar_best_picture_2000_2024.json":
                     item["title_cn"] = ""
                     item["description_cn"] = ""

                if special_handler:
                    special_handler(item)

                movie = MovieInDB(**item)
                await self._insert(self.movie_repo, movie)
                
                self.movie_id_map[movie.title] = movie
                if movie.title not in self.movies:
                    self.movies[movie.title] = []
                self.movies[movie.title].append(movie)

        # 1. User A - Movies
        await load_and_insert("oscar_best_picture_2000_2024.json", "爱吃香菜_电影")
        await load_and_insert("hong_kong_classics_10.json", "爱吃香菜_电影")
        await load_and_insert("mainland_classics_10.json", "爱吃香菜_电影")

        # 2. User A - Vlogs
        await load_and_insert("travel_vlog_7.json", "爱吃香菜_青葱岁月")

        # 3. User B - Movies
        await load_and_insert("marvel_13.json", "AAA建材王哥_电影")
        await load_and_insert("comedy_10.json", "AAA建材王哥_电影")

        # 4. User B - Learning
        await load_and_insert("llm_learn_6.json", "AAA建材王哥_大模型学习")

    async def seed_assets(self):
        # 1. Load specific assets for Vlogs and Learning
        await self._seed_specific_assets("travel_vlog_7.json", "爱吃香菜_青葱岁月")
        await self._seed_specific_assets("llm_learn_6.json", "AAA建材王哥_大模型学习")
        
        # 2. Generate fake assets for others
        # We need to iterate over movies and check if they are already handled
        handled_titles = set()
        
        # Helper to check if title is from specific list
        def is_in_json(title, json_file):
            # Optimization: could cache these lists
            # For now, simplistic check
            return False 

        # We can identify handled movies by their library
        vlog_lib_id = self.libraries["爱吃香菜_青葱岁月"].id
        learn_lib_id = self.libraries["AAA建材王哥_大模型学习"].id

        all_movies = await self.movie_repo.find({})
        for movie in all_movies:
            if movie.library_id in [vlog_lib_id, learn_lib_id]:
                continue
            
            await self._generate_fake_assets_for_movie(movie)

    async def _seed_specific_assets(self, json_filename, lib_key):
        base_path = os.path.join(os.path.dirname(__file__), "../data/test_data/movie_assets")
        file_path = os.path.join(base_path, json_filename)
        
        if not os.path.exists(file_path):
            logger.warning(f"Asset file not found: {file_path}")
            return

        with open(file_path, 'r') as f:
            data = json.load(f)

        for item in data:
            movie_title = item.pop("movie_title", None)
            if not movie_title:
                continue
            
            # Find movie in the specific library
            # Since self.movies[title] is a list, we need to filter by library_id
            target_lib_id = self.libraries[lib_key].id
            target_movie = None
            
            # Try to find by title (English)
            if movie_title in self.movies:
                for m in self.movies[movie_title]:
                    if m.library_id == target_lib_id:
                        target_movie = m
                        break
            
            # If not found, try to find by title_cn
            if not target_movie:
                for title_key, movies_list in self.movies.items():
                    for m in movies_list:
                        if m.library_id == target_lib_id and m.title_cn == movie_title:
                            target_movie = m
                            break
                    if target_movie:
                        break
            
            if not target_movie:
                logger.warning(f"Movie not found for asset: {movie_title} in lib {lib_key}")
                continue

            item["id"] = get_random_object_id()
            item["movie_id"] = target_movie.id
            item["user_id"] = self.libraries[lib_key].user_id # Asset usually belongs to movie owner
            item["library_id"] = target_movie.library_id
            item["created_at"] = datetime.now(timezone.utc)
            item["updated_at"] = datetime.now(timezone.utc)
            
            # Metadata conversion
            meta_data = item.get("metadata", {})
            if meta_data.get("type") == "video":
                item["metadata"] = VideoMetadata(**meta_data)
            elif meta_data.get("type") == "subtitle":
                item["metadata"] = SubtitleMetadata(**meta_data)
            elif meta_data.get("type") == "image":
                item["metadata"] = ImageMetadata(**meta_data)
            
            asset = AssetInDB(**item)
            await self._insert(self.asset_repo, asset)

    async def _generate_fake_assets_for_movie(self, movie: MovieInDB):
        # Special Rules
        title = movie.title
        
        # 1. Special Movies with specific rules
        if title == "Infernal Affairs":
            await self._create_fake_asset(movie, AssetType.VIDEO, count=2)
            await self._create_fake_asset(movie, AssetType.SUBTITLE, count=1, lang="zh")
            await self._create_fake_asset(movie, AssetType.IMAGE, count=3)
            return

        if title == "12 Years a Slave":
            await self._create_fake_asset(movie, AssetType.VIDEO, count=1)
            await self._create_fake_asset(movie, AssetType.IMAGE, count=1)
            # No subtitles
            return

        no_subtitle_movies = ["The Artist", "Argo", "Birdman", "Spotlight", "Moonlight"]
        if title in no_subtitle_movies:
             await self._create_fake_asset(movie, AssetType.VIDEO, count=1)
             await self._create_fake_asset(movie, AssetType.IMAGE, count=1)
             return

        if title == "The Lord of the Rings: The Return of the King":
            await self._create_fake_asset(movie, AssetType.VIDEO, count=1)
            await self._create_fake_asset(movie, AssetType.SUBTITLE, count=1, lang="de")
            await self._create_fake_asset(movie, AssetType.IMAGE, count=1)
            return

        if title == "Iron Man 2":
            await self._create_fake_asset(movie, AssetType.VIDEO, count=1)
            await self._create_fake_asset(movie, AssetType.SUBTITLE, count=1, lang="zh")
            await self._create_fake_asset(movie, AssetType.IMAGE, count=1)
            return

        if title == "A Beautiful Mind":
            # 1 Video, missing metadata
            asset = await self._create_fake_asset(movie, AssetType.VIDEO, count=1, return_obj=True)
            # Manually strip metadata
            # Assuming _create_fake_asset creates and saves. We update it.
            # But wait, create_fake_asset implementation below needs to handle this or we update after.
            # Let's handle it by update
            # Actually, the requirement says "元数据缺失". 
            # If I set metadata fields to None/Default?
            # VideoMetadata has required fields. I'll just set them to 0 or empty.
            asset.metadata = VideoMetadata(
                codec="", width=0, height=0, duration=0, size=0, bit_rate=0
            )
            await self._update(self.asset_repo, asset)
            return

        # 2. General Rules
        # Video: 30%
        if random.random() < 0.3:
            await self._create_fake_asset(movie, AssetType.VIDEO, count=1)
        
        # Subtitle: 80%
        if random.random() < 0.8:
            # 90% Chinese, 10% German
            lang = "zh" if random.random() < 0.9 else "de"
            await self._create_fake_asset(movie, AssetType.SUBTITLE, count=1, lang=lang)

        # Image: 10%
        if random.random() < 0.1:
             await self._create_fake_asset(movie, AssetType.IMAGE, count=1)


    async def _create_fake_asset(self, movie: MovieInDB, asset_type: AssetType, count=1, lang="zh", return_obj=False):
        created_assets = []
        for i in range(count):
            asset_id = get_random_object_id()
            metadata = None
            path = ""
            name = ""
            
            if asset_type == AssetType.VIDEO:
                name = f"{movie.title}_video_{i+1}.mp4"
                path = f"/data/fake/{movie.title}/{name}"
                duration = 7200 + random.randint(-600, 600) # ~2 hours
                metadata = VideoMetadata(
                    codec="h264", width=1920, height=1080, duration=duration, size=1024*1024*1000, bit_rate=5000
                )
            elif asset_type == AssetType.SUBTITLE:
                ext = "srt"
                name = f"{movie.title}_{lang}.{ext}"
                path = f"/data/fake/{movie.title}/{name}"
                metadata = SubtitleMetadata(
                    language=lang, encoding="utf-8"
                )
            elif asset_type == AssetType.IMAGE:
                name = f"{movie.title}_poster_{i+1}.jpg"
                path = f"/data/fake/{movie.title}/{name}"
                metadata = ImageMetadata(
                    width=1920, height=1080, format="jpeg"
                )

            asset = AssetInDB(
                id=asset_id,
                movie_id=movie.id,
                library_id=movie.library_id,
                user_id=self.library_id_map[movie.library_id].user_id,
                name=name,
                path=path,
                type=asset_type,
                store_type=AssetStoreType.LOCAL,
                metadata=metadata,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            await self._insert(self.asset_repo, asset)
            created_assets.append(asset)
        
        if return_obj and created_assets:
            return created_assets[0]
        return created_assets

    async def seed_user_assets(self):
        # 1. 让子弹飞
        # Find "让子弹飞" from User A (it's in Mainland Classics)
        # Note: The doc says "让子弹飞" in User A's movie lib.
        # It also says User B has "让子弹飞" in his Comedy lib.
        
        # User A's "让子弹飞"
        movie_a_list = self.movies.get("Let the Bullets Fly")
        movie_a = None
        movie_b = None
        
        if movie_a_list:
            for m in movie_a_list:
                m_user_id = self.library_id_map[m.library_id].user_id
                if m_user_id == self.users["爱吃香菜"].id:
                    movie_a = m
                elif m_user_id == self.users["AAA建材王哥"].id:
                    movie_b = m

        if movie_a:
            # User A: 2 Images, 1 Comment, 1 Note
            # Images
            for i in range(2):
                await self._insert(self.user_asset_repo, UserAssetInDB(
                    id=get_random_object_id(),
                    user_id=self.users["爱吃香菜"].id,
                    movie_id=movie_a.id,
                    type=UserAssetType.SCREENSHOT,
                    name=f"让子弹飞_截图_{i+1}",
                    path=f"/user_assets/img_{i}.jpg",
                    store_type=AssetStoreType.LOCAL,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                ))
            # Comment
            await self._insert(self.user_asset_repo, UserAssetInDB(
                id=get_random_object_id(),
                user_id=self.users["爱吃香菜"].id,
                movie_id=movie_a.id,
                type=UserAssetType.REVIEW,
                name="神作",
                content="站着把钱挣了！",
                path="/virtual/review", # Review doesn't necessarily have a file path
                store_type=AssetStoreType.LOCAL,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))
            # Note
            await self._insert(self.user_asset_repo, UserAssetInDB(
                id=get_random_object_id(),
                user_id=self.users["爱吃香菜"].id,
                movie_id=movie_a.id,
                type=UserAssetType.NOTE,
                name="观影笔记",
                content="细节分析...",
                path="/virtual/note",
                store_type=AssetStoreType.LOCAL,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))
            
            # User B comment on User A's movie
            await self._insert(self.user_asset_repo, UserAssetInDB(
                id=get_random_object_id(),
                user_id=self.users["AAA建材王哥"].id,
                movie_id=movie_a.id,
                type=UserAssetType.REVIEW,
                name="Re: 神作",
                content="确实！",
                path="/virtual/review",
                store_type=AssetStoreType.LOCAL,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))

        if movie_b:
            # User A comment on User B's movie
            await self._insert(self.user_asset_repo, UserAssetInDB(
                id=get_random_object_id(),
                user_id=self.users["爱吃香菜"].id,
                movie_id=movie_b.id,
                type=UserAssetType.REVIEW,
                name="串门",
                content="你也喜欢这个？",
                path="/virtual/review",
                store_type=AssetStoreType.LOCAL,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))
            # User B comment on User B's movie
            await self._insert(self.user_asset_repo, UserAssetInDB(
                id=get_random_object_id(),
                user_id=self.users["AAA建材王哥"].id,
                movie_id=movie_b.id,
                type=UserAssetType.REVIEW,
                name="经典",
                content="百看不厌",
                path="/virtual/review",
                store_type=AssetStoreType.LOCAL,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))

    async def seed_collections(self):
        # 1. 爱吃香菜
        user_a_id = self.users["爱吃香菜"].id
        
        # 人生必看
        movies_1 = []
        for title in ["American Beauty", "Gladiator", "A Beautiful Mind", "Chicago", "The Lord of the Rings: The Return of the King", "Million Dollar Baby"]:
             if title in self.movies:
                 # Prefer User A's movie
                 for m in self.movies[title]:
                     if self.library_id_map[m.library_id].user_id == user_a_id:
                         movies_1.append(m.id)
                         break
        
        await self._insert(self.collection_repo, CustomListInDB(
            id=get_random_object_id(),
            user_id=user_a_id,
            name="人生必看",
            type=CustomListType.CUSTOMLIST,
            is_public=True,
            movies=movies_1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        ))

        # 岁月时光
        movies_2 = []
        titles_2 = ["Let the Bullets Fly", "Flirting Scholar", "Gladiator", "A Better Tomorrow", "A Chinese Odyssey: Part 2 - Cinderella", "Infernal Affairs", "Days of Being Wild"]
        # "Let the Bullets Fly" (AAA建材王哥的“电影”中的让子弹飞)
        # Find User B's Let the Bullets Fly
        bullets_b = None
        if "Let the Bullets Fly" in self.movies:
            for m in self.movies["Let the Bullets Fly"]:
                if self.library_id_map[m.library_id].user_id == self.users["AAA建材王哥"].id:
                    bullets_b = m
                    break
        if bullets_b:
            movies_2.append(bullets_b.id)
        
        for title in titles_2:
            if title == "Let the Bullets Fly": continue
            if title in self.movies:
                for m in self.movies[title]:
                    if self.library_id_map[m.library_id].user_id == user_a_id:
                        movies_2.append(m.id)
                        break

        await self._insert(self.collection_repo, CustomListInDB(
            id=get_random_object_id(),
            user_id=user_a_id,
            name="岁月时光",
            type=CustomListType.CUSTOMLIST,
            is_public=True,
            movies=movies_2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        ))

        # 周末安排
        movies_3 = []
        # 让子弹飞（爱吃香菜的）
        bullets_a = None
        if "Let the Bullets Fly" in self.movies:
             for m in self.movies["Let the Bullets Fly"]:
                if self.library_id_map[m.library_id].user_id == user_a_id:
                    bullets_a = m
                    break
        if bullets_a:
            movies_3.append(bullets_a.id)
        
        # Captain America: Civil War（AAA建材王哥的）
        cap_civil = None
        if "Captain America: Civil War" in self.movies:
            for m in self.movies["Captain America: Civil War"]:
                if self.library_id_map[m.library_id].user_id == self.users["AAA建材王哥"].id:
                    cap_civil = m
                    break
        if cap_civil:
            movies_3.append(cap_civil.id)
            
        await self._insert(self.collection_repo, CustomListInDB(
            id=get_random_object_id(),
            user_id=user_a_id,
            name="周末安排",
            type=CustomListType.CUSTOMLIST,
            is_public=True,
            movies=movies_3,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        ))

        # 2. AAA建材王哥
        user_b_id = self.users["AAA建材王哥"].id
        
        # 漫威补全计划
        marvel_lib = self.libraries["AAA建材王哥_电影"]
        marvel_titles = ["Iron Man", "The Incredible Hulk", "Iron Man 2", "Thor", "Captain America: The First Avenger", 
                         "The Avengers", "Iron Man 3", "Thor: The Dark World", "Captain America: The Winter Soldier", 
                         "Guardians of the Galaxy", "Avengers: Age of Ultron", "Ant-Man", "Captain America: Civil War"]
        
        movies_b_1 = []
        for title in marvel_titles:
            if title in self.movies:
                for m in self.movies[title]:
                    if self.library_id_map[m.library_id].user_id == user_b_id:
                        movies_b_1.append(m.id)
                        break
        
        await self._insert(self.collection_repo, CustomListInDB(
            id=get_random_object_id(),
            user_id=user_b_id,
            name="漫威补全计划",
            type=CustomListType.CUSTOMLIST,
            is_public=False,
            movies=movies_b_1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        ))

        # LLM 复习计划
        movies_b_2 = []
        for title in ["LLM 之模型后训练", "LLM 之模型预训练"]:
             if title in self.movies:
                for m in self.movies[title]:
                    if self.library_id_map[m.library_id].user_id == user_b_id:
                        movies_b_2.append(m.id)
                        break
        
        await self._insert(self.collection_repo, CustomListInDB(
            id=get_random_object_id(),
            user_id=user_b_id,
            name="LLM 复习计划",
            type=CustomListType.CUSTOMLIST,
            is_public=True,
            movies=movies_b_2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        ))

    async def seed_history(self):
        # User A: HK/CN movies, 2023-2024
        user_a_id = self.users["爱吃香菜"].id
        target_movies = []
        
        # HK Classics
        hk_titles = ["A Better Tomorrow", "A Chinese Odyssey: Part 2 - Cinderella", "Infernal Affairs", "Days of Being Wild", "Ashes of Time", "Police Story", "All for the Winner", "A Chinese Ghost Story", "Kung Fu Hustle", "Flirting Scholar"]
        # CN Classics
        cn_titles = ["Farewell My Concubine", "To Live", "Red Sorghum", "Let the Bullets Fly", "Dying to Survive", "Wreaths at the Foot of the Mountain", "Hibiscus Town", "Raise the Red Lantern", "In the Heat of the Sun", "The Wandering Earth"]
        
        for title in hk_titles + cn_titles:
            if title in self.movies:
                for m in self.movies[title]:
                    if self.library_id_map[m.library_id].user_id == user_a_id:
                        target_movies.append(m)
                        break
        
        for movie in target_movies:
            # Random date in 2023-2024
            start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
            end_date = datetime(2024, 12, 31, tzinfo=timezone.utc)
            random_date = start_date + timedelta(seconds=random.randint(0, int((end_date - start_date).total_seconds())))
            
            await self._insert(self.history_repo, WatchHistoryInDB(
                id=get_random_object_id(),
                user_id=user_a_id,
                movie_id=movie.id,
                asset_id=get_random_object_id(),
                type=WatchType.Official,
                last_position=random.randint(0, 7200),
                total_duration=7200,
                last_watched=random_date,
                device_info={"device": random.choice(["Web", "Mobile", "TV"])},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))

    async def seed_tasks(self):
        # 1. American Beauty: Failed Metadata Download (Network Timeout)
        ab_movie = self.movies.get("American Beauty", [None])[0]
        if ab_movie:
            await self._insert(self.task_repo, TaskInDB(
                id=get_random_object_id(),
                name="Metadata Download",
                task_type=TaskType.ANALYSIS,
                sub_type=TaskSubType.EXTRACT_METADATA,
                status=TaskStatus.FAILED,
                parameters={"movie_id": ab_movie.id},
                error_message="Network Timeout",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))

        # 2. Gladiator: Waiting for preview
        glad_movie = self.movies.get("Gladiator", [None])[0]
        if glad_movie:
             await self._insert(self.task_repo, TaskInDB(
                id=get_random_object_id(),
                name="Preview Generation",
                task_type=TaskType.ANALYSIS,
                sub_type=TaskSubType.THUMB_SPRITE_GENERATE,
                status=TaskStatus.PENDING,
                parameters={"movie_id": glad_movie.id},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))

        # 3. A Beautiful Mind: Failed OOM
        abm_movie = self.movies.get("A Beautiful Mind", [None])[0]
        if abm_movie:
             await self._insert(self.task_repo, TaskInDB(
                id=get_random_object_id(),
                name="Metadata Download",
                task_type=TaskType.ANALYSIS,
                sub_type=TaskSubType.EXTRACT_METADATA,
                status=TaskStatus.FAILED,
                parameters={"movie_id": abm_movie.id},
                error_message="OOM: Out of Memory",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            ))
