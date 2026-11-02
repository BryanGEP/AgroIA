"""Herramientas del agente. La logica vive en otros modulos; aqui solo se envuelven.

- buscar_conocimiento (RAG, app/rag.py): explica y fundamenta con la base de conocimiento.
  Devuelve dos cosas (response_format="content_and_artifact"):
  - content: el texto de los fragmentos, que es lo que lee el modelo.
  - artifact: los fragmentos con sus metadatos, que el modelo NO ve. Queda en el
    ToolMessage y de ahi agent.py saca las fuentes para la respuesta de /chat.
- diagnosticar_sintomas y evaluar_huerto (SBR, app/reglas.py): orientan y clasifican
  con reglas deterministicas. Son dos herramientas, una por capacidad, para que el
  modelo sepa cual usar segun lo que describe el productor.
"""
import logging
from dataclasses import asdict
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app import rag, reglas

logger = logging.getLogger(__name__)

SIN_RESULTADOS = "No se encontro informacion sobre eso en la base de conocimiento."
BASE_NO_DISPONIBLE = (
    "ERROR: la base de conocimiento no esta disponible en este momento; no se pudo consultar."
)


def formatear_fragmentos(fragmentos: list[rag.Fragmento]) -> str:
    """Texto que recibe el modelo: cada fragmento con su documento de origen.

    La etiqueta [archivo] es la que el modelo cita en su linea final "FUENTES:" para
    indicar que documentos uso (ver app/prompt.py y agent.split_cited_sources). El
    texto del chunk ya empieza con "titulo > seccion", asi que no se repiten aqui.
    """
    bloques = [f"[{f.archivo}]\n{f.texto}" for f in fragmentos]
    return "\n\n---\n\n".join(bloques)


@tool(response_format="content_and_artifact")
def buscar_conocimiento(consulta: str) -> tuple[str, list[dict]]:
    """Base de conocimiento tecnica del aguacate: riego, suelo, pH, fertilizacion, poda, heladas, plagas, enfermedades, sintomas y manejo. Usala SIEMPRE antes de responder una duda tecnica; no para saludos ni temas ajenos.

    Args:
        consulta: la duda reformulada como pregunta completa en espanol.
    """
    try:
        fragmentos = rag.buscar_conocimiento(consulta)
    except Exception as exc:  # pgvector caido, modelo de embeddings sin cargar, etc.
        logger.error("No se pudo consultar la base de conocimiento: %s", type(exc).__name__)
        return BASE_NO_DISPONIBLE, []
    if not fragmentos:
        return SIN_RESULTADOS, []
    return formatear_fragmentos(fragmentos), [asdict(f) for f in fragmentos]


# --- Sistema basado en reglas (SBR) ---

# Los esquemas y descripciones de las herramientas viajan en cada llamada al LLM:
# se mantienen cortos (ver app/prompt.py).
CodigoSintoma = Literal[tuple(reglas.SINTOMAS)]
_CATALOGO = "; ".join(f"{codigo}: {texto}" for codigo, texto in reglas.SINTOMAS.items())
NO_DOSIS = "Recuerda: orientacion, no tratamiento. No des dosis, productos ni recetas."


class EntradaSintomas(BaseModel):
    sintomas: list[CodigoSintoma] = Field(description="Codigos de los sintomas mencionados. " + _CATALOGO)
    otros_sintomas: str | None = Field(default=None, description="Sintomas que no encajan en ningun codigo.")


class EntradaHuerto(BaseModel):
    ph_suelo: float | None = Field(default=None, description="pH del suelo")
    ph_agua: float | None = Field(default=None, description="pH del agua de riego")
    tipo_suelo: Literal[reglas.TIPOS_SUELO] | None = Field(default=None, description="volcanico = Andosol")
    encharcamiento: bool | None = Field(default=None, description="True si se encharca; False si drena bien")
    edad_arboles: float | None = Field(default=None, description="Anos")
    hectareas: float | None = Field(default=None, description="Solo contexto")


def formatear_diagnostico(diag: reglas.Diagnostico) -> str:
    lineas = ["RESULTADO DEL SISTEMA DE REGLAS (diagnostico orientativo por sintomas)"]
    for c in diag.coincidencias:
        con = c.regla.entonces
        lineas.append(f"\nCausa probable: {con.causa} [gravedad {con.gravedad}]")
        lineas.append(f"- Por que: {con.explicacion}")
        if c.apoyos:
            lineas.append(f"- Lo refuerza: {', '.join(reglas.SINTOMAS[a] for a in c.apoyos)}")
        lineas.append(f"- Siguiente paso: {con.recomendacion}")
        lineas.append(f"- Para explicarla, busca en la base de conocimiento ({con.documento}).")
    for p in diag.parciales:
        faltan = "; ".join(reglas.SINTOMAS[f] for f in p.faltan)
        lineas.append(f"\nPosible (datos incompletos): {p.regla.entonces.causa}. Faltaria confirmar: {faltan}.")
    lineas.append("\nAvisos:")
    lineas += [f"- {a}" for a in diag.avisos]
    lineas.append(NO_DOSIS)
    return "\n".join(lineas)


def formatear_evaluacion(ev: reglas.Evaluacion) -> str:
    lineas = ["RESULTADO DEL SISTEMA DE REGLAS (evaluacion orientativa del huerto)"]
    for h in ev.hallazgos:
        marca = " (rango provisional)" if h.provisional else ""
        lineas.append(f"- {h.parametro} = {h.valor}: {h.estado}{marca} [gravedad {h.gravedad}]. {h.implicacion}")
    for nombre, valor in ev.contexto.items():
        lineas.append(f"- {nombre} = {valor}: solo contexto, no se evalua.")
    lineas.append("\nAvisos:")
    lineas += [f"- {a}" for a in ev.avisos]
    lineas.append(NO_DOSIS)
    return "\n".join(lineas)


@tool(args_schema=EntradaSintomas)
def diagnosticar_sintomas(sintomas: list[str], otros_sintomas: str | None = None) -> str:
    """Orienta la causa probable de SINTOMAS que el productor observa (fruto, hojas, hueso, raices, arbol) con reglas fijas. Indica si los datos son incompletos o ambiguos y cuando acudir a un tecnico. No da tratamientos."""
    try:
        return formatear_diagnostico(reglas.diagnosticar(sintomas, otros_sintomas))
    except ValueError as exc:
        return f"ERROR: {exc}. Usa solo los codigos del catalogo."


@tool(args_schema=EntradaHuerto)
def evaluar_huerto(
    ph_suelo: float | None = None,
    ph_agua: float | None = None,
    tipo_suelo: str | None = None,
    encharcamiento: bool | None = None,
    edad_arboles: float | None = None,
    hectareas: float | None = None,
) -> str:
    """Evalua DATOS del huerto que dio el productor: pH del suelo o del agua, tipo de suelo, si se encharca, edad de los arboles, hectareas. Usala SIEMPRE que de un valor (ej. "el pH de mi suelo es 4.8"), ademas de buscar. Pasa solo esos datos. Rangos orientativos y provisionales; no da correcciones."""
    try:
        ev = reglas.evaluar_parametros(
            ph_suelo=ph_suelo, ph_agua=ph_agua, tipo_suelo=tipo_suelo,
            encharcamiento=encharcamiento, edad_arboles=edad_arboles, hectareas=hectareas,
        )
    except ValueError as exc:
        return f"ERROR: {exc}."
    return formatear_evaluacion(ev)
