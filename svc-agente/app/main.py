"""Microservicio FastAPI que expone el agente AgroIA mediante POST /chat."""
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import AgentError, chat
from app.sessions import chat_with_session

# Maximo de mensajes de historial que acepta /chat en una peticion.
MAX_HISTORY = 50

app = FastAPI(title="AgroIA - svc-agente", version="0.1.0")

# CORS abierto para pruebas locales (ajustar en produccion).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    # Opcional. Si viene, el agente usa este historial y el servidor no guarda nada.
    # Si no viene, se usa la memoria del servidor por session_id (CLI y demo web).
    history: list[HistoryMessage] | None = Field(default=None, max_length=MAX_HISTORY)


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.get("/health")
def health():
    """Comprobacion de estado del servicio."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """Recibe un mensaje y devuelve la respuesta del agente.

    Con `history`, el agente responde con ese contexto y no se guarda nada en el
    servidor. Sin `history`, se usa y se actualiza la memoria del `session_id`.
    """
    session_id = req.session_id or str(uuid.uuid4())
    try:
        if req.history is not None:
            answer = chat(req.message, [m.model_dump() for m in req.history])
        else:
            answer = chat_with_session(req.message, session_id)
    except AgentError:
        raise HTTPException(
            status_code=503,
            detail="El servicio de IA no está disponible, intenta más tarde",
        )
    return ChatResponse(response=answer, session_id=session_id)


# Monta el front web (index.html, styles.css, app.js) en la raiz.
# Va al final para que /health y /chat se resuelvan antes que el static files.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
