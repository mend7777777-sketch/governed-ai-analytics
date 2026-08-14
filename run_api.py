"""ASGI entry point: uvicorn run_api:app --host 127.0.0.1 --port 8010."""

from app.api.main import app as fastapi_app

# Keep an explicit module-level `app` for PyCharm's FastAPI run configuration.
app = fastapi_app

__all__ = ["app"]
