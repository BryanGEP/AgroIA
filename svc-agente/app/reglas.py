"""Sistema Basado en Reglas (SBR): orientacion deterministica "SI ... ENTONCES ...".

Modulo PURO: no usa el LLM ni depende del agente. Recibe hechos, evalua las reglas
y devuelve conclusiones. Las herramientas de app/tools.py lo envuelven.

Dos capacidades:
  A) diagnosticar(hechos): orienta sobre la causa probable a partir de SINTOMAS.
  B) evaluar_parametros(...): clasifica parametros del huerto (pH, suelo, edad...).

Las reglas son DATOS (listas al final de cada seccion), no ifs sueltos: para agregar
una regla basta con agregar un elemento a la lista. Se derivan de la base de
conocimiento (conocimiento/); cada una indica el documento de donde sale.

El SBR ORIENTA: nunca da dosis, productos ni recetas de tratamiento, y no sustituye
un analisis de laboratorio ni a un tecnico. Todas las recomendaciones lo reflejan.
"""
from collections.abc import Iterable
from dataclasses import dataclass, field

# Gravedad de una conclusion: "alta" obliga a recomendar acudir a un profesional.
MEDIA = "media"
ALTA = "alta"

CONSULTA_TECNICO = (
    "Confirma el diagnostico en campo con un tecnico o agronomo antes de aplicar "
    "cualquier medida; el sistema de reglas solo orienta y no indica tratamientos."
)


# =====================================================================
# A) Diagnostico orientativo por sintomas
# =====================================================================

# Catalogo de hechos (sintomas observables). El agente traduce la descripcion del
# productor a estos codigos; un sintoma que no encaje va como texto en "otros".
# Las descripciones van en el esquema de la herramienta en cada llamada al LLM: se
# mantienen cortas, solo con lo que distingue a cada sintoma.
SINTOMAS: dict[str, str] = {
    "fruto_manchas_hundidas_oscuras": "Manchas oscuras hundidas en la cascara",
    "fruto_manchas_sin_detalle": "Manchas en el fruto, sin saber si estan hundidas o levantadas",
    "fruto_pulpa_podrida": "Pulpa podrida u oscura bajo las manchas",
    "fruto_esporas_rosadas": "Esporas rosadas o salmon sobre las manchas",
    "costras_corchosas_levantadas": "Costras asperas, corchosas, levantadas (no polvo)",
    "fruto_cicatrices_asperas": "Cicatrices asperas o plateadas en la cascara",
    "hojas_bronceadas": "Hojas bronceadas, rojizas o 'quemadas'",
    "hojas_manchas_plateadas_enves_telaranas": "Manchas plateadas redondas en el enves, con telaranas",
    "hojas_caida_prematura": "Caida prematura de hojas",
    "hueso_danado_galerias": "Dano o galerias en el hueso",
    "fruto_perforaciones": "Perforaciones en el fruto",
    "fruto_exudado_o_aserrin": "Exudado blanquecino o aserrin en orificios del fruto",
    "fruto_caida_prematura": "Caida prematura de frutos",
    "marchitez_general": "Marchitez del arbol aunque el suelo este humedo",
    "raices_danadas": "Raices finas escasas, negras o quebradizas",
    "suelo_encharcado": "Suelo encharcado o que tarda en secarse",
    "hojas_pequenas_palidas": "Hojas pequenas, palidas o amarillas; copa rala",
}


@dataclass(frozen=True)
class Conclusion:
    causa: str
    explicacion: str
    recomendacion: str
    gravedad: str = MEDIA
    documento: str = ""  # archivo de conocimiento/ con la explicacion completa


@dataclass(frozen=True)
class Regla:
    """SI estan todos los hechos de `si` (y ninguno de `excluye`) ENTONCES `entonces`.

    `apoyan` son hechos que no hacen falta pero refuerzan la conclusion.
    """

    id: str
    si: frozenset[str]
    entonces: Conclusion
    apoyan: frozenset[str] = frozenset()
    excluye: frozenset[str] = frozenset()


