"""Conversacion con memoria por session_id, usando SimpleMemory como respaldo.

El agente es sin estado; esta capa es la que lee y escribe el historial cuando el
cliente no lo manda (CLI y demo web). Solo guarda la pregunta y la respuesta si el
agente respondio bien.
"""
from app.agent import chat
from app.memory import memory


def chat_with_session(message: str, session_id: str) -> str:
    history = memory.get(session_id)
    answer = chat(message, history)
    memory.add(session_id, "user", message)
    memory.add(session_id, "assistant", answer)
    return answer
