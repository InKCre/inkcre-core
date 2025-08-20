"""Run API Service.
"""

import contextlib
import fastapi
import uvicorn


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    from app.task import scheduler
    scheduler.start()
    yield
    scheduler.shutdown(wait=True)
    await ExtensionManager.close_all()

from app.business.block import BLOCK_ROUTER
api_app.include_router(BLOCK_ROUTER)
api_app = fastapi.FastAPI(title="InKCre", lifespan=lifespan)

from app.business.source import SourceManager  # noqa: E402
source_router = fastapi.APIRouter(prefix="/source", tags=["sources"])
source_router.get("/{source_id}/collect")(SourceManager.run_a_collect)
api_app.include_router(source_router)
SourceManager.set_up_collect_jobs()


if __name__ == "__main__":
    uvicorn.run(
        api_app,
        host="0.0.0.0", port=8000
    )