def _regla(id, si, entonces, apoyan=(), excluye=()) -> Regla:
    return Regla(id, frozenset(si), entonces, frozenset(apoyan), frozenset(excluye))


REGLAS_SINTOMAS: list[Regla] = [
    _regla(
        "antracnosis",
        si={"fruto_manchas_hundidas_oscuras"},
        apoyan={"fruto_pulpa_podrida", "fruto_esporas_rosadas"},
        entonces=Conclusion(
            causa="Antracnosis (hongos del género Colletotrichum)",
            explicacion="Las manchas oscuras que se hunden y pudren la pulpa son el sintoma tipico.",
            recomendacion="Lleva frutos con sintomas a un laboratorio de diagnostico o a la Junta Local de Sanidad Vegetal para confirmarlo.",
            documento="enfermedades/antracnosis.md",
        ),
    ),
    _regla(
        "rona",
        si={"costras_corchosas_levantadas"},
        entonces=Conclusion(
            causa="Roña del aguacate (Elsinoë perseae / Sphaceloma perseae)",
            explicacion="Las costras asperas, corchosas y levantadas son superficiales; no es un polvo (eso seria mildiu) ni manchas hundidas (antracnosis).",
            recomendacion="Revisa tambien si hay trips: sus heridas son la puerta de entrada de la rona.",
            documento="enfermedades/rona.md",
        ),
    ),
    _regla(
        "trips",
        si={"fruto_cicatrices_asperas"},
        apoyan={"hojas_bronceadas"},
        entonces=Conclusion(
            causa="Daño por trips",
            explicacion="Los trips dejan cicatrices asperas o plateadas en la cascara del fruto pequeno.",
            recomendacion="Monitorea trips en brotes y frutos pequenos con un tecnico.",
            documento="enfermedades/trips.md",
        ),
    ),
    _regla(
        "arana_roja",
        si={"hojas_bronceadas"},
        apoyan={"hojas_caida_prematura"},
        # "sin manchas redondas en el enves": si las hay, es el acaro persea (regla siguiente)
        excluye={"hojas_manchas_plateadas_enves_telaranas"},
        entonces=Conclusion(
            causa="Araña roja / ácaros (Oligonychus punicae)",
            explicacion="El bronceado de las hojas sin manchas redondas en el enves orienta a la arana roja; los trips tambien pueden broncear hojas.",
            recomendacion="Revisa el haz de las hojas con una lupa para confirmar la presencia de acaros.",
            documento="enfermedades/arana-roja.md",
        ),
    ),
    _regla(
        "acaro_persea",
        si={"hojas_manchas_plateadas_enves_telaranas"},
        apoyan={"hojas_bronceadas", "hojas_caida_prematura"},
        entonces=Conclusion(
            causa="Ácaro persea (Oligonychus perseae)",
            explicacion="Forma colonias bajo telaranas en el enves; vistas desde abajo parecen manchas plateadas redondas.",
            recomendacion="Revisa el enves de las hojas con una lupa para confirmarlo.",
            documento="enfermedades/arana-roja.md",
        ),
    ),
    _regla(
        "barrenador_hueso",
        si={"hueso_danado_galerias"},
        apoyan={"fruto_perforaciones", "fruto_exudado_o_aserrin", "fruto_caida_prematura"},
        entonces=Conclusion(
            causa="Barrenador del hueso (picudos Conotrachelus/Heilipus o palomilla Stenoma catenifer)",
            explicacion="El dano o las galerias dentro de la semilla son la senal de los barrenadores.",
            recomendacion="Son plagas reglamentadas: reportalo al Comite Estatal o a la Junta Local de Sanidad Vegetal.",
            gravedad=ALTA,
            documento="enfermedades/barrenadores-del-hueso.md",
        ),
    ),
    _regla(
        "phytophthora",
        si={"marchitez_general", "raices_danadas", "suelo_encharcado"},
        apoyan={"hojas_pequenas_palidas"},
        entonces=Conclusion(
            causa="Posible tristeza del aguacate (pudrición de raíz por Phytophthora cinnamomi)",
            explicacion="Marchitez con raices danadas en un suelo que se encharca es el cuadro tipico de la pudricion de raiz.",
            recomendacion="Es grave: acude a un tecnico para confirmarlo con analisis de laboratorio y revisa el drenaje y el riego.",
            gravedad=ALTA,
            documento="riego/estres-hidrico.md",
        ),
    ),
]


