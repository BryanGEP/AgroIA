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


# --- Sistema basado en reglas (SBR) ---

CodigoSintoma = Literal[tuple(reglas.SINTOMAS)]
_CATALOGO = "\n".join(f"- {codigo}: {texto}" for codigo, texto in reglas.SINTOMAS.items())
NO_DOSIS = "Recuerda: orientacion, no tratamiento. No des dosis, productos ni recetas."


class EntradaSintomas(BaseModel):
    sintomas: list[CodigoSintoma] = Field(
        description="Codigos de los sintomas que describe el productor (solo los que "
        "menciona, sin suponer otros):\n" + _CATALOGO
    )
    otros_sintomas: str | None = Field(
        default=None,
        description="Sintomas descritos que no encajan en ningun codigo, en texto breve.",
    )


class EntradaHuerto(BaseModel):
    ph_suelo: float | None = Field(default=None, description="pH del suelo (0 a 14).")
    ph_agua: float | None = Field(default=None, description="pH del agua de riego (0 a 14).")
    tipo_suelo: Literal[reglas.TIPOS_SUELO] | None = Field(
        default=None,
        description="Textura del suelo. 'volcanico' = Andosol (tierra de migajon volcanica).",
    )
    encharcamiento: bool | None = Field(
        default=None,
        description="True si el suelo se encharca o tarda en secarse; False si drena bien.",
    )
    edad_arboles: float | None = Field(default=None, description="Edad de los arboles en anos.")
    hectareas: float | None = Field(default=None, description="Superficie del huerto (solo contexto).")


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
    """Orienta sobre la causa probable de lo que el productor OBSERVA en su huerto.

    Usala cuando el productor describa sintomas en frutos, hojas, hueso, raices o el
    arbol (manchas, costras, hojas bronceadas, galerias en el hueso, marchitez...).
    Traduce lo que describe a los codigos del catalogo. Aplica reglas fijas (SI ... ENTONCES)
    y devuelve la causa probable, si los datos son incompletos o ambiguos, y cuando
    acudir a un tecnico. Despues puedes usar buscar_conocimiento para explicar la causa.
    No da dosis ni tratamientos.
    """
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
    """Evalua DATOS o parametros del huerto que da el productor y dice si estan bien.

    Usala cuando el productor de valores o caracteristicas de su huerto: pH del suelo o
    del agua de riego, tipo de suelo (arcilloso, arenoso, franco, volcanico), si se
    encharca, edad de los arboles o hectareas. Pasa solo los datos que dio, sin inventar
    los demas. Clasifica cada dato con rangos orientativos y provisionales, y recuerda
    confirmarlos con un analisis de laboratorio y un tecnico. No da dosis ni correcciones.
    """
    try:
        ev = reglas.evaluar_parametros(
            ph_suelo=ph_suelo, ph_agua=ph_agua, tipo_suelo=tipo_suelo,
            encharcamiento=encharcamiento, edad_arboles=edad_arboles, hectareas=hectareas,
        )
    except ValueError as exc:
        return f"ERROR: {exc}."
    return formatear_evaluacion(ev)
