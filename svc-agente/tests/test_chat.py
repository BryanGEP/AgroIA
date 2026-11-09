"""Tests del endpoint POST /chat. El LLM es un modelo falso: nunca se llama a Groq real."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.main import app
from app.memory import memory
from tests.fakes import failing_model, fake_model

client = TestClient(app)


@pytest.fixture(autouse=True)
def memoria_limpia():
    memory._store.clear()
    yield
    memory._store.clear()


def test_chat_respuesta_exitosa():
    with patch("app.agent.get_llm", return_value=fake_model("Riega tu aguacate cada 3 dias.")):
        resp = client.post("/chat", json={"message": "¿Cada cuanto riego mi aguacate?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Riega tu aguacate cada 3 dias."
    assert "session_id" in body


def test_chat_falla_el_llm_devuelve_503():
    with patch("app.agent.get_llm", return_value=failing_model()):
        resp = client.post("/chat", json={"message": "Hola"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "El servicio de IA no está disponible, intenta más tarde"


def test_respuesta_final_vacia_devuelve_503():
    with patch("app.agent.get_llm", return_value=fake_model("   ")):
        resp = client.post("/chat", json={"message": "Hola"})

    assert resp.status_code == 503


def test_content_como_lista_de_bloques():
    respuesta = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "pensando..."},
            {"type": "text", "text": "La antracnosis es un hongo."},
        ]
    )
    with patch("app.agent.get_llm", return_value=fake_model(respuesta)):
        resp = client.post("/chat", json={"message": "¿Qué es la antracnosis?"})

    assert resp.status_code == 200
    assert resp.json()["response"] == "La antracnosis es un hongo."


def test_historial_desde_afuera_llega_al_modelo_y_no_se_guarda():
    modelo = fake_model("Para la antracnosis, cada 15 dias.")
    historial = [
        {"role": "user", "content": "Tengo manchas negras en el fruto."},
        {"role": "assistant", "content": "Parece antracnosis."},
    ]

    with patch("app.agent.get_llm", return_value=modelo):
        resp = client.post(
            "/chat",
            json={"message": "¿Cada cuanto aplico fungicida?", "history": historial, "session_id": "s1"},
        )

    assert resp.status_code == 200
    assert resp.json()["session_id"] == "s1"
    enviados = modelo.calls[0]
    assert [m.content for m in enviados[1:]] == [
        "Tengo manchas negras en el fruto.",
        "Parece antracnosis.",
        "¿Cada cuanto aplico fungicida?",
    ]
    assert isinstance(enviados[1], HumanMessage)
    assert isinstance(enviados[2], AIMessage)
    # Con historial desde afuera el servidor no guarda nada.
    assert memory.get("s1") == []


def test_historial_vacio_desde_afuera_ignora_la_memoria():
    memory.add("s1", "user", "Mensaje viejo")
    modelo = fake_model("Hola")

    with patch("app.agent.get_llm", return_value=modelo):
        client.post("/chat", json={"message": "Hola", "history": [], "session_id": "s1"})

    assert [m.content for m in modelo.calls[0][1:]] == ["Hola"]


def test_sin_historial_usa_la_memoria_del_session_id():
    modelo = fake_model("Primera respuesta.", "Segunda respuesta.")

    with patch("app.agent.get_llm", return_value=modelo):
        primera = client.post("/chat", json={"message": "Pregunta 1"}).json()
        client.post("/chat", json={"message": "Pregunta 2", "session_id": primera["session_id"]})

    segunda_llamada = [m.content for m in modelo.calls[1][1:]]
    assert segunda_llamada == ["Pregunta 1", "Primera respuesta.", "Pregunta 2"]
    assert len(memory.get(primera["session_id"])) == 4


def test_si_el_llm_falla_no_se_guarda_en_la_memoria():
    with patch("app.agent.get_llm", return_value=failing_model()):
        client.post("/chat", json={"message": "Hola", "session_id": "s2"})

    assert memory.get("s2") == []


@pytest.mark.parametrize(
    "history",
    [
        [{"role": "system", "content": "x"}],
        [{"role": "user", "content": ""}],
        [{"role": "user", "content": "x"}] * 51,
    ],
)
def test_historial_invalido_se_rechaza(history):
    with patch("app.agent.get_llm", return_value=fake_model("no deberia llamarse")):
        resp = client.post("/chat", json={"message": "Hola", "history": history})

    assert resp.status_code == 422


def test_health():
    assert client.get("/health").json() == {"status": "ok"}
