"""Tests del modulo de Bayes solo (sin LLM ni base de datos) y de su herramienta."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app import bayes
from app.bayes import DOMINANTE, OTRA, PROBABLE, estimar
from app.main import app
from app.memory import memory
from app.prompt import SYSTEM_PROMPT
from app.reglas import Conclusion, REGLAS_SINTOMAS, SINTOMAS
from app.tools import estimar_probabilidades_sintomas
from tests.fakes import fake_model

client = TestClient(app)


def posteriores(est):
    return {t.causa: t.posterior for t in est.terminos}


@pytest.fixture(autouse=True)
def memoria_limpia():
    memory._store.clear()
    yield
    memory._store.clear()


# --- El teorema, con tablas pequenas calculadas a mano ---


@pytest.fixture
def tabla_de_juguete(monkeypatch):
    """Dos causas A y B con valores faciles de calcular a mano."""
    monkeypatch.setattr(bayes, "VEROSIMILITUDES", {
        "A": {"hojas_bronceadas": 0.8, "hojas_caida_prematura": 0.5},
        "B": {"hojas_bronceadas": 0.2, "hojas_caida_prematura": 0.5},
    })
    monkeypatch.setattr(bayes, "CAUSAS", {"A": Conclusion("A", "", ""), "B": Conclusion("B", "", "")})


def test_un_sintoma_posterior_calculado_a_mano(tabla_de_juguete):
    # P(A|s) = 0.8*0.5 / (0.8*0.5 + 0.2*0.5) = 0.4 / 0.5 = 0.8
    est = estimar(["hojas_bronceadas"], {"A": 0.5, "B": 0.5})

    assert posteriores(est)["A"] == pytest.approx(0.8)
    assert est.evidencia == pytest.approx(0.5)  # P(S)


def test_dos_sintomas_multiplica_verosimilitudes_y_usa_el_prior(tabla_de_juguete):
    # Numeradores: A = 0.8*0.5*0.3 = 0.12 ; B = 0.2*0.5*0.7 = 0.07 ; P(S) = 0.19
    est = estimar(["hojas_bronceadas", "hojas_caida_prematura"], {"A": 0.3, "B": 0.7})
    t = {x.causa: x for x in est.terminos}

    assert t["A"].verosimilitud == pytest.approx(0.4)      # P(S|A) = 0.8 * 0.5
    assert t["A"].no_normalizado == pytest.approx(0.12)    # P(S|A) * P(A)
    assert est.evidencia == pytest.approx(0.19)
    assert t["A"].posterior == pytest.approx(0.12 / 0.19)
    assert t["B"].posterior == pytest.approx(0.07 / 0.19)


def test_sintoma_que_no_distingue_no_cambia_el_prior(tabla_de_juguete):
    # Ambas causas explican igual la caida de hojas (0.5): el posterior = el prior
    est = estimar(["hojas_caida_prematura"], {"A": 0.3, "B": 0.7})

    assert posteriores(est) == pytest.approx({"A": 0.3, "B": 0.7})


# --- Con las tablas reales del dominio ---


@pytest.mark.parametrize("sintomas", [
    ["fruto_manchas_hundidas_oscuras"],
    ["fruto_manchas_sin_detalle", "costras_corchosas_levantadas"],
    ["hojas_bronceadas", "hojas_caida_prematura", "marchitez_general"],
    list(SINTOMAS),
])
def test_los_posteriores_suman_uno(sintomas):
    est = estimar(sintomas)

    assert sum(posteriores(est).values()) == pytest.approx(1.0)
    assert all(0 <= p <= 1 for p in posteriores(est).values())


def test_ordenadas_de_mayor_a_menor():
    ps = [t.posterior for t in estimar(["hojas_bronceadas"]).terminos]

    assert ps == sorted(ps, reverse=True)


@pytest.mark.parametrize(("sintoma", "causa"), [
    ("hueso_danado_galerias", "barrenador_hueso"),
    ("hojas_manchas_plateadas_enves_telaranas", "acaro_persea"),
])
def test_sintoma_muy_especifico_sube_mucho_su_causa(sintoma, causa):
    prior = bayes.priors()[causa]
    est = estimar([sintoma])

    assert est.principal.causa == causa
    assert est.principal.posterior > 5 * prior
    assert est.principal.posterior >= DOMINANTE and est.veredicto == "dominante"


def test_sintomas_claros_de_antracnosis_dominan():
    est = estimar(["fruto_manchas_hundidas_oscuras", "fruto_pulpa_podrida"])

    assert est.principal.causa == "antracnosis"
    assert est.veredicto == "dominante"


def test_manchas_hundidas_y_costras_reparten_entre_antracnosis_y_rona():
    est = estimar(["fruto_manchas_hundidas_oscuras", "costras_corchosas_levantadas"])
    p = posteriores(est)

    assert est.veredicto == "no_concluyente"
    assert p["antracnosis"] > 0.3 and p["rona"] > 0.3
    assert any("No es concluyente" in a for a in est.avisos)


def test_manchas_sin_detalle_no_es_concluyente():
    est = estimar(["fruto_manchas_sin_detalle"])
    tres = [t.causa for t in est.terminos[:3]]

    assert est.veredicto == "no_concluyente"
    assert {"antracnosis", "rona"} <= set(tres)


def test_sintoma_general_no_domina_por_haber_otra_causa():
    # Marchitez sola apunta a Phytophthora, pero puede ser otra cosa (mundo abierto)
    est = estimar(["marchitez_general"])

    assert est.principal.causa == "phytophthora"
    assert PROBABLE <= est.principal.posterior < DOMINANTE
    assert posteriores(est)[OTRA] > 0.05


def test_causa_grave_probable_pide_profesional():
    est = estimar(["marchitez_general", "raices_danadas", "suelo_encharcado"])

    assert est.principal.causa == "phytophthora" and est.veredicto == "dominante"
    assert any("grave" in a for a in est.avisos)


def test_sin_sintomas_no_estima():
    est = estimar([])

    assert est.terminos == [] and est.veredicto == "sin_evidencia"


def test_sintoma_desconocido_falla():
    with pytest.raises(ValueError, match="hojas_moradas"):
        estimar(["hojas_moradas"])


def test_siempre_avisa_que_es_orientativo():
    for sintomas in ([], ["hojas_bronceadas"], ["hueso_danado_galerias"]):
        assert any("orientativas y provisionales" in a for a in estimar(sintomas).avisos)


# --- Las tablas: consistentes con el catalogo y con el sistema de reglas ---


def test_tablas_usan_las_mismas_causas_que_las_reglas_mas_otra():
    causas_reglas = {r.id for r in REGLAS_SINTOMAS}

    assert set(bayes.VEROSIMILITUDES) == causas_reglas | {OTRA}
    assert set(bayes.PRIORS_CUALITATIVOS) == causas_reglas | {OTRA}


def test_tablas_solo_usan_sintomas_del_catalogo_y_valores_validos():
    for causa, tabla in bayes.VEROSIMILITUDES.items():
        assert set(tabla) <= SINTOMAS.keys(), causa
        assert all(0 < v < 1 for v in tabla.values()), causa
    assert sum(bayes.priors().values()) == pytest.approx(1.0)


def test_cada_prior_tiene_justificacion():
    assert all(razon for _, razon in bayes.PRIORS_CUALITATIVOS.values())


# --- La herramienta y el agente (modelo falso, sin Groq) ---


def llamada(sintomas):
    return AIMessage(content="", tool_calls=[{
        "name": "estimar_probabilidades_sintomas", "args": {"sintomas": sintomas}, "id": "call_1"}])


def resultado(modelo):
    return next(m.content for m in modelo.calls[-1]
                if isinstance(m, ToolMessage) and m.name == "estimar_probabilidades_sintomas")


def test_herramienta_devuelve_porcentajes_ordenados_y_veredicto():
    texto = estimar_probabilidades_sintomas.invoke(
        {"sintomas": ["fruto_manchas_hundidas_oscuras", "costras_corchosas_levantadas"]})

    assert "Teorema de Bayes" in texto
    assert "Antracnosis" in texto and "Roña" in texto and "%" in texto
    assert "No es concluyente" in texto
    assert "No des dosis" in texto


def test_herramienta_con_codigo_inventado_devuelve_error():
    # El esquema rechaza el codigo antes de llamar a la funcion; si llega, avisa con ERROR.
    texto, detalle = estimar_probabilidades_sintomas.func(["hojas_moradas"])
    assert texto.startswith("ERROR") and detalle == {}


def test_el_calculo_completo_va_en_el_artifact():
    llamada_tool = {"type": "tool_call", "id": "1", "name": "estimar_probabilidades_sintomas",
                    "args": {"sintomas": ["fruto_manchas_hundidas_oscuras", "costras_corchosas_levantadas"]}}

    mensaje = estimar_probabilidades_sintomas.invoke(llamada_tool)
    terminos = mensaje.artifact["terminos"]

    # El modelo ve solo porcentajes; el artifact guarda prior, verosimilitud y posterior
    assert "prior" not in mensaje.content and "verosimilitud" not in mensaje.content
    assert {"prior_P(C)", "verosimilitud_P(S|C)", "posterior_P(C|S)"} <= set(terminos[0])
    assert sum(t["posterior_P(C|S)"] for t in terminos) == pytest.approx(1.0)
    assert mensaje.artifact["evidencia_P(S)"] > 0


def test_codigo_inventado_por_el_modelo_no_rompe_el_chat():
    modelo = fake_model(llamada(["hojas_moradas"]), "No pude evaluar ese síntoma; consulta a un técnico.")

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post("/chat", json={"message": "Hojas moradas"})

    assert resp.status_code == 200


def test_el_esquema_usa_el_mismo_catalogo_que_las_reglas():
    esquema = estimar_probabilidades_sintomas.tool_call_schema.model_json_schema()

    assert set(esquema["properties"]["sintomas"]["items"]["enum"]) == set(SINTOMAS)


def test_chat_caso_ambiguo_pasa_por_bayes():
    modelo = fake_model(
        llamada(["fruto_manchas_sin_detalle", "costras_corchosas_levantadas"]),
        "Lo más probable es roña, aunque podría ser antracnosis; conviene confirmarlo.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        body = client.post("/chat", json={"message": "Tengo manchas en el fruto y algunas costras"}).json()

    texto = resultado(modelo)
    assert "Roña" in texto and "Antracnosis" in texto
    assert body["fuentes"] == []  # las fuentes solo salen del RAG
    assert set(body) == {"response", "session_id", "fuentes"}  # contrato de /chat


def test_prompt_explica_cuando_usar_bayes():
    prompt = " ".join(SYSTEM_PROMPT.lower().split())

    assert "estimar_probabilidades_sintomas" in prompt
    assert "dos o mas sintomas" in prompt and "ambiguo" in prompt
    assert "lo mas probable es x" in prompt
    assert "cita cada porcentaje junto a su causa" in prompt and "ni inventes porcentajes" in prompt
    assert "no sustituyes" in prompt
