"""Nucleo del agente AgroIA construido con LangChain.

El agente es SIN ESTADO: recibe el historial de la conversacion desde afuera y no
guarda nada. Quien lo llama (el endpoint /chat, el CLI o, mas adelante, el servicio
de gestion con la base de datos) decide donde vive el historial.

El flujo esta separado en piezas para que el RAG y las herramientas entren limpio:
    build_messages -> invoke_model -> extract_answer

Arquitectura "tool-ready": hoy el agente solo conversa. Cuando existan
herramientas, la lista TOOLS se llenara y invoke_model pasara a un agente con
function calling; extract_answer ya lee el ultimo AIMessage y tolera los mensajes
intermedios de las herramientas.
"""
import logging
from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.config import settings
from app.prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Aqui se registraran las herramientas del agente en futuras entregas:
#   - Entrega 2: retriever de RAG, motor de reglas (SBR), modulo Bayes.
#   - Entrega 3: modelo de vision (clasificacion de aguacate).
TOOLS = []

# Formato del historial: [{"role": "user" | "assistant", "content": "..."}]
History = Sequence[dict]

_llm = None


class AgentError(Exception):
    """Error de dominio: el agente no pudo generar una respuesta valida."""


def build_llm() -> ChatGroq:
    """Crea el modelo de lenguaje. Cambiar de proveedor aqui no afecta al resto.

    timeout y max_retries son explicitos para que una peticion nunca se quede
    colgada indefinidamente esperando a Groq.
    """
    return ChatGroq(
        model=settings.llm_model,
        api_key=settings.groq_api_key,
        temperature=0.3,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


def get_llm() -> BaseChatModel:
    """Construye el modelo solo la primera vez que se usa (carga diferida)."""
    global _llm
    if _llm is None:
        _llm = build_llm()
    return _llm


def build_messages(message: str, history: History | None = None) -> list[BaseMessage]:
    """Arma la conversacion para el modelo: prompt del sistema + historial + mensaje nuevo."""
    messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    for m in history or []:
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        else:
            messages.append(AIMessage(content=m["content"]))
    messages.append(HumanMessage(content=message))
    return messages


def invoke_model(messages: list[BaseMessage]) -> BaseMessage:
    """Llama al modelo. Cualquier fallo (red, timeout, proveedor) se vuelve AgentError."""
    try:
        return get_llm().invoke(messages)
    except Exception as exc:
        logger.error("Fallo al invocar el LLM: %s", type(exc).__name__)
        raise AgentError("El LLM no respondio correctamente") from exc


def _content_to_text(content) -> str:
    """Convierte el content de un mensaje a texto.

    content puede ser un string o una lista de bloques (por ejemplo con tool-calling o
    razonamiento): se juntan solo los bloques de texto y se ignora lo demas.
    """
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def extract_answer(result: BaseMessage | Sequence[BaseMessage]) -> str:
    """Devuelve el texto de la respuesta FINAL al usuario.

    Acepta un solo mensaje o la lista de mensajes que devolvera un agente con
    herramientas; en ese caso usa el ultimo AIMessage. Los mensajes intermedios con
    tool_calls y content vacio no cuentan como error: solo falla si la respuesta
    final esta vacia.
    """
    messages = [result] if isinstance(result, BaseMessage) else list(result)
    final = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if final is None:
        logger.error("El LLM no devolvio ningun mensaje de respuesta")
        raise AgentError("El LLM no devolvio ningun mensaje de respuesta")

    answer = _content_to_text(final.content).strip()
    if not answer:
        logger.error("El LLM devolvio una respuesta final vacia")
        raise AgentError("El LLM devolvio una respuesta vacia")
    return answer


def chat(message: str, history: History | None = None) -> str:
    """Responde un mensaje usando el historial que recibe. No guarda nada.

    history: mensajes anteriores [{"role": "user" | "assistant", "content": ...}].
    Lanza AgentError si el LLM falla o la respuesta final viene vacia.
    """
    messages = build_messages(message, history)
    result = invoke_model(messages)
    return extract_answer(result)
