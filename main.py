import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pansou_py.api.auth import router as auth_router
from pansou_py.api.search import router as search_router
from pansou_py.api.health import router as health_router
from pansou_py.api.wechat import router as wechat_router
from pansou_py.core.config import settings
from pansou_py.models.database import init_db
from pansou_py.core.scheduler import scheduler
import pansou_py.plugins.core  # Load internal plugins

app = FastAPI(title="PanSou Python API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(search_router, prefix="/api", tags=["Search"])
app.include_router(health_router, prefix="/api", tags=["Health"])
app.include_router(wechat_router, tags=["WeChat"])

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.on_event("startup")
async def startup_event():
    print("🚀 [System] Initializing database...")
    await init_db()
    print("🚀 [System] Starting scheduler...")
    await scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 [System] Stopping scheduler...")
    scheduler.stop()

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/static/index.html")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True
    )