@dataclass
class Coincidencia:
    regla: Regla
    apoyos: list[str]  # hechos de `apoyan` presentes


@dataclass
class Parcial:
    """Una regla con algunos de sus hechos: falta confirmar el resto."""

    regla: Regla
    faltan: list[str]


@dataclass
class Diagnostico:
    coincidencias: list[Coincidencia] = field(default_factory=list)
    parciales: list[Parcial] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def diagnosticar(
    hechos: Iterable[str], otros: str | None = None, reglas: list[Regla] = REGLAS_SINTOMAS
) -> Diagnostico:
    """Encadena hechos -> reglas -> conclusiones y aplica las reglas transversales."""
    hechos = set(hechos)
    desconocidos = hechos - SINTOMAS.keys()
    if desconocidos:
        raise ValueError(f"Sintomas desconocidos: {', '.join(sorted(desconocidos))}")

    diag = Diagnostico()
    for regla in reglas:
        if hechos & regla.excluye:
            continue
        presentes = regla.si & hechos
        if presentes == regla.si:
            diag.coincidencias.append(Coincidencia(regla, sorted(regla.apoyan & hechos)))
        elif presentes:
            diag.parciales.append(Parcial(regla, sorted(regla.si - hechos)))

    _transversales_sintomas(diag, otros)
    return diag


def _transversales_sintomas(diag: Diagnostico, otros: str | None) -> None:
    """Reglas transversales: ambiguo, incompleto, grave o sin hechos -> profesional."""
    if not diag.coincidencias and not diag.parciales:
        diag.avisos.append(
            "Los sintomas descritos no bastan para orientar a ninguna causa del catalogo de "
            "reglas. No se fuerza una conclusion: lleva muestras o fotos a un tecnico."
        )
    if len(diag.coincidencias) > 1:
        diag.avisos.append(
            "Los sintomas apuntan a mas de una causa a la vez (puede haber varios problemas "
            "o sintomas parecidos). Valida en campo con un tecnico."
        )
    if diag.parciales:
        diag.avisos.append(
            "Hay causas posibles con datos incompletos; revisa los sintomas que faltan o "
            "consulta a un tecnico antes de concluir."
        )
    if any(c.regla.entonces.gravedad == ALTA for c in diag.coincidencias):
        diag.avisos.append("Hay una causa grave posible: acude a un profesional lo antes posible.")
    if otros and otros.strip():
        diag.avisos.append(
            f"Sintomas no incluidos en las reglas ({otros.strip()}): no se evaluaron; "
            "comentalos con un tecnico."
        )
    diag.avisos.append(CONSULTA_TECNICO)


# =====================================================================
# B) Evaluacion de parametros del huerto
# =====================================================================
#
# UMBRALES ORIENTATIVOS Y PROVISIONALES. Varios no estan confirmados con una fuente
# oficial para Michoacan (en la base de conocimiento estan marcados "verificar"):
# - pH del suelo 5.5-7.0: suelo/ph-y-drenaje.md (INTAGRI; otras guias dicen 6.0-7.5).
# - pH del agua 6.5-7.5 y edad de 3 anos: definidos por el equipo, sin fuente en la base.
# Por eso el resultado SIEMPRE recomienda confirmar con un analisis de suelo/agua y un
# tecnico. No agregar umbrales que no esten en la base ni acordados con el equipo.


