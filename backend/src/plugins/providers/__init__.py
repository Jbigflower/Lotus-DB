"""
插件提供方目录
在此目录下新增具体插件模块（如 tmdb.py、omdb.py、opensubtitles.py 等）
推荐在模块中实现 get_plugins() -> List[BasePlugin] 返回实例，便于配置化构造。
"""