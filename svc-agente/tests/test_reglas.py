"""Tests del motor de reglas (SBR) solo: hechos -> conclusion, sin LLM ni base de datos."""
import pytest

from app import reglas
from app.reglas import ALTA, diagnosticar, evaluar_parametros


def causas(diag):
    return [c.regla.id for c in diag.coincidencias]


def estados(ev):
    return {h.parametro: h.estado for h in ev.hallazgos}


def tiene_aviso(avisos, texto):
    return any(texto in a for a in avisos)


# --- A) Diagnostico por sintomas ---


@pytest.mark.parametrize(
    ("hechos", "esperada"),
    [
        ({"fruto_manchas_hundidas_oscuras"}, "antracnosis"),
        ({"fruto_manchas_hundidas_oscuras", "fruto_pulpa_podrida"}, "antracnosis"),
        ({"costras_corchosas_levantadas"}, "rona"),
        ({"hojas_bronceadas"}, "arana_roja"),
        ({"hojas_manchas_plateadas_enves_telaranas"}, "acaro_persea"),
        ({"hueso_danado_galerias"}, "barrenador_hueso"),
        ({"fruto_cicatrices_asperas"}, "trips"),
        ({"marchitez_general", "raices_danadas", "suelo_encharcado"}, "phytophthora"),
    ],
)
def test_un_sintoma_claro_orienta_a_una_causa(hechos, esperada):
    diag = diagnosticar(hechos)

    assert causas(diag) == [esperada]
    assert not diag.parciales


def test_apoyos_refuerzan_sin_ser_obligatorios():
    diag = diagnosticar({"fruto_manchas_hundidas_oscuras", "fruto_pulpa_podrida", "fruto_esporas_rosadas"})

    assert diag.coincidencias[0].apoyos == ["fruto_esporas_rosadas", "fruto_pulpa_podrida"]


def test_bronceado_con_manchas_en_el_enves_no_es_arana_roja():
    diag = diagnosticar({"hojas_bronceadas", "hojas_manchas_plateadas_enves_telaranas"})

    assert causas(diag) == ["acaro_persea"]


def test_phytophthora_incompleta_es_parcial_y_pide_lo_que_falta():
    diag = diagnosticar({"marchitez_general"})

    assert causas(diag) == []
    assert [p.regla.id for p in diag.parciales] == ["phytophthora"]
    assert diag.parciales[0].faltan == ["raices_danadas", "suelo_encharcado"]
    assert tiene_aviso(diag.avisos, "datos incompletos")


def test_varias_causas_a_la_vez_es_ambiguo_y_pide_tecnico():
    diag = diagnosticar({"fruto_manchas_hundidas_oscuras", "costras_corchosas_levantadas"})

    assert causas(diag) == ["antracnosis", "rona"]
    assert tiene_aviso(diag.avisos, "mas de una causa")


def test_bronceado_y_cicatrices_no_se_excluyen_entre_si():
    diag = diagnosticar({"hojas_bronceadas", "fruto_cicatrices_asperas"})

    assert causas(diag) == ["trips", "arana_roja"]
    assert tiene_aviso(diag.avisos, "mas de una causa")


def test_sin_hechos_no_fuerza_conclusion():
    diag = diagnosticar(set())

    assert causas(diag) == [] and diag.parciales == []
    assert tiene_aviso(diag.avisos, "No se fuerza una conclusion")


def test_hechos_que_no_disparan_reglas_no_fuerzan_conclusion():
    diag = diagnosticar({"hojas_caida_prematura"})  # solo apoya, no basta

    assert causas(diag) == []
    assert tiene_aviso(diag.avisos, "no bastan")


@pytest.mark.parametrize("hechos", [{"hueso_danado_galerias"}, {"marchitez_general", "raices_danadas", "suelo_encharcado"}])
def test_causa_grave_pide_profesional(hechos):
    diag = diagnosticar(hechos)

    assert diag.coincidencias[0].regla.entonces.gravedad == ALTA
    assert tiene_aviso(diag.avisos, "acude a un profesional")


def test_sintomas_fuera_del_catalogo_se_avisan():
    diag = diagnosticar({"hojas_bronceadas"}, otros="hojas enrolladas")

    assert tiene_aviso(diag.avisos, "hojas enrolladas")


def test_siempre_recuerda_consultar_al_tecnico():
    for hechos in [set(), {"hojas_bronceadas"}, {"hueso_danado_galerias"}]:
        assert reglas.CONSULTA_TECNICO in diagnosticar(hechos).avisos


def test_sintoma_desconocido_falla():
    with pytest.raises(ValueError, match="hojas_moradas"):
        diagnosticar({"hojas_moradas"})


