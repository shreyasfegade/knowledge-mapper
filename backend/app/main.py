from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db
from .config import UPLOAD_DIR, CORS_ORIGINS
from .api.upload import router as upload_router
from .api.stream import router as stream_router
from .api.documents import router as documents_router
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()
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
    return {"status": "ok", "version": "0.1.0"}
