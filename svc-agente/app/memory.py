"""Memoria conversacional simple, por sesion, en la memoria del proceso.

El agente ya no la usa: es sin estado. Esta memoria queda solo como RESPALDO para el
CLI y para /chat cuando el cliente no manda el historial (la demo web actual), a
partir del session_id. En la Entrega 2 el historial vivira en la base de datos del
servicio de gestion y se pasara al agente desde afuera.

Guarda los ultimos max_messages de cada sesion y como maximo max_sessions sesiones:
al pasar el limite se descarta la que lleva mas tiempo sin usarse.
"""
import threading
from collections import OrderedDict, deque


class SimpleMemory:
    def __init__(self, max_messages: int = 10, max_sessions: int = 1000):
        self.max_messages = max_messages
        self.max_sessions = max_sessions
        self._store: OrderedDict[str, deque] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, session_id: str, role: str, content: str):
        with self._lock:
            session = self._store.get(session_id)
            if session is None:
                session = deque(maxlen=self.max_messages)
                self._store[session_id] = session
            session.append({"role": role, "content": content})
            self._store.move_to_end(session_id)
            while len(self._store) > self.max_sessions:
                self._store.popitem(last=False)

    def get(self, session_id: str):
        with self._lock:
            session = self._store.get(session_id)
            if session is None:
                return []
            self._store.move_to_end(session_id)
            return list(session)

    def reset(self, session_id: str):
        with self._lock:
            self._store.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._store)


# Instancia compartida por el CLI y /chat.
memory = SimpleMemory(max_messages=10, max_sessions=1000)
