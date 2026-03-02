from fastapi import APIRouter

from src.routers.auth import router as auth_router

from src.routers.libraries import router as libraries_router
from src.routers.movies import router as movies_router
from src.routers.movie_assets import router as movie_assets_router

from src.routers.system import router as system_router
from src.routers.tasks import router as tasks_router

from src.routers.users import router as users_router
from src.routers.user_assets import router as user_assets_router
from src.routers.user_collections import router as user_collections_router
from src.routers.player import router as player_router
from src.routers.llm import router as llm_router

from src.routers.search import router as search_router


def register_routers(app):
    routers = [
        users_router,
        auth_router,
        libraries_router,
        movies_router,
        movie_assets_router,
        tasks_router,
        system_router,
        user_assets_router,
        user_collections_router,
        player_router,
        search_router,
        llm_router,
    ]
    for r in routers:
        app.include_router(r)
