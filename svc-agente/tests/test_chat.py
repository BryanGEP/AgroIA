"""Tests del endpoint POST /chat. El LLM se mockea: nunca se llama a Groq real."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_respuesta_exitosa():
    llm_falso = MagicMock()
    llm_falso.invoke.return_value = SimpleNamespace(content="Riega tu aguacate cada 3 dias.")

    with patch("app.agent.get_llm", return_value=llm_falso):
        resp = client.post("/chat", json={"message": "¿Cada cuanto riego mi aguacate?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Riega tu aguacate cada 3 dias."
    assert "session_id" in body


def test_chat_falla_el_llm_devuelve_503():
    llm_falso = MagicMock()
    llm_falso.invoke.side_effect = RuntimeError("Groq no disponible")

    with patch("app.agent.get_llm", return_value=llm_falso):
        resp = client.post("/chat", json={"message": "Hola"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "El servicio de IA no está disponible, intenta más tarde"
