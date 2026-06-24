from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db
from .examples_seed import seed_examples
from .config import UPLOAD_DIR, CORS_ORIGINS
from .api.upload import router as upload_router
from .api.stream import router as stream_router
from .api.documents import router as documents_router
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()
    # Seed bundled example graphs so the demo has instant, zero-key content even
    # on a fresh (ephemeral) database.
    seed_examples()
    yield


app = FastAPI(
    title="Conceptual Knowledge Mapping Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(stream_router)
app.include_router(documents_router)


@app.get("/health")
async def health():
    # server_has_key tells the frontend whether uploads work out of the box or
    # whether a visitor must supply their own key (bring-your-own-key).
    from .services.deepseek_client import server_has_key

    return {"status": "ok", "version": "0.1.0", "server_has_key": server_has_key()}
