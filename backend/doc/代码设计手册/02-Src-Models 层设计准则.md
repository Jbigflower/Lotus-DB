```
├── models/               # 数据模型层（Pydantic v2）
│   ├── movies/
│   │   ├── movie_models.py
│   │   ├── asset_models.py
│   │   └── library_models.py
│   ├── users/
│   │   ├── user_models.py
│   │   ├── user_asset_models.py
│   │   └── watch_history_models.py
│   ├── tasks/
│   │   └── task_models.py
│   └── logs/
│       └── log_models.py
```

## 一、整体设计思路

优先为每个代码文件生成相应的 xxxInDB / xxxCreate / xxxUpdate / xxxPageResult
此外注意：

* 不能把数据库字段（如** **`id`、`created_at`）放到 Create 模型里。
* 如果Update 模型直接继承 Base，但没改成可选字段，更新时会覆盖为默认值。
* 可变默认值（如 list、dict），所有实例共享同一个列表。
* Optional 类型与默认值不一致，如Optional[str] = ""，这不是** **`Optional`，是默认空字符串
* 不该暴露更新的字段出现在 Update 模型，如：is_deleted、has-poster

## 二、设计要求

使用 str 而非 自定义的 pyobjectID，我们将在 repo 层进行自动 Pydantic 不支持的类型转换。
除去 id 之外的字段，严格遵循说明文档的要求

## 三、字段说明

`movies`：核心元数据、高频访问字段聚合

> 高频访问、核心元数据聚合在一起，前端展示只需一次查询。
> 对于 poster/backdrop/thumbnail 等高频且唯一资源，直接约定静态路径，减少 join 查询。

```json
示例数据
{
  "_id": ObjectId(),
  "title": "Avengers: Endgame",
  "title_cn": "复仇者联盟4",
  "directors": ["Kaige Chen"],
  "actors": ["Leslie Cheung", "Fengyi Zhang", "Gong Li"],
  "description": "the average heros sum and flight againts mb.",
  "description_cn": "地球的超级英雄们集结起来对抗灭霸的故事。",
  "release_date": "2019-01-05",
  "genres": ["动作", "科幻", "冒险"], // 官方标签
  "metadata": {
    "duration": 181,
    "country": ["USA"],
    "language": "en"
  },
  "has_poster": true,
  "has_backdrop": true,
  "has_thumbnail": true,
  "video_asset_ids": [ObjectId("..."), ObjectId("...")],
  "subtitle_asset_ids": [ObjectId("...")],
  "rating": 8.4,
  "tags": ["年度烂片", "我了个大区"], // 用户标签
  "is_deleted": False, // soft deleted
  "deleted_at": ISODate(),
  "created_at": ISODate(),
  "updated_at": ISODate()
}
```

静态资源约定路径：

```
static/movies/{movie_id}/poster.jpg
static/movies/{movie_id}/backdrop.jpg
static/movies/{movie_id}/thumbnail.jpg
```

---

`assets`：多源资源、衍生资源、版本管理

> 视频、字幕、雪碧图、缩略图、截图等独立管理
> 支持版本控制、权限设置、跨影片/跨库共享
> 衍生资源静态路径约定 + 可选 DB path 字段

```json
{
  "_id": ObjectId,
  "movie_id": ObjectId,
  "library_id": ObjectId,          // 所属媒体库
  "type": "video",                 // video | subtitle | image
  "version": 1,                    // 支持版本管理
  "quality": "4K",
  "codec": "H265",
  "filename": 4kXXX.mkv
  "path": "videos/4kXXX.mkv",         // 原始文件
  "size": 3500000000,
  "duration": 7200,
  "permissions": ["public"],       // 支持独立权限控制
  "shared_across_libraries": false,

  "has_thumbnail": True, // 后台任务进行提取，成功后该位置True
  "has_sprite": True, // 同上
  
  "is_deleted": False, // soft deleted
  "deleted_at": ISODate(),
  "created_at": ISODate,
  "updated_at": ISODate
}
```

静态资源约定路径：

```
static/movies/{movie_id}/{asset_id}/thumbnail.jpg
static/movies/{movie_id}/{asset_id}/sprites/*.jpg
```

---

`user`：基础信息 + 高频收藏/片单内嵌

