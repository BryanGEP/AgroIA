"""Memoria conversacional simple, por sesion.

Guarda los ultimos N mensajes de cada sesion en la memoria del proceso.
Es suficiente para la Entrega 1. Mas adelante (Entrega 2) se puede reemplazar
por una base de datos sin modificar el agente.
"""
from collections import deque, defaultdict


class SimpleMemory:
    def __init__(self, max_messages: int = 10):
        self.max_messages = max_messages
        self._store = defaultdict(lambda: deque(maxlen=self.max_messages))

    def add(self, session_id: str, role: str, content: str):
        self._store[session_id].append({"role": role, "content": content})

    def get(self, session_id: str):
        return list(self._store[session_id])

    def reset(self, session_id: str):
        self._store.pop(session_id, None)


# Instancia compartida por todo el microservicio.
memory = SimpleMemory(max_messages=10)
