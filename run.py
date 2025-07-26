"""Run API Service.
"""

import fastapi
import uvicorn

api_app = fastapi.FastAPI(title="InKCre")

@api_app.get("/heartbeat")
def heartbeat():
    """Check if the API is running."""
    return {"status": "ok"}

from app.business.block import BLOCK_ROUTER
api_app.include_router(BLOCK_ROUTER)


if __name__ == "__main__":
    uvicorn.run(
        api_app,
        host="0.0.0.0", port=8000
    )