> 高频访问数据（少量收藏/片单）可内嵌
> 大量收藏/片单建议拆分独立集合 `user_lists` 或 `user_favorites`

```json
{
  "_id": ObjectId,
  "username": "bob",
  "email": "bob@example.com",
  "hashed_password": "xxx",
  "role": ["user"],

  "favorites": [ ObjectId("movie_id1"), ObjectId("movie_id2") ],
  "watchlist": [ ObjectId("movie_id3") ],
  "custom_lists": [
    {
      "list_id": ObjectId,
      "name": "漫威系列",
      "movies": [ ObjectId("movie_id1"), ObjectId("movie_id4") ]
    }
  ],

  "settings": {
    "theme": "light",
    "language": "en-US"
  },
  "is_deleted": False, // soft deleted
  "deleted_at": ISODate(),
  "created_at": ISODate,
  "updated_at": ISODate
}
```

内嵌适合片单数量小于 50、每个片单电影 <1000 部
大量片单/电影 → 独立集合，按 `user_id` 查询。

---

`user_assets`：用户个人创作内容

> 每个 asset 对应单部电影和单版本，支持多版本管理
> 少量跨电影资产使用 `user_asset_relations` 关联表
> 可选在 asset 文档中增加 `related_movie_ids` 字段表示跨电影关联

```json
{
  "_id": ObjectId,
  "user_id": ObjectId,
  "movie_id": ObjectId,          // 单部电影
  "type": "note",                // screenshot | clip | note
  "version": 1,                  // 支持版本管理
  "title": "复仇者联盟系列笔记",
  "content": "Markdown文本内容",
  "files": [
    { "path": "user_assets/bob/notes/screenshot1.png", "kind": "screenshot" },
    { "path": "user_assets/bob/notes/clip1.mp4", "kind": "clip" }
  ],
  "related_movie_ids": [ ObjectId("movie_id2"), ObjectId("movie_id3") ], // 可选
  "is_deleted": False, // soft deleted
  "deleted_at": ISODate(),
  "created_at": ISODate,
  "updated_at": ISODate
}
```

也可以多电影关联单独建立 `user_asset_relations`：

```json
{ "user_asset_id": ObjectId, "movie_id": ObjectId }
```

---

`watch_history`：长尾数据，独立 collection，需要索引优化：`user_id + movie_id` / `movie_id + user_id`

```json
{
  "_id": ObjectId,
  "user_id": ObjectId,
  "movie_id": ObjectId,
  "asset_id": ObjectId,
  "progress": 3200,   // 已观看秒数
  "finished": false,
  "last_watched": ISODate
}
```

---

`tasks`（后台任务 / Celery / 媒体处理），需要索引优化：`status + movie_id + asset_id`

```json
{
  "_id": ObjectId,
  "task_type": "generate_thumbnail",
  "status": "running",            // pending | running | success | failed
  "movie_id": ObjectId,
  "asset_id": ObjectId,
  "progress": 60,
  "created_at": ISODate,
  "updated_at": ISODate,
  "error": null
```

`libraries`：媒体库配置，定义统一存储规则。

```json
{
  "_id": ObjectId,
  "name": "Movie Library A",
  "type": "movie",
  "root_path": "/mnt/media/movies",
  "structure": {
    "movie": "{movie_id}/",
    "poster": "{movie_id}/poster*.jpg",
    "thumbnails": "{movie_id}/thumbs/*.jpg",
    "backdrop": "{movie_id}/backdrop*.jpg",
    "subtitles": "{movie_id}/subs/*.srt",
    "videos": "{movie_id}/videos/*",
  },
  "description": 'MIAOSHU',
  "is_active": True,
  "scan_interval": 3600,
  "auto_import": True,
  "supported_formats": ["mp4", "mkv", "avi", "mov", "wmv", "flv"],
  "is_scanning": False,
  "scan_progress": 0,
  "last_scan_at": datetime,
  "last_scan_result": {
    "scanned_files": 100,
    "added_files": 2,
    "updated_files": 2,
    "removed_files": 3,
    "error_files": 0,
    "scan_duration_seconds": 120,
    "scan_started_at": datetime,
    "scan_completed_at": datetime,
  },
  "is_deleted": False,
  "deleted_at": ISODate(),
  "created_at": ISODate,
  "updated_at": ISODate
}
```
