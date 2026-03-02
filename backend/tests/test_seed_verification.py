import pytest
from bson import ObjectId
from src.models.users.user_models import UserRole
from src.models.movies.library_models import LibraryType
from src.models.movies.asset_models import AssetType
from src.models.users.user_asset_models import UserAssetType

@pytest.mark.asyncio
async def test_verify_seeding(test_seeder, mongo_connection):
    seeder = test_seeder
    
    # 1. Verify Users
    admin = await seeder.user_repo.find_by_id(seeder.users["admin"].id)
    assert admin.username == "admin"
    assert admin.role == UserRole.ADMIN
    
    user_a = await seeder.user_repo.find_by_id(seeder.users["爱吃香菜"].id)
    assert user_a.username == "爱吃香菜"
    
    user_b = await seeder.user_repo.find_by_id(seeder.users["AAA建材王哥"].id)
    assert user_b.username == "AAA建材王哥"

    # 2. Verify Libraries
    libs = await seeder.library_repo.find({})
    assert len(libs) == 4
    
    lib_names = [l.name for l in libs]
    assert "电影" in lib_names
    assert "青葱岁月" in lib_names
    assert "大模型学习" in lib_names

    # 3. Verify Movies
    movies = await seeder.movie_repo.find({})
    print(movies[0:5])
    # 25 Oscar + 10 HK + 10 CN + 7 Vlog + 13 Marvel + 10 Comedy + 6 LLM = 81
    # But wait, some titles might be duplicates across users/libraries?
    # "让子弹飞" is in both (CN classics for A, Comedy for B).
    # "唐伯虎点秋香" is in both (HK classics for A, Comedy for B).
    # "功夫" is in both.
    # "大话西游" is in both.
    # "我不是药神" is in both.
    # "Gladiator" is in Oscar (A) and maybe in A's collection (but collection just refs id).
    # So we should have unique movie entries for each library insertion.
    # Oscar: 25
    # HK: 10
    # CN: 10
    # Vlog: 7
    # Marvel: 13
    # Comedy: 10
    # LLM: 6
    # Total = 81
    assert len(movies) == 81

    # Check American Beauty
    ab = next((m for m in movies if m.title == "American Beauty"), None)
    assert ab is not None, "American Beauty not found"
    assert ab.description == ""
    assert ab.actors == []
    assert ab.title_cn == ""
    assert ab.tags == []
    assert ab.rating is None
    assert ab.release_date is None
    assert ab.metadata.duration is None
    assert ab.metadata.country == []
    assert ab.metadata.language is None
    
    # Check Oscar movie (e.g. Gladiator) has no Chinese title
    gladiator = next((m for m in movies if m.title == "Gladiator"), None)
    assert gladiator is not None, "Gladiator not found"
    assert gladiator.title_cn == ""
    assert gladiator.description_cn == ""
    
    # Check Iron Man 2 has Chinese subtitle
    iron_man = next((m for m in movies if m.title == "Iron Man 2"), None)
    assert iron_man is not None, "Iron Man 2 not found"
    iron_assets = await seeder.asset_repo.find({"movie_id": ObjectId(iron_man.id)})
    iron_subs = [a for a in iron_assets if a.type == AssetType.SUBTITLE]
    assert len(iron_subs) >= 1
    assert any(s.metadata.language == "zh" for s in iron_subs)

    # 4. Verify Assets
    # Check "无间道" (User A)
    # Find "无间道" belonging to User A
    user_a_libs = await seeder.library_repo.find({"user_id": ObjectId(user_a.id)})
    user_a_lib_ids = {l.id for l in user_a_libs}
    
    # Debug print
    user_a_movies = [m for m in movies if m.library_id in user_a_lib_ids]
    print(f"User A movies count: {len(user_a_movies)}")
    print(f"User A movie titles: {[m.title for m in user_a_movies]}")
    print(f"User A movie cn titles: {[m.title_cn for m in user_a_movies]}")

    wjd = None
    for m in movies:
        if m.library_id in user_a_lib_ids:
            if m.title_cn == "无间道" or m.title == "Infernal Affairs":
                wjd = m
                break
    
    assert wjd is not None, f"Could not find '无间道' or 'Infernal Affairs' for User A in {[m.title for m in movies if m.library_id in user_a_lib_ids]}"
    
    assets = await seeder.asset_repo.find({"movie_id": ObjectId(wjd.id)})
    videos = [a for a in assets if a.type == AssetType.VIDEO]
    subtitles = [a for a in assets if a.type == AssetType.SUBTITLE]
    images = [a for a in assets if a.type == AssetType.IMAGE]
    
    assert len(videos) == 2
    assert len(subtitles) == 1
    assert subtitles[0].metadata.language == "zh"
    assert len(images) == 3

    # Check "12 Years a Slave"
    slave = next((m for m in movies if m.title == "12 Years a Slave"), None)
    assert slave is not None, "12 Years a Slave not found"
    slave_assets = await seeder.asset_repo.find({"movie_id": ObjectId(slave.id)})
    assert not any(a.type == AssetType.SUBTITLE for a in slave_assets)

    # Check "The Lord of the Rings: The Return of the King"
    lotr = next((m for m in movies if m.title == "The Lord of the Rings: The Return of the King"), None)
    assert lotr is not None, "LOTR not found"
    lotr_assets = await seeder.asset_repo.find({"movie_id": ObjectId(lotr.id)})
    lotr_subs = [a for a in lotr_assets if a.type == AssetType.SUBTITLE]
    assert len(lotr_subs) == 1
    assert lotr_subs[0].metadata.language == "de"

    # Check Vlogs (from json)
    vlog_lib = seeder.libraries["爱吃香菜_青葱岁月"]
    vlog_movies = await seeder.movie_repo.find({"library_id": ObjectId(vlog_lib.id)})
    assert len(vlog_movies) == 7
    # Check assets for one vlog
    # e.g. "2022年春节三亚之旅" -> "出发 VLOG"
    # Need to find the movie first. The movie title in JSON is "2022年春节三亚之旅".
    # But wait, the movie list JSON `travel_vlog_7.json` has `title`="2022年春节三亚之旅".
    # Actually `travel_vlog_7.json` contains multiple entries with same title?
    # Let's check `travel_vlog_7.json` content again.
    # Ah, `travel_vlog_7.json` (assets) has `movie_title`="2022年春节三亚之旅".
    # The movies JSON `travel_vlog_7.json` (movies) has... let's assume it has 7 distinct movies or 1 movie?
    # The doc says "User A '青葱岁月' ... 包含电影: 1. 2022年春节三亚之旅 ... 7. 2024年11月闪击天津".
    # So there are 7 movies.
    # The assets JSON likely maps these titles to assets.
    
    # 5. Verify User Assets
    # "让子弹飞" (User A)
    bullets_a = next((m for m in movies if (m.title == "Let the Bullets Fly" or m.title_cn == "让子弹飞") and m.library_id in user_a_lib_ids), None)
    
    if bullets_a is None:
        user_a_movies_titles = [m.title for m in movies if m.library_id in user_a_lib_ids]
        user_a_movies_cn_titles = [m.title_cn for m in movies if m.library_id in user_a_lib_ids]
        raise AssertionError(f"User A's '让子弹飞' not found. Available titles: {user_a_movies_titles}. CN titles: {user_a_movies_cn_titles}")
        
    ua_assets = await seeder.user_asset_repo.find({"movie_id": ObjectId(bullets_a.id)})
    # 2 SCREENSHOT (A), 1 REVIEW (A), 1 NOTE (A), 1 REVIEW (B on A's movie) = 5
    assert len(ua_assets) == 5
    
    screenshots = [a for a in ua_assets if a.type == UserAssetType.SCREENSHOT]
    reviews = [a for a in ua_assets if a.type == UserAssetType.REVIEW]
    notes = [a for a in ua_assets if a.type == UserAssetType.NOTE]
    
    assert len(screenshots) == 2
    assert len(reviews) == 2
    assert len(notes) == 1
    
    # 6. Verify Collections
    collections = await seeder.collection_repo.find({"user_id": ObjectId(user_a.id)})
    names = [c.name for c in collections]
    assert "人生必看" in names
    assert "岁月时光" in names
    assert "周末安排" in names
    
    # Verify content of "周末安排"
    weekend = next((c for c in collections if c.name == "周末安排"), None)
    assert weekend is not None, "'周末安排' collection not found"
    assert len(weekend.movies) == 2

    # 7. Verify Watch History
    history = await seeder.history_repo.find({"user_id": ObjectId(user_a.id)})
    assert len(history) > 0

    # 8. Verify Tasks
    tasks = await seeder.task_repo.find({})
    assert len(tasks) >= 3
    
    # Check for "Network Timeout" task (American Beauty)
    ab_task = next((t for t in tasks if t.error_message == "Network Timeout"), None)
    assert ab_task is not None, "Network Timeout task not found"
    
    # Check for "OOM" task (Gladiator)
    oom_task = next((t for t in tasks if t.error_message == "OOM: Out of Memory"), None)
    assert oom_task is not None, "OOM task not found"
    
