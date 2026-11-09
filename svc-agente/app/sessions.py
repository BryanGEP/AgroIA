"""Conversacion con memoria por session_id, usando SimpleMemory como respaldo.

El agente es sin estado; esta capa es la que lee y escribe el historial cuando el
cliente no lo manda (CLI y demo web). Solo guarda la pregunta y la respuesta si el
agente respondio bien.
"""
from app.agent import AgentReply, chat_with_sources
from app.memory import memory


def reply_with_session(message: str, session_id: str) -> AgentReply:
    history = memory.get(session_id)
    reply = chat_with_sources(message, history)
    memory.add(session_id, "user", message)
    memory.add(session_id, "assistant", reply.answer)
    return reply


def chat_with_session(message: str, session_id: str) -> str:
    return reply_with_session(message, session_id).answer
