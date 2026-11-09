"""Tests de las herramientas del SBR dentro del agente, con el modelo falso.

No se llama a Groq ni a pgvector: el modelo falso simula los tool_calls.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app.agent import TOOLS
from app.main import app
from app.memory import memory
from app.prompt import SYSTEM_PROMPT
from app.tools import NO_DOSIS, diagnosticar_sintomas, evaluar_huerto
from tests.fakes import fake_model

client = TestClient(app)


@pytest.fixture(autouse=True)
def memoria_limpia():
    memory._store.clear()
    yield
    memory._store.clear()


def llamada(nombre: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nombre, "args": args, "id": call_id}])


def resultado_de(modelo, nombre):
    """Contenido del ToolMessage de esa herramienta que recibio el modelo."""
    return next(m.content for m in modelo.calls[-1] if isinstance(m, ToolMessage) and m.name == nombre)


def test_el_agente_registra_las_herramientas():
    modelo = fake_model("Hola.")
    with patch("app.agent.get_llm", return_value=modelo):
        client.post("/chat", json={"message": "Hola"})

    assert [t.name for t in TOOLS] == [
        "buscar_conocimiento",
        "diagnosticar_sintomas",
        "evaluar_huerto",
        "estimar_probabilidades_sintomas",
    ]
    assert [t.name for t in modelo.tools_recibidas] == [t.name for t in TOOLS]


def test_el_esquema_lista_los_codigos_de_sintomas():
    esquema = diagnosticar_sintomas.tool_call_schema.model_json_schema()
    codigos = esquema["properties"]["sintomas"]["items"]["enum"]

    assert "fruto_manchas_hundidas_oscuras" in codigos and "hojas_bronceadas" in codigos
    assert "estimar_probabilidades_sintomas" in esquema["properties"]["sintomas"]["description"]


def test_el_catalogo_descrito_viaja_una_sola_vez():
    from app.reglas import SINTOMAS
    from app.tools import estimar_probabilidades_sintomas

    reglas_esq = diagnosticar_sintomas.tool_call_schema.model_json_schema()["properties"]["sintomas"]
    bayes_esq = estimar_probabilidades_sintomas.tool_call_schema.model_json_schema()["properties"]["sintomas"]

    # Los dos aceptan exactamente el mismo catalogo de codigos...
    assert set(reglas_esq["items"]["enum"]) == set(bayes_esq["items"]["enum"]) == set(SINTOMAS)
    # ...pero las descripciones solo viajan una vez (en el esquema de Bayes)
    assert all(texto in bayes_esq["description"] for texto in SINTOMAS.values())
    assert not any(texto in reglas_esq["description"] for texto in SINTOMAS.values())


def test_las_descripciones_dicen_cuando_usarlas():
    assert "sintomas" in diagnosticar_sintomas.description.lower()
    for dato in ("ph", "tipo de suelo", "encharca", "edad"):
        assert dato in evaluar_huerto.description.lower()


# --- Diagnostico por sintomas ---


def test_sintomas_orientan_a_antracnosis_y_no_hay_fuentes_sin_rag():
    modelo = fake_model(
        llamada("diagnosticar_sintomas", {"sintomas": ["fruto_manchas_hundidas_oscuras"]}),
        "Por lo que describes, la causa probable es antracnosis. Confírmalo con un técnico.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        body = client.post("/chat", json={"message": "Tengo manchas negras hundidas en el fruto"}).json()

    assert "antracnosis" in body["response"]
    assert body["fuentes"] == []  # las fuentes solo salen del RAG
    resultado = resultado_de(modelo, "diagnosticar_sintomas")
    assert "Causa probable: Antracnosis" in resultado
    assert "enfermedades/antracnosis.md" in resultado  # sugiere explicar con el RAG
    assert NO_DOSIS in resultado


def test_ambiguo_lo_dice_el_resultado_de_la_herramienta():
    modelo = fake_model(
        llamada("diagnosticar_sintomas", {"sintomas": ["fruto_manchas_hundidas_oscuras", "costras_corchosas_levantadas"]}),
        "Puede ser más de una causa; valida en campo con un técnico.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        client.post("/chat", json={"message": "Manchas hundidas y costras en el fruto"})

    assert "mas de una causa" in resultado_de(modelo, "diagnosticar_sintomas")


def test_sin_sintomas_reconocibles_no_fuerza_conclusion():
    modelo = fake_model(
        llamada("diagnosticar_sintomas", {"sintomas": [], "otros_sintomas": "hojas enrolladas"}),
        "Con eso no puedo orientarte; consulta a un técnico.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post("/chat", json={"message": "Las hojas se enrollan"})

    assert resp.status_code == 200
    resultado = resultado_de(modelo, "diagnosticar_sintomas")
    assert "Causa probable" not in resultado
    assert "No se fuerza una conclusion" in resultado and "hojas enrolladas" in resultado


def test_codigo_inventado_por_el_modelo_no_rompe_el_chat():
    modelo = fake_model(
        llamada("diagnosticar_sintomas", {"sintomas": ["hojas_moradas"]}),
        "No pude evaluar ese síntoma; consulta a un técnico.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post("/chat", json={"message": "Hojas moradas"})

    assert resp.status_code == 200
    assert resultado_de(modelo, "diagnosticar_sintomas").lower().startswith("error")


# --- Parametros del huerto ---


def test_ph_acido():
    modelo = fake_model(
        llamada("evaluar_huerto", {"ph_suelo": 4.8}),
        "Un pH de 4.8 es ácido; confírmalo con un análisis de suelo y un técnico.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        body = client.post("/chat", json={"message": "El pH de mi suelo es 4.8, ¿está bien?"}).json()

    resultado = resultado_de(modelo, "evaluar_huerto")
    assert "ph_suelo = 4.8: acido (rango provisional)" in resultado
    assert "analisis" in resultado
    assert body["fuentes"] == []


def test_suelo_arcilloso_encharcado():
    modelo = fake_model(
        llamada("evaluar_huerto", {"tipo_suelo": "arcilloso", "encharcamiento": True}),
        "Hay riesgo alto de Phytophthora.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        client.post("/chat", json={"message": "Mi suelo es muy arcilloso y se encharca"})

    resultado = resultado_de(modelo, "evaluar_huerto")
    assert resultado.count("Phytophthora") >= 2 and "riesgo alto" in resultado


def test_valor_imposible_se_devuelve_como_error_al_modelo():
    modelo = fake_model(llamada("evaluar_huerto", {"ph_suelo": 20}), "Ese pH no es posible.")

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post("/chat", json={"message": "Mi pH es 20"})

    assert resp.status_code == 200
    assert "fuera del rango posible" in resultado_de(modelo, "evaluar_huerto")


def test_combina_reglas_y_rag_en_un_turno():
    from tests.fakes import tool_call

    modelo = fake_model(
        llamada("diagnosticar_sintomas", {"sintomas": ["hojas_bronceadas"]}),
        tool_call("¿Qué es la araña roja del aguacate?", "call_2"),
        "Probablemente son ácaros (araña roja).\nFUENTES: enfermedades/arana-roja.md",
    )
    with (
        patch("app.rag.buscar_conocimiento", return_value=[]),
        patch("app.agent.get_llm", return_value=modelo),
    ):
        body = client.post("/chat", json={"message": "Las hojas se ven bronceadas"}).json()

    nombres = [m.name for m in modelo.calls[-1] if isinstance(m, ToolMessage)]
    assert nombres == ["diagnosticar_sintomas", "buscar_conocimiento"]
    assert body["response"] == "Probablemente son ácaros (araña roja)."


def test_prompt_explica_cuando_usar_cada_herramienta():
    prompt = " ".join(SYSTEM_PROMPT.lower().split())  # sin saltos de linea

    assert "diagnosticar_sintomas" in prompt and "evaluar_huerto" in prompt
    assert "no fuerces una conclusion" in prompt
    assert "ni las reglas, ni las probabilidades, ni tu dan dosis" in prompt
    assert "no sustituyes" in prompt
