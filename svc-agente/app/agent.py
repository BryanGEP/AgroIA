"""Nucleo del agente AgroIA construido con LangChain.

El agente es SIN ESTADO: recibe el historial de la conversacion desde afuera y no
guarda nada. Quien lo llama (el endpoint /chat, el CLI o, mas adelante, el servicio
de gestion con la base de datos) decide donde vive el historial.

El flujo esta separado en piezas:
    build_messages -> invoke_model -> extract_answer (+ extract_sources)

invoke_model usa create_agent de LangChain: el modelo decide si llama a las
herramientas de TOOLS (la busqueda en la base de conocimiento del RAG y las dos del
sistema basado en reglas) y se
devuelve la conversacion completa, con los mensajes intermedios de las herramientas.
extract_answer toma la respuesta final y extract_sources junta las fuentes de los
fragmentos que recupero la herramienta.
"""
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_groq import ChatGroq

from app.config import settings
from app.prompt import SYSTEM_PROMPT
from app.tools import (
    buscar_conocimiento,
    diagnosticar_sintomas,
    estimar_probabilidades_sintomas,
    evaluar_huerto,
)

logger = logging.getLogger(__name__)

# Herramientas del agente: RAG (explica y fundamenta), SBR (orienta y clasifica) y
# Bayes (cuantifica la incertidumbre). Siguiente: en la Entrega 3, el modelo de vision.
TOOLS = [buscar_conocimiento, diagnosticar_sintomas, evaluar_huerto, estimar_probabilidades_sintomas]

# Tope de pasos del agente (cada busqueda son 2: la llamada a la herramienta y su
# resultado). Evita que el modelo se quede buscando en bucle.
MAX_AGENT_STEPS = 10

# Formato del historial: [{"role": "user" | "assistant", "content": "..."}]
History = Sequence[dict]

_llm = None


class AgentError(Exception):
    """Error de dominio: el agente no pudo generar una respuesta valida."""


@dataclass
class AgentReply:
    """Respuesta final del agente y las fuentes de lo que consulto para darla."""

    answer: str
    sources: list[str] = field(default_factory=list)


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


def build_agent():
    """Agente con herramientas. El prompt del sistema ya viene como primer mensaje
    (build_messages), por eso no se pasa system_prompt aqui."""
    return create_agent(model=get_llm(), tools=TOOLS)


def invoke_model(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Corre el agente y devuelve todos los mensajes (entrada, herramientas y respuesta).

    Cualquier fallo (red, timeout, proveedor, demasiados pasos) se vuelve AgentError.
    Un fallo de la base de conocimiento NO llega aqui: la herramienta lo convierte en
    un aviso para el modelo (ver app/tools.py).
    """
    try:
        result = build_agent().invoke(
            {"messages": messages}, config={"recursion_limit": MAX_AGENT_STEPS}
        )
    except Exception as exc:
        logger.error("Fallo al invocar el agente: %s", type(exc).__name__)
        raise AgentError("El LLM no respondio correctamente") from exc
    return result["messages"]


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


# Linea final con los documentos usados: "FUENTES: riego/x.md, suelo/y.md" o "FUENTES: ninguna"
_SOURCES_LINE = re.compile(r"^[\s*_]*fuentes[\s*_]*:[\s*_]*(.*?)[\s*_]*$", re.IGNORECASE)


def split_cited_sources(answer: str) -> tuple[str, set[str] | None]:
    """Separa la linea final "FUENTES: ..." que pide el prompt del resto de la respuesta.

    Devuelve (texto sin esa linea, archivos citados). Los archivos citados son None si
    el modelo no escribio la linea, y un conjunto vacio si escribio "ninguna".
    Tolera adornos de Markdown como **FUENTES:** o etiquetas entre `comillas`.
    """
    cited: set[str] | None = None
    kept = []
    for line in answer.splitlines():
        match = _SOURCES_LINE.match(line)
        if match is None:
            kept.append(line)
            continue
        items = [i.strip(" `*_[]") for i in match.group(1).split(",")]
        cited = (cited or set()) | {i for i in items if i and i.lower() != "ninguna"}
    if cited is not None:
        # El modelo a veces separa la linea con una regla de Markdown ("---"): se quita.
        while kept and kept[-1].strip() in ("", "---", "***", "___"):
            kept.pop()
    return "\n".join(kept).strip(), cited


def extract_sources(messages: Sequence[BaseMessage], cited: set[str] | None = None) -> list[str]:
    """Fuentes (sin repetir, en orden) de los fragmentos que devolvio buscar_conocimiento.

    cited: archivos que el modelo dijo haber usado. Si es None (no escribio la linea
    FUENTES), se toman todos los fragmentos consultados. Solo cuentan las busquedas de
    este turno: el historial entra como texto, sin resultados de herramientas.
    """
    fragments = [
        fragment
        for m in messages
        if isinstance(m, ToolMessage) and m.name == buscar_conocimiento.name
        for fragment in m.artifact or []
    ]
    if cited is not None:
        # El modelo a veces acorta o altera la etiqueta ("antracnosis.md", "roña.md"),
        # por eso se compara solo el nombre del archivo, sin carpeta ni acentos.
        keys = {_doc_key(c) for c in cited}
        used = [f for f in fragments if _doc_key(f.get("archivo", "")) in keys]
        # Citó algo que no se puede ubicar: mejor todas las consultadas que ninguna.
        fragments = used if used or not cited else fragments

    sources: list[str] = []
    for fragment in fragments:
        for source in fragment.get("fuentes", []):
            if source not in sources:
                sources.append(source)
    return sources


def _doc_key(label: str) -> str:
    """'enfermedades/Roña.md' -> 'rona': nombre del archivo sin carpeta, extension ni acentos."""
    name = label.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()
    name = name.removesuffix(".md")
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()


def chat_with_sources(message: str, history: History | None = None) -> AgentReply:
    """Responde un mensaje usando el historial que recibe y devuelve sus fuentes.

    history: mensajes anteriores [{"role": "user" | "assistant", "content": ...}].
    Lanza AgentError si el LLM falla o la respuesta final viene vacia.
    """
    messages = build_messages(message, history)
    result = invoke_model(messages)
    answer, cited = split_cited_sources(extract_answer(result))
    if not answer:
        logger.error("El LLM solo devolvio la linea de fuentes")
        raise AgentError("El LLM devolvio una respuesta vacia")
    return AgentReply(answer=answer, sources=extract_sources(result, cited))


def chat(message: str, history: History | None = None) -> str:
    """Igual que chat_with_sources, pero solo el texto. No guarda nada."""
    return chat_with_sources(message, history).answer