@dataclass(frozen=True)
class Rango:
    """SI minimo <= valor < maximo (con los limites indicados) ENTONCES estado."""

    parametro: str
    estado: str
    implicacion: str
    minimo: float | None = None
    maximo: float | None = None
    incluye_minimo: bool = True
    incluye_maximo: bool = False
    gravedad: str = MEDIA
    provisional: bool = True

    def aplica(self, valor: float) -> bool:
        if self.minimo is not None and (
            valor < self.minimo or (valor == self.minimo and not self.incluye_minimo)
        ):
            return False
        if self.maximo is not None and (
            valor > self.maximo or (valor == self.maximo and not self.incluye_maximo)
        ):
            return False
        return True


@dataclass(frozen=True)
class ReglaCategorica:
    """SI parametro == valor ENTONCES estado."""

    parametro: str
    valor: object
    estado: str
    implicacion: str
    gravedad: str = MEDIA
    provisional: bool = False


RANGOS: list[Rango] = [
    # pH del suelo (suelo/ph-y-drenaje.md, marcado "verificar")
    Rango("ph_suelo", "acido", maximo=5.5,
          implicacion="Por debajo del rango de referencia (5.5-7.0); algunos nutrientes se aprovechan peor aunque esten en el suelo. Corregirlo (por ejemplo con cal) solo con base en un analisis y la recomendacion de un tecnico."),
    Rango("ph_suelo", "adecuado", minimo=5.5, maximo=7.0, incluye_maximo=True,
          implicacion="Dentro del rango de referencia (5.5-7.0, ligeramente acido a neutro)."),
    Rango("ph_suelo", "en el limite superior", minimo=7.0, maximo=7.5, incluye_minimo=False, incluye_maximo=True,
          implicacion="Algo arriba del rango de referencia (5.5-7.0); algunas guias aceptan hasta 7.5. Conviene vigilarlo con un analisis de suelo."),
    Rango("ph_suelo", "alcalino", minimo=7.5, incluye_minimo=False,
          implicacion="Por arriba del rango de referencia; hay riesgo de clorosis (hojas amarillas) por menor disponibilidad de nutrientes."),
    # pH del agua de riego (acordado con el equipo, sin fuente en la base)
    Rango("ph_agua", "acida", maximo=6.5,
          implicacion="Fuera del rango orientativo para agua de riego (6.5-7.5): conviene analizarla y ajustarla con un tecnico."),
    Rango("ph_agua", "adecuada", minimo=6.5, maximo=7.5, incluye_maximo=True,
          implicacion="Dentro del rango orientativo para agua de riego (6.5-7.5)."),
    Rango("ph_agua", "alcalina", minimo=7.5, incluye_minimo=False,
          implicacion="Fuera del rango orientativo para agua de riego (6.5-7.5): conviene analizarla y ajustarla con un tecnico."),
    # Edad de los arboles (acordado con el equipo)
    Rango("edad_arboles", "joven", maximo=3,
          implicacion="Arboles jovenes: el manejo es distinto (formacion, riego y nutricion de establecimiento)."),
    Rango("edad_arboles", "en produccion", minimo=3,
          implicacion="Arboles en edad productiva."),
]

