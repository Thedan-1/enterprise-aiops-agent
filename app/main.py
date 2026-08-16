from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.runtime_factory import build_agent_runtime
from app.api.chat import router as chat_router
from app.core.logging import setup_logging
from app.db.session import SessionLocal, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    session = SessionLocal()
    try:
        app.state.agent_runtime = build_agent_runtime(session)
    finally:
        session.close()
    yield


app = FastAPI(title="Enterprise AIOps Diagnosis Agent", lifespan=lifespan)
app.include_router(chat_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
