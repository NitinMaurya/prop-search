"""FastAPI app: CORS + /v1 routers + /health. Run: `prop-search-api` (uvicorn)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import router

app = FastAPI(title="prop-search API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


def run():
    """Console-script entry: `prop-search-api`."""
    import os
    import uvicorn
    uvicorn.run("prop_search_api.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", 8000)), reload=False)
