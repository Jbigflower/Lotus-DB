from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html


def custom_openapi(app):
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # ✅ 确保 components 存在
    if "components" not in schema:
        schema["components"] = {}

    if "securitySchemes" not in schema["components"]:
        schema["components"]["securitySchemes"] = {}

    # ✅ 不覆盖已有的 OAuth2PasswordBearer，而是追加自定义的 BearerAuth
    schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    # ✅ 不强制全局 security，除非你确实希望所有接口都默认带 Bearer
    # schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = schema
    return schema


def custom_swagger_ui(app):
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_ui_parameters={
            "persistAuthorization": True,
            "displayRequestDuration": True,
        },
    )
