"""
Admin Server — FastAPI backend for AI-Content-Hub management UI.

Run from the project root:
    uvicorn admin-server.main:app --host 127.0.0.1 --port 8765 --reload

Or from admin-server/ directory:
    uvicorn main:app --host 127.0.0.1 --port 8765 --reload
"""
import logging
import logging.handlers
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Make project root importable for db package
sys.path.insert(0, str(Path(__file__).parent.parent))
# Make middleware package importable for handler singletons
sys.path.insert(0, str(Path(__file__).parent.parent / "middleware"))

import db
from db.migrate import run_migrations

from routers import plans, contents, publish, logs, sync, stats, skus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            filename=Path(__file__).parent.parent / "logs" / "admin.log",
            maxBytes=10 * 1024 * 1024,   # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI-Content-Hub Admin",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8765", "http://127.0.0.1:8765"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    run_migrations()
    engine = db._get_engine()
    db.init_engine(engine)
    logger.info("Admin DB ready: %s", engine.url)
    _init_handler_singletons(app)


def _init_handler_singletons(app):
    """Load middleware handlers into app.state for background task execution."""
    try:
        from core.config import load_system, load_model_params
        from adapters.feishu import FeishuClient
        from core.local_storage import LocalStorage
        from handlers.content_generation import ContentGenerationHandler
        from handlers.publish import PublishHandler
        from handlers.material_migration import MaterialMigrationHandler

        sys_cfg = load_system()
        feishu_cfg = sys_cfg["feishu"]
        feishu = FeishuClient(
            app_id=feishu_cfg["app_id"],
            app_secret=feishu_cfg["app_secret"],
            base_token=feishu_cfg["base_token"],
        )
        tables = feishu_cfg["tables"]
        storage = LocalStorage(root=sys_cfg.get("local_storage", {}).get("root"))
        model_params = load_model_params()
        publish_cfg = sys_cfg.get("publish", {})
        notif_cfg = sys_cfg.get("notifications", {})

        app.state.feishu = feishu
        app.state.tables = tables
        app.state.storage = storage
        app.state.model_params = model_params
        app.state.gen_handler = ContentGenerationHandler(feishu, tables, model_params, storage)
        app.state.pub_handler = PublishHandler(feishu, tables, storage, publish_cfg, notif_cfg)
        app.state.migrate_handler = MaterialMigrationHandler(feishu, tables, storage)
        app.state.handlers_ready = True
        logger.info("Handler singletons initialized OK")
    except Exception as exc:
        logger.warning("Handler singletons NOT available (graceful degradation): %s", exc)
        app.state.handlers_ready = False
        app.state.feishu = None
        app.state.tables = {}
        app.state.gen_handler = None
        app.state.pub_handler = None
        app.state.migrate_handler = None


# Mount API routers
app.include_router(plans.router, prefix="/api/v1/plans", tags=["plans"])
app.include_router(contents.router, prefix="/api/v1/contents", tags=["contents"])
app.include_router(publish.router, prefix="/api/v1/publish", tags=["publish"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["logs"])
app.include_router(sync.router, prefix="/api/v1/sync", tags=["sync"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(skus.router, prefix="/api/v1/skus", tags=["skus"])


# Serve the simple HTML admin UI
templates_dir = Path(__file__).parent / "templates"


@app.get("/", response_class=HTMLResponse)
def index():
    html = (templates_dir / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)
