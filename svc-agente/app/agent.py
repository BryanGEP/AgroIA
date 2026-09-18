"""Nucleo del agente AgroIA construido con LangChain.

Arquitectura "tool-ready": hoy el agente solo conversa, pero esta preparado
para agregar herramientas (RAG, reglas, Bayes, vision) en las siguientes
entregas sin reescribir esta capa. Cuando existan herramientas, la lista TOOLS
se llenara y el chain se cambiara por un agente con function calling.
"""
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.config import settings
from app.prompt import SYSTEM_PROMPT
from app.memory import memory

# Aqui se registraran las herramientas del agente en futuras entregas:
#   - Entrega 2: retriever de RAG, motor de reglas (SBR), modulo Bayes.
#   - Entrega 3: modelo de vision (clasificacion de aguacate).
TOOLS = []

_llm = None


def build_llm() -> ChatGroq:
    """Crea el modelo de lenguaje. Cambiar de proveedor aqui no afecta al resto."""
    return ChatGroq(
        model=settings.llm_model,
        api_key=settings.groq_api_key,
        temperature=0.3,
    )


def get_llm() -> ChatGroq:
    """Construye el modelo solo la primera vez que se usa (carga diferida)."""
    global _llm
    if _llm is None:
        _llm = build_llm()
    return _llm


def _to_lc_messages(history):
    """Convierte el historial de memoria a mensajes de LangChain."""
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    for m in history:
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        else:
            messages.append(AIMessage(content=m["content"]))
    return messages


def chat(message: str, session_id: str = "default") -> str:
    """Procesa un mensaje del usuario y devuelve la respuesta del agente."""
    history = memory.get(session_id)
    lc_messages = _to_lc_messages(history)
    lc_messages.append(HumanMessage(content=message))

    response = get_llm().invoke(lc_messages)
    answer = response.content or ""

    memory.add(session_id, "user", message)
    memory.add(session_id, "assistant", answer)
    return answer
