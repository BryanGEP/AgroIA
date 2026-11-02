"""Tests del RAG dentro del agente: herramienta, fuentes en /chat y robustez.

El LLM es un modelo falso con tool_calls simulados y la base de conocimiento es un
vector store en memoria con embeddings falsos: no se llama a Groq ni a pgvector.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app import rag
from app.agent import TOOLS, chat_with_sources, extract_sources, split_cited_sources
from app.main import app
from app.memory import memory
from app.prompt import SYSTEM_PROMPT
from app.rag import EmbeddingsE5
from app.tools import BASE_NO_DISPONIBLE, SIN_RESULTADOS, buscar_conocimiento
from ingesta.cargar import indexar
from ingesta.documentos import cargar_documentos
from ingesta.fragmentos import fragmentar
from tests.fakes import fake_model, tool_call
from tests.fakes_rag import EmbeddingsPalabrasClave, InMemoryConRelevancia, contar_palabras

client = TestClient(app)


@pytest.fixture(scope="module")
def store_real():
    store = InMemoryConRelevancia(EmbeddingsE5(EmbeddingsPalabrasClave()))
    indexar(store, fragmentar(cargar_documentos(), contar_palabras))
    return store


@pytest.fixture
def base(store_real):
    """La herramienta busca en la base en memoria en lugar de pgvector."""
    with patch("app.rag.vector_store_por_defecto", return_value=store_real):
        yield store_real


@pytest.fixture(autouse=True)
def memoria_limpia():
    memory._store.clear()
    yield
    memory._store.clear()


def mensajes_de_herramienta(modelo):
    """ToolMessages que recibio el modelo en su ultima llamada."""
    return [m for m in modelo.calls[-1] if isinstance(m, ToolMessage)]


# --- La herramienta ---


def test_el_agente_registra_la_herramienta():
    modelo = fake_model("Hola.")
    with patch("app.agent.get_llm", return_value=modelo):
        chat_with_sources("Hola")

    assert TOOLS == [buscar_conocimiento]
    assert [t.name for t in modelo.tools_recibidas] == ["buscar_conocimiento"]


def test_la_descripcion_dice_cuando_usarla():
    descripcion = buscar_conocimiento.description.lower()

    for tema in ("riego", "suelo", "plagas", "enfermedades", "siempre", "saludos"):
        assert tema in descripcion


def test_herramienta_devuelve_texto_y_fragmentos(base):
    mensaje = buscar_conocimiento.invoke(
        {"type": "tool_call", "id": "1", "name": "buscar_conocimiento",
         "args": {"consulta": "¿Qué es la roña?"}}
    )

    assert isinstance(mensaje, ToolMessage)
    assert "[enfermedades/rona.md] Documento: Roña del aguacate" in mensaje.content
    assert len(mensaje.artifact) == rag.settings.rag_top_k
    assert mensaje.artifact[0]["archivo"] == "enfermedades/rona.md"
    assert mensaje.artifact[0]["fuentes"]


def test_herramienta_sin_resultados():
    vacio = InMemoryConRelevancia(EmbeddingsE5(EmbeddingsPalabrasClave()))
    with patch("app.rag.vector_store_por_defecto", return_value=vacio):
        contenido, fragmentos = buscar_conocimiento.func("¿Qué es la roña?")

    assert (contenido, fragmentos) == (SIN_RESULTADOS, [])


def test_herramienta_con_la_base_caida_no_lanza():
    with patch("app.rag.vector_store_por_defecto", side_effect=ConnectionError("pgvector caido")):
        contenido, fragmentos = buscar_conocimiento.func("¿Qué es la roña?")

    assert (contenido, fragmentos) == (BASE_NO_DISPONIBLE, [])


# --- Pregunta tecnica, saludo y contexto sin la respuesta ---


def test_pregunta_tecnica_llama_a_la_herramienta_y_devuelve_fuentes(base):
    modelo = fake_model(
        tool_call("¿Qué es la roña del aguacate?"),
        "La roña produce lesiones corchosas y elevadas en el fruto.",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post("/chat", json={"message": "¿Qué es la roña del aguacate?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "La roña produce lesiones corchosas y elevadas en el fruto."
    assert any(f.startswith("Ramírez Dávila et al. (2013)") for f in body["fuentes"])
    assert len(body["fuentes"]) == len(set(body["fuentes"]))  # sin repetir
    # El modelo recibio el texto recuperado antes de dar la respuesta final.
    resultado = mensajes_de_herramienta(modelo)
    assert len(resultado) == 1 and "Roña del aguacate" in resultado[0].content


def test_saludo_no_busca_y_fuentes_vacias():
    store = MagicMock()
    with (
        patch("app.rag.vector_store_por_defecto", return_value=store),
        patch("app.agent.get_llm", return_value=fake_model("¡Hola! ¿En qué te ayudo con tu huerta?")),
    ):
        resp = client.post("/chat", json={"message": "Hola"})

    assert resp.status_code == 200
    assert resp.json()["fuentes"] == []
    store.similarity_search_with_relevance_scores.assert_not_called()


def test_contexto_sin_la_respuesta_el_agente_lo_admite():
    admite = "No tengo esa información en mi base de conocimiento; consulta a un técnico."
    modelo = fake_model(tool_call("¿Qué dosis de glifosato uso?"), admite)
    vacio = InMemoryConRelevancia(EmbeddingsE5(EmbeddingsPalabrasClave()))

    with (
        patch("app.rag.vector_store_por_defecto", return_value=vacio),
        patch("app.agent.get_llm", return_value=modelo),
    ):
        resp = client.post("/chat", json={"message": "¿Qué dosis de glifosato uso?"})

    assert resp.status_code == 200
    assert resp.json() == {"response": admite, "session_id": resp.json()["session_id"], "fuentes": []}
    assert mensajes_de_herramienta(modelo)[0].content == SIN_RESULTADOS


def test_base_caida_responde_200_sin_fuentes():
    modelo = fake_model(
        tool_call("¿Cada cuánto riego?"),
        "No pude consultar la base de conocimiento; intenta más tarde.",
    )
    with (
        patch("app.rag.vector_store_por_defecto", side_effect=ConnectionError("caida")),
        patch("app.agent.get_llm", return_value=modelo),
    ):
        resp = client.post("/chat", json={"message": "¿Cada cuánto riego?"})

    assert resp.status_code == 200
    assert resp.json()["fuentes"] == []
    assert mensajes_de_herramienta(modelo)[0].content == BASE_NO_DISPONIBLE


def test_bucle_de_herramientas_se_corta_con_503(base):
    modelo = fake_model(*[tool_call("roña", f"call_{i}") for i in range(20)])

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post("/chat", json={"message": "¿Qué es la roña?"})

    assert resp.status_code == 503


def test_sesion_guarda_la_respuesta_sin_los_mensajes_de_herramienta(base):
    modelo = fake_model(tool_call("roña"), "Respuesta sobre la roña.")

    with patch("app.agent.get_llm", return_value=modelo):
        body = client.post("/chat", json={"message": "¿Qué es la roña?"}).json()

    assert [m["content"] for m in memory.get(body["session_id"])] == [
        "¿Qué es la roña?",
        "Respuesta sobre la roña.",
    ]


# --- Linea final FUENTES: solo las fuentes que el modelo uso ---


def test_solo_devuelve_las_fuentes_de_los_documentos_citados(base):
    modelo = fake_model(
        tool_call("¿Qué es la roña?"),
        "La roña forma costras corchosas.\n\nFUENTES: enfermedades/rona.md",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        body = client.post("/chat", json={"message": "¿Qué es la roña?"}).json()

    consultados = {f["archivo"] for f in mensajes_de_herramienta(modelo)[0].artifact}
    assert len(consultados) > 1  # la busqueda trajo otros documentos tambien
    assert body["response"] == "La roña forma costras corchosas."  # sin la linea FUENTES
    rona = next(d for d in cargar_documentos() if d.subtema == "rona")
    assert body["fuentes"] == rona.fuentes


def test_fuentes_ninguna_deja_la_lista_vacia(base):
    modelo = fake_model(
        tool_call("dosis de acido giberelico"),
        "No tengo esa información en mi base de conocimiento.\nFUENTES: ninguna",
    )

    with patch("app.agent.get_llm", return_value=modelo):
        body = client.post("/chat", json={"message": "¿Qué dosis de ácido giberélico uso?"}).json()

    assert body == {
        "response": "No tengo esa información en mi base de conocimiento.",
        "session_id": body["session_id"],
        "fuentes": [],
    }


def test_sin_linea_fuentes_usa_todo_lo_consultado(base):
    modelo = fake_model(tool_call("¿Qué es la roña?"), "La roña forma costras.")

    with patch("app.agent.get_llm", return_value=modelo):
        body = client.post("/chat", json={"message": "¿Qué es la roña?"}).json()

    esperadas = extract_sources(modelo.calls[-1])
    assert body["fuentes"] == esperadas and len(esperadas) > 3


@pytest.mark.parametrize(
    ("respuesta", "texto", "citados"),
    [
        ("Texto.\nFUENTES: a.md, b/c.md", "Texto.", {"a.md", "b/c.md"}),
        ("Texto.\n\n**FUENTES:** `a.md`, [b.md]", "Texto.", {"a.md", "b.md"}),
        ("Texto.\nfuentes: Ninguna", "Texto.", set()),
        ("Texto.\n\n---\nFUENTES: a.md", "Texto.", {"a.md"}),
        ("Uno.\n\n---\n\nDos.", "Uno.\n\n---\n\nDos.", None),
        ("Texto sin linea.", "Texto sin linea.", None),
        ("Las fuentes de agua: pozo y lluvia.", "Las fuentes de agua: pozo y lluvia.", None),
    ],
)
def test_split_cited_sources(respuesta, texto, citados):
    assert split_cited_sources(respuesta) == (texto, citados)


def test_solo_la_linea_de_fuentes_es_respuesta_vacia_503(base):
    modelo = fake_model(tool_call("roña"), "FUENTES: ninguna")

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post("/chat", json={"message": "¿Qué es la roña?"})

    assert resp.status_code == 503


# --- Extraccion de fuentes y prompt ---


def test_extract_sources_sin_repetir_e_ignora_otras_herramientas():
    mensajes = [
        ToolMessage("x", tool_call_id="1", name="buscar_conocimiento",
                    artifact=[{"fuentes": ["A", "B"]}, {"fuentes": ["B", "C"]}]),
        ToolMessage("y", tool_call_id="2", name="otra_herramienta", artifact=[{"fuentes": ["Z"]}]),
        ToolMessage("z", tool_call_id="3", name="buscar_conocimiento", artifact=[]),
        AIMessage("Respuesta"),
    ]

    assert extract_sources(mensajes) == ["A", "B", "C"]


def test_extract_sources_filtra_por_archivos_citados():
    mensajes = [
        ToolMessage("x", tool_call_id="1", name="buscar_conocimiento", artifact=[
            {"archivo": "a.md", "fuentes": ["A"]},
            {"archivo": "b.md", "fuentes": ["B"]},
        ]),
    ]

    assert extract_sources(mensajes, {"b.md"}) == ["B"]
    assert extract_sources(mensajes, set()) == []


@pytest.mark.parametrize("citado", ["antracnosis.md", "Antracnosis", "enfermedades/antracnosis.md"])
def test_cita_acortada_o_con_mayusculas_se_reconoce(citado):
    mensajes = [
        ToolMessage("x", tool_call_id="1", name="buscar_conocimiento", artifact=[
            {"archivo": "enfermedades/antracnosis.md", "fuentes": ["A"]},
            {"archivo": "enfermedades/rona.md", "fuentes": ["R"]},
        ]),
    ]

    assert extract_sources(mensajes, {citado}) == ["A"]
    assert extract_sources(mensajes, {"roña.md"}) == ["R"]  # con ñ, como lo escribe el modelo


def test_cita_irreconocible_usa_todo_lo_consultado():
    mensajes = [
        ToolMessage("x", tool_call_id="1", name="buscar_conocimiento", artifact=[
            {"archivo": "a.md", "fuentes": ["A"]},
            {"archivo": "b.md", "fuentes": ["B"]},
        ]),
    ]

    assert extract_sources(mensajes, {"documento-inventado.md"}) == ["A", "B"]


def test_prompt_obliga_a_buscar_y_a_no_inventar():
    prompt = SYSTEM_PROMPT.lower()

    assert "siempre a la herramienta" in prompt and "antes de responder" in prompt
    assert "no tienes esa informacion" in prompt
    assert "no necesitan" in prompt and "saludos" in prompt
    assert "no sustituyes" in prompt and "validar en campo" in prompt