def test_las_reglas_usan_solo_sintomas_del_catalogo_y_documentos_reales():
    from ingesta.documentos import CARPETA_CONOCIMIENTO

    for regla in reglas.REGLAS_SINTOMAS:
        assert regla.si | regla.apoyan | regla.excluye <= reglas.SINTOMAS.keys(), regla.id
        assert (CARPETA_CONOCIMIENTO / regla.entonces.documento).exists(), regla.id


def test_ninguna_conclusion_da_dosis():
    textos = [
        f"{r.entonces.explicacion} {r.entonces.recomendacion}" for r in reglas.REGLAS_SINTOMAS
    ] + [r.implicacion for r in reglas.RANGOS + reglas.REGLAS_PARAMETROS]
    for texto in textos:
        for palabra in ("kg", "litros por", "ml", "g/", "dosis de", "aplica "):
            assert palabra not in texto.lower(), texto


def test_agregar_una_regla_es_agregar_un_dato():
    nueva = reglas._regla("prueba", si={"hojas_caida_prematura"}, entonces=reglas.Conclusion("X", "x", "x"))

    assert causas(diagnosticar({"hojas_caida_prematura"}, reglas=[nueva])) == ["prueba"]


# --- B) Parametros del huerto ---


@pytest.mark.parametrize(
    ("ph", "estado"),
    [(4.8, "acido"), (5.49, "acido"), (5.5, "adecuado"), (6.5, "adecuado"), (7.0, "adecuado"),
     (7.2, "en el limite superior"), (7.5, "en el limite superior"), (7.6, "alcalino"), (8.4, "alcalino")],
)
def test_ph_del_suelo(ph, estado):
    assert estados(evaluar_parametros(ph_suelo=ph)) == {"ph_suelo": estado}


def test_ph_alcalino_menciona_clorosis():
    assert "clorosis" in evaluar_parametros(ph_suelo=8).hallazgos[0].implicacion


@pytest.mark.parametrize(("ph", "estado"), [(6.0, "acida"), (6.5, "adecuada"), (7.5, "adecuada"), (8.0, "alcalina")])
def test_ph_del_agua(ph, estado):
    assert estados(evaluar_parametros(ph_agua=ph)) == {"ph_agua": estado}


@pytest.mark.parametrize(("edad", "estado"), [(1, "joven"), (2.9, "joven"), (3, "en produccion"), (12, "en produccion")])
def test_edad_de_los_arboles(edad, estado):
    assert estados(evaluar_parametros(edad_arboles=edad)) == {"edad_arboles": estado}


def test_suelo_arcilloso_que_se_encharca_es_riesgo_alto_de_phytophthora():
    ev = evaluar_parametros(tipo_suelo="arcilloso", encharcamiento=True)

    assert {h.gravedad for h in ev.hallazgos} == {ALTA}
    assert all("Phytophthora" in h.implicacion for h in ev.hallazgos)
    assert tiene_aviso(ev.avisos, "riesgo alto")


@pytest.mark.parametrize("suelo", reglas.TIPOS_SUELO)
def test_cada_tipo_de_suelo_tiene_una_regla(suelo):
    assert len(evaluar_parametros(tipo_suelo=suelo).hallazgos) == 1


def test_hectareas_solo_es_contexto():
    ev = evaluar_parametros(hectareas=5)

    assert ev.hallazgos == [] and ev.contexto == {"hectareas": 5}
    assert tiene_aviso(ev.avisos, "No se saca ninguna conclusion")


def test_sin_parametros_no_concluye():
    ev = evaluar_parametros()

    assert ev.hallazgos == []
    assert tiene_aviso(ev.avisos, "No se saca ninguna conclusion")


def test_rangos_provisionales_piden_analisis_de_laboratorio():
    ev = evaluar_parametros(ph_suelo=6.2)

    assert ev.hallazgos[0].provisional
    assert tiene_aviso(ev.avisos, "analisis")


@pytest.mark.parametrize("datos", [{"ph_suelo": 15}, {"ph_agua": -1}, {"edad_arboles": -2}])
def test_valores_imposibles_fallan(datos):
    with pytest.raises(ValueError, match="fuera del rango posible"):
        evaluar_parametros(**datos)


def test_parametro_desconocido_falla():
    with pytest.raises(ValueError, match="nitrogeno"):
        evaluar_parametros(nitrogeno=3)


def test_los_rangos_de_cada_parametro_no_dejan_huecos():
    for parametro, valores in {
        "ph_suelo": [x / 10 for x in range(0, 141)],
        "ph_agua": [x / 10 for x in range(0, 141)],
        "edad_arboles": [x / 2 for x in range(0, 100)],
    }.items():
        for v in valores:
            assert len(evaluar_parametros(**{parametro: v}).hallazgos) == 1, (parametro, v)
