"""Microservicio FastAPI que expone el agente AgroIA mediante POST /chat."""
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent import chat

app = FastAPI(title="AgroIA - svc-agente", version="0.1.0")

# CORS abierto para pruebas locales (ajustar en produccion).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
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
    answer = chat(req.message, session_id=session_id)
    return ChatResponse(response=answer, session_id=session_id)
