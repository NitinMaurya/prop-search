"""FastAPI app: CORS + /v1 routers + /health. Run: `prop-search-api` (uvicorn)."""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import router

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="prop-search API", version="2.0.0")


@app.middleware("http")
async def log_latency(request: Request, call_next):
    """Log every request with its wall-clock latency (ms)."""
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    log.info("%s %s -> %d  %.0f ms", request.method, request.url.path,
             response.status_code, ms)
    response.headers["X-Response-Time-ms"] = f"{ms:.0f}"
    return response


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
