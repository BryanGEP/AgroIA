"""Razonamiento probabilistico con el Teorema de Bayes para el diagnostico por sintomas.

Modulo PURO: no usa el LLM ni depende del agente. La herramienta de app/tools.py lo
envuelve. Complementa al sistema de reglas (app/reglas.py): las reglas clasifican de
forma determinista cuando el caso es claro; este modulo CUANTIFICA LA INCERTIDUMBRE
cuando hay varios sintomas o son ambiguos ("antracnosis 65 %, rona 30 %...").

Teorema de Bayes, para cada causa C y el conjunto de sintomas observados S:

                    P(S | C) * P(C)
    P(C | S)  =  ---------------------          P(S) = suma sobre C de P(S | C) * P(C)
                          P(S)

    - P(C)      prior: que tan comun es la causa antes de ver los sintomas.
    - P(S | C)  verosimilitud: que tan probable es ver esos sintomas si la causa es C.
    - P(C | S)  posterior: probabilidad de la causa dados los sintomas.
    - P(S)      evidencia: constante de normalizacion para que los posteriores sumen 1.

Supuesto de Bayes ingenuo (naive Bayes): los sintomas son independientes dada la
causa, asi que P(S | C) = producto de P(s | C) para cada sintoma s observado.

Solo cuentan los sintomas REPORTADOS. Que el productor no mencione un sintoma no
significa que no este, asi que no se usa como evidencia en contra.

ADVERTENCIA - PROBABILIDADES ORIENTATIVAS Y PROVISIONALES
Los priors y las verosimilitudes de las tablas de abajo NO son datos clinicos ni
epidemiologicos medidos. Son una escala cualitativa (muy alta, alta, media, baja)
derivada de la base de conocimiento (conocimiento/enfermedades/ y riego/) y
convertida a numeros fijos. Sirven para ordenar las causas y expresar la duda, no
como un porcentaje exacto. Deben calibrarse con un especialista o con datos de campo
antes de usarse para decisiones. El resultado no sustituye un diagnostico
profesional ni de laboratorio, y nunca indica dosis ni tratamientos.
"""
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.reglas import ALTA as GRAVEDAD_ALTA
from app.reglas import REGLAS_SINTOMAS, SINTOMAS, Conclusion

# ---------------------------------------------------------------------------
# Escala cualitativa -> numero. Usar pocos niveles fijos evita aparentar una
# precision que no tenemos. MUY_BAJA no es cero: un sintoma raro para una causa no
# la descarta del todo (un cero anularia el producto de Bayes).
# ---------------------------------------------------------------------------
MUY_ALTA = 0.9
ALTA = 0.7
MEDIA = 0.4
BAJA = 0.15
MUY_BAJA = 0.01  # valor por omision: sintoma no relacionado con la causa

# Prior P(C): que tan comun es cada causa en huertas de Michoacan, en tres niveles.
COMUN = 3
MODERADA = 2
POCO_COMUN = 1

# Umbrales para describir el resultado.
DOMINANTE = 0.80        # una causa concentra la probabilidad
PROBABLE = 0.50         # la mas probable, pero conviene confirmar
# Por debajo de PROBABLE: no concluyente, varias causas posibles.

# Nombre y documento de cada causa: se reutilizan del sistema de reglas para que las
# dos herramientas hablen de las mismas causas.
CAUSAS: dict[str, Conclusion] = {r.id: r.entonces for r in REGLAS_SINTOMAS}

# El catalogo no cubre todo lo que puede enfermar un arbol. Sin esta causa el modelo
# seria un "mundo cerrado": un sintoma general (como marchitez) se atribuiria con
# mucha seguridad a la unica causa del catalogo que lo explica.
OTRA = "otra"
CAUSAS[OTRA] = Conclusion(
    causa="Otra causa no incluida en el catalogo (estres hidrico, nutricion, otros hongos o plagas)",
    explicacion="Los sintomas tambien pueden deberse a algo que este modelo no evalua.",
    recomendacion="Consulta a un tecnico para revisar otras causas posibles.",
)

# Sintomas tan caracteristicos que casi solo los explica su propia causa: para "otra"
# valen MUY_BAJA; cualquier otro sintoma vale BAJA para "otra" (puede tener muchos origenes).
SINTOMAS_ESPECIFICOS = {
    "hueso_danado_galerias",
    "hojas_manchas_plateadas_enves_telaranas",
    "costras_corchosas_levantadas",
    "fruto_esporas_rosadas",
    "fruto_exudado_o_aserrin",
    "fruto_cicatrices_asperas",
}