REGLAS_PARAMETROS: list[ReglaCategorica] = [
    # Tipo de suelo (suelo/ph-y-drenaje.md)
    ReglaCategorica("tipo_suelo", "arcilloso", "drenaje deficiente",
                    "Los suelos arcillosos drenan mal: alto riesgo de asfixia de raiz y de tristeza del aguacate (Phytophthora).",
                    gravedad=ALTA),
    ReglaCategorica("tipo_suelo", "arenoso", "retiene poca agua",
                    "Los suelos arenosos retienen poca agua y nutrientes; necesitan riegos mas frecuentes."),
    ReglaCategorica("tipo_suelo", "franco", "textura adecuada",
                    "La textura franca (intermedia) es de las mas adecuadas para el aguacate si drena bien."),
    ReglaCategorica("tipo_suelo", "volcanico", "retiene bien la humedad",
                    "Los suelos volcanicos (Andosoles) retienen bien la humedad; por eso muchas huertas de Michoacan producen sin riego."),
    # Drenaje (suelo/ph-y-drenaje.md, riego/estres-hidrico.md)
    ReglaCategorica("encharcamiento", True, "riesgo alto de Phytophthora",
                    "El encharcamiento asfixia las raices y es la principal condicion que favorece la tristeza del aguacate (Phytophthora).",
                    gravedad=ALTA),
    ReglaCategorica("encharcamiento", False, "sin encharcamiento",
                    "No se reporta encharcamiento: buena senal para la salud de la raiz."),
]

# Parametros que solo dan contexto y no disparan reglas por si solos.
INFORMATIVOS = {"hectareas"}
LIMITES = {"ph_suelo": (0, 14), "ph_agua": (0, 14), "edad_arboles": (0, 200), "hectareas": (0, 100_000)}
TIPOS_SUELO = tuple(r.valor for r in REGLAS_PARAMETROS if r.parametro == "tipo_suelo")


@dataclass
class Hallazgo:
    parametro: str
    valor: object
    estado: str
    implicacion: str
    gravedad: str
    provisional: bool


@dataclass
class Evaluacion:
    hallazgos: list[Hallazgo] = field(default_factory=list)
    contexto: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def evaluar_parametros(
    rangos: list[Rango] = RANGOS, categoricas: list[ReglaCategorica] = REGLAS_PARAMETROS, **datos
) -> Evaluacion:
    """Evalua los parametros dados (los que vengan en None se ignoran)."""
    datos = {k: v for k, v in datos.items() if v is not None}
    conocidos = {r.parametro for r in rangos} | {r.parametro for r in categoricas} | INFORMATIVOS
    desconocidos = datos.keys() - conocidos
    if desconocidos:
        raise ValueError(f"Parametros desconocidos: {', '.join(sorted(desconocidos))}")
    for parametro, (minimo, maximo) in LIMITES.items():
        if parametro in datos and not minimo <= datos[parametro] <= maximo:
            raise ValueError(f"{parametro}={datos[parametro]} fuera del rango posible ({minimo}-{maximo})")

    ev = Evaluacion(contexto={k: datos[k] for k in INFORMATIVOS & datos.keys()})
    for parametro, valor in datos.items():
        for r in rangos:
            if r.parametro == parametro and r.aplica(valor):
                ev.hallazgos.append(Hallazgo(parametro, valor, r.estado, r.implicacion, r.gravedad, r.provisional))
                break
        for r in categoricas:
            if r.parametro == parametro and r.valor == valor:
                ev.hallazgos.append(Hallazgo(parametro, valor, r.estado, r.implicacion, r.gravedad, r.provisional))

    _transversales_parametros(ev)
    return ev


def _transversales_parametros(ev: Evaluacion) -> None:
    if not ev.hallazgos:
        ev.avisos.append(
            "No se dieron parametros que se puedan evaluar (pH del suelo o del agua, tipo de "
            "suelo, encharcamiento, edad de los arboles). No se saca ninguna conclusion."
        )
        return
    if any(h.gravedad == ALTA for h in ev.hallazgos):
        ev.avisos.append("Hay un riesgo alto: revisalo con un tecnico lo antes posible.")
    if any(h.provisional for h in ev.hallazgos):
        ev.avisos.append(
            "Los rangos usados son orientativos y provisionales: confirma con un analisis "
            "de suelo o de agua en laboratorio y con un tecnico."
        )
    ev.avisos.append("Esta evaluacion no indica dosis ni correcciones concretas; eso lo define tu tecnico.")
