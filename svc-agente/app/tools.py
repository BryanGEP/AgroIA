"""Herramientas del agente. La logica vive en otros modulos; aqui solo se envuelven.

buscar_conocimiento devuelve dos cosas (response_format="content_and_artifact"):
- content: el texto de los fragmentos, que es lo que lee el modelo.
- artifact: los fragmentos con sus metadatos, que el modelo NO ve. Queda en el
  ToolMessage y de ahi agent.py saca las fuentes para la respuesta de /chat.
"""
import logging
from dataclasses import asdict

from langchain_core.tools import tool

from app import rag

logger = logging.getLogger(__name__)

SIN_RESULTADOS = "No se encontro informacion sobre eso en la base de conocimiento."
BASE_NO_DISPONIBLE = (
    "ERROR: la base de conocimiento no esta disponible en este momento; no se pudo consultar."
)


def formatear_fragmentos(fragmentos: list[rag.Fragmento]) -> str:
    """Texto que recibe el modelo: cada fragmento con su documento de origen.

    La etiqueta [archivo] es la que el modelo cita en su linea final "FUENTES:" para
    indicar que documentos uso (ver app/prompt.py y agent.split_cited_sources).
    """
    bloques = [
        f"[{f.archivo}] Documento: {f.titulo} (seccion: {f.seccion})\n{f.texto}"
        for f in fragmentos
    ]
    return "\n\n---\n\n".join(bloques)


@tool(response_format="content_and_artifact")
def buscar_conocimiento(consulta: str) -> tuple[str, list[dict]]:
    """Busca en la base de conocimiento tecnica de AgroIA sobre el cultivo del aguacate.

    Usala SIEMPRE antes de responder cualquier duda tecnica sobre el aguacate: riego,
    suelo, pH, fertilizacion, poda, heladas, plagas (barrenadores, trips, acaros) o
    enfermedades (antracnosis, rona, pudricion de raiz), sintomas que describe el
    productor y su manejo. No la uses para saludos, agradecimientos ni temas ajenos
    al aguacate.

    Args:
        consulta: la duda del productor reformulada como pregunta completa y concreta,
            en espanol (por ejemplo "¿Que sintomas tiene la rona del aguacate?").
    """
    try:
        fragmentos = rag.buscar_conocimiento(consulta)
    except Exception as exc:  # pgvector caido, modelo de embeddings sin cargar, etc.
        logger.error("No se pudo consultar la base de conocimiento: %s", type(exc).__name__)
        return BASE_NO_DISPONIBLE, []
    if not fragmentos:
        return SIN_RESULTADOS, []
    return formatear_fragmentos(fragmentos), [asdict(f) for f in fragmentos]