# ---------------------------------------------------------------------------
# P(C): priors (frecuencia relativa cualitativa) y por que
# ---------------------------------------------------------------------------
PRIORS_CUALITATIVOS: dict[str, tuple[int, str]] = {
    "antracnosis": (COMUN, "La principal enfermedad del fruto en poscosecha (antracnosis.md)."),
    "rona": (COMUN, "Presente en toda la region aguacatera de Michoacan (rona.md)."),
    "trips": (COMUN, "Una de las principales plagas del aguacate en Mexico (trips.md)."),
    "arana_roja": (COMUN, "Plaga importante en Hass, con altas densidades ano con ano (arana-roja.md)."),
    "acaro_persea": (MODERADA, "Presente, con menos estudios en Michoacan que la arana roja (arana-roja.md)."),
    "phytophthora": (MODERADA, "La enfermedad de raiz mas grave; ligada a suelos que se encharcan (estres-hidrico.md)."),
    "barrenador_hueso": (POCO_COMUN, "Plaga reglamentada en focos; hay Zonas Libres oficiales (barrenadores-del-hueso.md)."),
    OTRA: (MODERADA, "Estres hidrico, deficiencias y otros problemas no incluidos en el catalogo."),
}

# ---------------------------------------------------------------------------
# P(s | C): verosimilitudes. Solo se listan las relaciones que la base de
# conocimiento describe; cualquier otra combinacion vale MUY_BAJA.
# ---------------------------------------------------------------------------
VEROSIMILITUDES: dict[str, dict[str, float]] = {
    "antracnosis": {
        "fruto_manchas_hundidas_oscuras": MUY_ALTA,  # sintoma tipico
        "fruto_manchas_sin_detalle": ALTA,
        "fruto_pulpa_podrida": ALTA,                 # la pudricion avanza a la pulpa
        "fruto_esporas_rosadas": MEDIA,              # solo con humedad
        "costras_corchosas_levantadas": BAJA,        # el "sindrome de rona" incluye Colletotrichum
        "hojas_caida_prematura": BAJA,               # en casos graves
        "fruto_caida_prematura": BAJA,               # fruto pequeno puede caer
    },
    "rona": {
        "costras_corchosas_levantadas": MUY_ALTA,    # sintoma tipico
        "fruto_manchas_sin_detalle": ALTA,           # lesiones cafes en la cascara
        "fruto_cicatrices_asperas": MEDIA,           # aspecto parecido a dano de trips
        "fruto_manchas_hundidas_oscuras": BAJA,      # la rona es superficial, no hundida
    },
    "trips": {
        "fruto_cicatrices_asperas": MUY_ALTA,        # "piel de cocodrilo"
        "fruto_manchas_sin_detalle": MEDIA,
        "hojas_bronceadas": MEDIA,                   # raspaduras palidas o bronceadas
        "costras_corchosas_levantadas": BAJA,        # sus heridas abren paso a la rona
    },
    "arana_roja": {
        "hojas_bronceadas": MUY_ALTA,                # bronceado en el haz
        "hojas_caida_prematura": MEDIA,
        # Sin "hojas_manchas_plateadas_enves_telaranas" (vale MUY_BAJA): esa senal es del
        # acaro persea; la arana roja broncea el haz "sin manchas redondas" (como en las reglas).
    },
    "acaro_persea": {
        "hojas_manchas_plateadas_enves_telaranas": MUY_ALTA,  # colonias bajo telaranas
        "hojas_caida_prematura": ALTA,               # defoliacion en ataques severos
        "hojas_bronceadas": MEDIA,
    },
    "barrenador_hueso": {
        "hueso_danado_galerias": MUY_ALTA,           # dano en la semilla
        "fruto_perforaciones": ALTA,
        "fruto_exudado_o_aserrin": ALTA,             # polvo blanquecino, excremento
        "fruto_caida_prematura": ALTA,
        "fruto_pulpa_podrida": MEDIA,                # las larvas comen la pulpa
    },
    "phytophthora": {
        "raices_danadas": MUY_ALTA,                  # raices negras y quebradizas
        "marchitez_general": ALTA,                   # aunque el suelo este humedo
        "suelo_encharcado": ALTA,                    # condicion que la favorece
        "hojas_pequenas_palidas": ALTA,              # copa rala
        "hojas_caida_prematura": MEDIA,
    },
    OTRA: {s: (MUY_BAJA if s in SINTOMAS_ESPECIFICOS else BAJA) for s in SINTOMAS},
}


