"""Modelos falsos de LangChain para las pruebas: nunca se llama a Groq real.

Se basan en GenericFakeChatModel de langchain_core, asi que se comportan como un chat
model de verdad (mensajes, AIMessage, tool_calls) y sirven con create_agent: las
respuestas pueden traer tool_calls para simular que el modelo llama a una herramienta.
"""
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import Field


class _ConHerramientas(GenericFakeChatModel):
    """create_agent llama a bind_tools; el falso no necesita el esquema de las tools."""

    tools_recibidas: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self.tools_recibidas = list(tools)
        return self


class FakeModel(_ConHerramientas):
    """Responde en orden los mensajes dados y guarda lo que recibio en cada llamada."""

    calls: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class FailingModel(_ConHerramientas):
    """Simula que el proveedor del LLM falla (red caida, timeout, error 5xx)."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("Groq no disponible")


def fake_model(*answers) -> FakeModel:
    """Modelo falso que devuelve cada respuesta en orden (texto o AIMessage)."""
    messages = [a if isinstance(a, AIMessage) else AIMessage(content=a) for a in answers]
    return FakeModel(messages=iter(messages))


def failing_model() -> FailingModel:
    return FailingModel(messages=iter([]))


def tool_call(consulta: str, call_id: str = "call_1") -> AIMessage:
    """Turno del modelo que pide buscar en la base de conocimiento (sin texto)."""
    return AIMessage(
        content="",
        tool_calls=[{"name": "buscar_conocimiento", "args": {"consulta": consulta}, "id": call_id}],
    )
