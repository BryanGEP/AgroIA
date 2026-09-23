"""Microservicio FastAPI que expone el agente AgroIA mediante POST /chat."""
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent import AgentError, chat

app = FastAPI(title="AgroIA - svc-agente", version="0.1.0")

# CORS abierto para pruebas locales (ajustar en produccion).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.get("/health")
def health():
    """Comprobacion de estado del servicio."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """Recibe un mensaje y devuelve la respuesta del agente."""
    session_id = req.session_id or str(uuid.uuid4())
    try:
        answer = chat(req.message, session_id=session_id)
    except AgentError:
        raise HTTPException(
            status_code=503,
            detail="El servicio de IA no está disponible, intenta más tarde",
        )
    return ChatResponse(response=answer, session_id=session_id)