def priors() -> dict[str, float]:
    """P(C) normalizado: el peso cualitativo de cada causa dividido entre la suma."""
    total = sum(peso for peso, _ in PRIORS_CUALITATIVOS.values())
    return {causa: peso / total for causa, (peso, _) in PRIORS_CUALITATIVOS.items()}


def verosimilitud(sintoma: str, causa: str) -> float:
    """P(s | C): el valor de la tabla o MUY_BAJA si la causa no explica ese sintoma."""
    return VEROSIMILITUDES[causa].get(sintoma, MUY_BAJA)


@dataclass
class TerminoBayes:
    """El calculo de una causa, paso a paso, para poder mostrarlo o revisarlo."""

    causa: str
    prior: float                 # P(C)
    verosimilitud: float         # P(S | C) = producto de P(s | C)
    no_normalizado: float        # P(S | C) * P(C)
    posterior: float = 0.0       # P(C | S) = no_normalizado / P(S)


@dataclass
class Estimacion:
    sintomas: list[str]
    terminos: list[TerminoBayes] = field(default_factory=list)  # ordenados por posterior
    evidencia: float = 0.0       # P(S)
    veredicto: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def principal(self) -> TerminoBayes | None:
        return self.terminos[0] if self.terminos else None


def estimar(sintomas: Iterable[str], tabla_priors: dict[str, float] | None = None) -> Estimacion:
    """Aplica el Teorema de Bayes a los sintomas observados y ordena las causas."""
    sintomas = sorted(set(sintomas))
    desconocidos = set(sintomas) - SINTOMAS.keys()
    if desconocidos:
        raise ValueError(f"Sintomas desconocidos: {', '.join(sorted(desconocidos))}")

    est = Estimacion(sintomas=sintomas)
    if not sintomas:
        est.veredicto = "sin_evidencia"
        est.avisos.append(
            "No se reporto ningun sintoma del catalogo: sin evidencia no se puede estimar "
            "la probabilidad de ninguna causa."
        )
        _avisos_generales(est)
        return est

    p_causa = tabla_priors or priors()

    # 1) Numerador de Bayes para cada causa: P(S | C) * P(C)
    for causa, prior in p_causa.items():
        p_sintomas_dada_causa = 1.0
        for s in sintomas:
            p_sintomas_dada_causa *= verosimilitud(s, causa)
        est.terminos.append(TerminoBayes(causa, prior, p_sintomas_dada_causa, p_sintomas_dada_causa * prior))

    # 2) Evidencia P(S): suma de los numeradores (ley de probabilidad total)
    est.evidencia = sum(t.no_normalizado for t in est.terminos)

    # 3) Posterior P(C | S) = numerador / P(S)
    for t in est.terminos:
        t.posterior = t.no_normalizado / est.evidencia
    est.terminos.sort(key=lambda t: t.posterior, reverse=True)

    _veredicto(est)
    _avisos_generales(est)
    return est


def _veredicto(est: Estimacion) -> None:
    mejor = est.principal
    if mejor.posterior >= DOMINANTE:
        est.veredicto = "dominante"
    elif mejor.posterior >= PROBABLE:
        est.veredicto = "probable"
        est.avisos.append("Hay una causa mas probable, pero no es concluyente: conviene confirmarla.")
    else:
        est.veredicto = "no_concluyente"
        est.avisos.append(
            "No es concluyente: la probabilidad esta repartida entre varias causas posibles. "
            "Valida en campo con un tecnico o lleva muestras a un laboratorio."
        )
    if mejor.causa == OTRA:
        est.avisos.append(
            "Lo mas probable es una causa que no esta en el catalogo: consulta a un tecnico."
        )
    if CAUSAS[mejor.causa].gravedad == GRAVEDAD_ALTA and mejor.posterior >= PROBABLE:
        est.avisos.append("La causa mas probable es grave: acude a un profesional lo antes posible.")


def _avisos_generales(est: Estimacion) -> None:
    est.avisos.append(
        "Probabilidades orientativas y provisionales (no son datos clinicos ni de campo): "
        "no sustituyen un diagnostico profesional ni de laboratorio, y no indican tratamientos."
    )
