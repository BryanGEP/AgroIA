"""Herramientas del agente. La logica vive en otros modulos; aqui solo se envuelven.

- buscar_conocimiento (RAG, app/rag.py): explica y fundamenta con la base de conocimiento.
  Devuelve dos cosas (response_format="content_and_artifact"):
  - content: el texto de los fragmentos, que es lo que lee el modelo.
  - artifact: los fragmentos con sus metadatos, que el modelo NO ve. Queda en el
    ToolMessage y de ahi agent.py saca las fuentes para la respuesta de /chat.
- diagnosticar_sintomas y evaluar_huerto (SBR, app/reglas.py): orientan y clasifican
  con reglas deterministicas. Son dos herramientas, una por capacidad, para que el
  modelo sepa cual usar segun lo que describe el productor.
- estimar_probabilidades_sintomas (Teorema de Bayes, app/bayes.py): cuantifica la
  incertidumbre cuando hay varios sintomas o son ambiguos. Usa el mismo catalogo de
  sintomas (y el mismo esquema de entrada) que diagnosticar_sintomas.
"""
import logging
from dataclasses import asdict
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app import bayes, rag, reglas

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
# se mantienen cortos (ver app/prompt.py). El catalogo de sintomas con su descripcion
# va UNA sola vez, en el esquema de Bayes (la herramienta de varios sintomas, donde
# importa mas traducir bien lo que describe el productor); diagnosticar_sintomas
# remite a el. Probado: dejar solo los codigos, sin descripciones, hacia que el modelo
# omitiera sintomas que el productor si menciono.
CodigoSintoma = Literal[tuple(reglas.SINTOMAS)]
_CATALOGO = "; ".join(f"{codigo}: {texto}" for codigo, texto in reglas.SINTOMAS.items())
NO_DOSIS = "Orientativo: confirma con un tecnico. No des dosis, productos ni recetas."


class EntradaSintomas(BaseModel):
    sintomas: list[CodigoSintoma] = Field(
        description="Codigos de TODOS los sintomas mencionados (catalogo descrito en estimar_probabilidades_sintomas)."
    )
    otros_sintomas: str | None = Field(default=None, description="Sintomas sin codigo.")


class EntradaSintomasBayes(BaseModel):
    sintomas: list[CodigoSintoma] = Field(description="Codigos de TODOS los sintomas mencionados. " + _CATALOGO)
    otros_sintomas: str | None = Field(default=None, description="Sintomas que no encajan en ningun codigo.")


class EntradaHuerto(BaseModel):
    ph_suelo: float | None = Field(default=None, description="pH del suelo")
    ph_agua: float | None = Field(default=None, description="pH del agua de riego")
    tipo_suelo: Literal[reglas.TIPOS_SUELO] | None = Field(default=None, description="volcanico = Andosol")
    encharcamiento: bool | None = Field(default=None, description="True si se encharca; False si drena bien")
    edad_arboles: float | None = Field(default=None, description="Anos")
    hectareas: float | None = Field(default=None, description="Solo contexto")


def formatear_diagnostico(diag: reglas.Diagnostico) -> str:
    """Lo esencial para redactar: causa, gravedad, siguiente paso y avisos especificos.

    La explicacion de cada causa la da buscar_conocimiento; el aviso generico de
    consultar a un tecnico se resume en NO_DOSIS. El detalle completo va en el artifact.
    """
    lineas = ["REGLAS (orientativo):"]
    for c in diag.coincidencias:
        con = c.regla.entonces
        lineas.append(f"- Causa probable: {con.causa} [gravedad {con.gravedad}]. "
                      f"Siguiente paso: {con.recomendacion} Para explicarla: {con.documento}")
    for p in diag.parciales:
        faltan = "; ".join(reglas.SINTOMAS[f] for f in p.faltan)
        lineas.append(f"- Posible (datos incompletos): {p.regla.entonces.causa}. Faltaria confirmar: {faltan}.")
    lineas += [f"- {a}" for a in diag.avisos if a != reglas.CONSULTA_TECNICO]
    lineas.append(NO_DOSIS)
    return "\n".join(lineas)


def detalle_diagnostico(diag: reglas.Diagnostico) -> dict:
    """Artifact del SBR (el modelo no lo ve): reglas disparadas, apoyos y avisos completos."""
    return {
        "coincidencias": [
            {"regla": c.regla.id, "causa": c.regla.entonces.causa, "explicacion": c.regla.entonces.explicacion,
             "apoyos": c.apoyos, "documento": c.regla.entonces.documento}
            for c in diag.coincidencias
        ],
        "parciales": [{"regla": p.regla.id, "faltan": p.faltan} for p in diag.parciales],
        "avisos": diag.avisos,
    }


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


