from contextlib import asynccontextmanager
import asyncio
import base64
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.agent import Agent
from core.commands import handle_command
from core import notifier
from memory import archive, long_term
from memory.db import init_db
from memory.migrations import run_migrations
from scheduler.jobs import start_scheduler
from voice import stt, tts


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


init_db()
run_migrations()
agent = Agent()
agent_lock = Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    notifier.add_sink(notifier.print_sink)
    notifier.add_sink(notifier.desktop_sink)
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Rubi Assistant API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"ok": True, "service": "rubi-api", "model_profile": agent.llm.profile}


@app.post("/chat")
def chat(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")
    with agent_lock:
        return {"reply": agent.chat(message)}


@app.post("/command")
def command(request: ChatRequest):
    message = request.message.strip()
    if not message.startswith("/"):
        raise HTTPException(status_code=400, detail="command must start with '/'")
    with agent_lock:
        return {"reply": handle_command(agent, message)}


@app.post("/voice")
async def voice_message(audio: UploadFile = File(...)):
    """Transcribe a voice message, chat with Rubi, and return a voice reply."""
    if audio.content_type and not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="uploaded file must be audio")

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="uploaded audio is empty")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="audio file is too large")

    filename = audio.filename or "voice.wav"
    transcript = await asyncio.to_thread(stt.transcribe, data, filename)
    if not transcript:
        return {"transcript": "", "reply": "I could not hear any speech.", "audio": None}

    with agent_lock:
        reply = await asyncio.to_thread(agent.chat, transcript)

    audio_path = None
    try:
        audio_path = await asyncio.to_thread(
            tts.synthesize, reply, agent.llm.mode == "ollama"
        )
        encoded = base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
        mime = "audio/wav" if str(audio_path).endswith(".wav") else "audio/mpeg"
        return {
            "transcript": transcript,
            "reply": reply,
            "audio": {"mime": mime, "base64": encoded},
        }
    except Exception as error:
        return {
            "transcript": transcript,
            "reply": reply,
            "audio": None,
            "audio_error": str(error),
        }
    finally:
        if audio_path is not None:
            Path(audio_path).unlink(missing_ok=True)


@app.get("/memory")
def memories(limit: int = 50):
    return {"memories": long_term.list_memories(limit=max(1, min(limit, 200)))}


@app.post("/memory/search")
def memory_search(request: SearchRequest):
    return {"memories": long_term.search_memories(request.query)}


@app.get("/archive/search")
def archive_search(query: str, limit: int = 10):
    if not query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")
    return {"items": archive.search_archive(query, limit=max(1, min(limit, 50)))}
