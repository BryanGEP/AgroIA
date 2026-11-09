"""Tests del nucleo del agente: piezas separadas, sin estado y respuesta robusta."""
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app import agent
from app.agent import AgentError, build_messages, chat, extract_answer
from app.prompt import SYSTEM_PROMPT
from tests.fakes import failing_model, fake_model


def test_build_messages_con_prompt_historial_y_mensaje():
    messages = build_messages(
        "¿Y ahora?",
        [{"role": "user", "content": "Hola"}, {"role": "assistant", "content": "Hola, productor."}],
    )

    assert isinstance(messages[0], SystemMessage) and messages[0].content == SYSTEM_PROMPT
    assert [type(m) for m in messages[1:]] == [HumanMessage, AIMessage, HumanMessage]
    assert messages[-1].content == "¿Y ahora?"


def test_build_messages_sin_historial():
    messages = build_messages("Hola")

    assert [type(m) for m in messages] == [SystemMessage, HumanMessage]


def test_chat_no_guarda_estado_entre_llamadas():
    modelo = fake_model("Uno.", "Dos.")

    with patch("app.agent.get_llm", return_value=modelo):
        chat("Primera pregunta")
        chat("Segunda pregunta")

    # La segunda llamada no ve la primera: el agente no recuerda nada por su cuenta.
    assert [m.content for m in modelo.calls[1][1:]] == ["Segunda pregunta"]


def test_chat_convierte_el_fallo_del_llm_en_agent_error():
    with patch("app.agent.get_llm", return_value=failing_model()), pytest.raises(AgentError):
        chat("Hola")


@pytest.mark.parametrize(
    ("content", "esperado"),
    [
        ("  Texto simple.  ", "Texto simple."),
        ([{"type": "text", "text": "Parte 1. "}, {"type": "text", "text": "Parte 2."}], "Parte 1. Parte 2."),
        ([{"type": "reasoning", "reasoning": "x"}, {"type": "text", "text": "Solo esto."}], "Solo esto."),
        (["Bloque como texto."], "Bloque como texto."),
    ],
)
def test_extract_answer_acepta_texto_o_lista(content, esperado):
    assert extract_answer(AIMessage(content=content)) == esperado


@pytest.mark.parametrize("content", ["", "   ", [], [{"type": "reasoning", "reasoning": "x"}]])
def test_extract_answer_falla_si_la_respuesta_final_esta_vacia(content):
    with pytest.raises(AgentError):
        extract_answer(AIMessage(content=content))


def test_extract_answer_ignora_los_mensajes_intermedios_de_herramientas():
    conversacion = [
        HumanMessage("¿Cuánto es 37 + 58?"),
        AIMessage(content="", tool_calls=[{"name": "sumar", "args": {"a": 37, "b": 58}, "id": "1"}]),
        ToolMessage("95", tool_call_id="1"),
        AIMessage(content="El resultado es 95."),
    ]

    assert extract_answer(conversacion) == "El resultado es 95."


def test_extract_answer_sin_ningun_aimessage_falla():
    with pytest.raises(AgentError):
        extract_answer([HumanMessage("Hola")])


def test_build_llm_tiene_timeout_y_reintentos(monkeypatch):
    monkeypatch.setattr(agent.settings, "groq_api_key", "llave-de-prueba")
    monkeypatch.setattr(agent.settings, "llm_timeout", 12.5)
    monkeypatch.setattr(agent.settings, "llm_max_retries", 3)

    llm = agent.build_llm()

    assert llm.request_timeout == 12.5
    assert llm.max_retries == 3
