"""Run API Service.
"""

import fastapi

api_app = fastapi.FastAPI(title="InKCre")

@api_app.get("/heartbeat")
def heartbeat():
    """Check if the API is running."""
    return {"status": "ok"}

from .business.block import BLOCK_ROUTER
api_app.include_router(BLOCK_ROUTER)