@tool(args_schema=EntradaSintomas, response_format="content_and_artifact")
def diagnosticar_sintomas(sintomas: list[str], otros_sintomas: str | None = None) -> tuple[str, dict]:
    """Orienta la causa probable de SINTOMAS que el productor observa (fruto, hojas, hueso, raices, arbol) con reglas fijas. Indica si los datos son incompletos o ambiguos y cuando acudir a un tecnico. No da tratamientos."""
    try:
        diag = reglas.diagnosticar(sintomas, otros_sintomas)
    except ValueError as exc:
        return f"ERROR: {exc}. Usa solo los codigos del catalogo.", {}
    return formatear_diagnostico(diag), detalle_diagnostico(diag)


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


# --- Razonamiento probabilistico (Teorema de Bayes) ---

VEREDICTOS = {
    "dominante": "Una causa domina claramente.",
    "probable": "Hay una causa mas probable, pero no es concluyente.",
    "no_concluyente": "No es concluyente: varias causas posibles.",
    "sin_evidencia": "Sin sintomas del catalogo no hay evidencia para estimar.",
}


# El aviso de que las probabilidades son orientativas lo resume la ultima linea; los
# avisos especificos (no concluyente, causa grave, otra causa) si se pasan al modelo.
_AVISO_GENERICO_BAYES = "Probabilidades orientativas y provisionales"


def formatear_estimacion(est: bayes.Estimacion, mostrar: int = 4) -> str:
    """Causas ordenadas por probabilidad (sin las menores a 1 %), veredicto y avisos clave."""
    lineas = ["Teorema de Bayes, P(causa|sintomas), valores orientativos:"]
    for t in est.terminos[:mostrar]:
        if t.posterior < 0.01:
            break
        lineas.append(f"- {bayes.CAUSAS[t.causa].causa}: {t.posterior:.0%}")
    lineas.append(f"Veredicto: {VEREDICTOS[est.veredicto]}")
    if est.terminos:
        lineas.append("Cita cada porcentaje con su causa, tal cual; las causas que no estan aqui no tienen porcentaje.")
        # Igual que las reglas: senala que documento explica la causa principal, para que
        # el modelo la fundamente con buscar_conocimiento en lugar de quedarse en el numero.
        documento = bayes.CAUSAS[est.principal.causa].documento
        if documento:
            lineas.append(f"Para explicar la causa principal, busca en la base de conocimiento ({documento}).")
    lineas += [f"- {a}" for a in est.avisos if not a.startswith(_AVISO_GENERICO_BAYES)]
    lineas.append("Probabilidades orientativas, no un diagnostico. " + NO_DOSIS)
    return "\n".join(lineas)


def detalle_estimacion(est: bayes.Estimacion) -> dict:
    """Artifact de Bayes (el modelo no lo ve): el calculo completo, causa por causa."""
    return {
        "sintomas": est.sintomas,
        "evidencia_P(S)": est.evidencia,
        "veredicto": est.veredicto,
        "terminos": [
            {"causa": t.causa, "prior_P(C)": t.prior, "verosimilitud_P(S|C)": t.verosimilitud,
             "numerador_P(S|C)P(C)": t.no_normalizado, "posterior_P(C|S)": t.posterior}
            for t in est.terminos
        ],
        "avisos": est.avisos,
    }


@tool(args_schema=EntradaSintomasBayes, response_format="content_and_artifact")
def estimar_probabilidades_sintomas(sintomas: list[str], otros_sintomas: str | None = None) -> tuple[str, dict]:
    """Estima con el Teorema de Bayes la PROBABILIDAD de cada causa (antracnosis, rona, trips, acaros, barrenador, Phytophthora u otra) cuando hay VARIOS sintomas o son AMBIGUOS. Devuelve las causas de mayor a menor probabilidad y si el resultado es concluyente. Valores orientativos; no da tratamientos."""
    try:
        est = bayes.estimar(sintomas)
    except ValueError as exc:
        return f"ERROR: {exc}. Usa solo los codigos del catalogo.", {}
    texto = formatear_estimacion(est)
    if otros_sintomas and otros_sintomas.strip():
        texto += f"\nNo evaluados (fuera del catalogo): {otros_sintomas.strip()}."
    return texto, detalle_estimacion(est)
