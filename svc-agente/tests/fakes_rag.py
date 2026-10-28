"""Embeddings falsos y deterministas para probar la ingesta y la recuperacion.

No descargan modelos: cada texto se convierte en un vector que cuenta palabras clave
del dominio, asi que textos con las mismas palabras quedan cerca. Guardan los textos
recibidos para comprobar que se aplican los prefijos de e5.
"""
import re
import unicodedata

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

VOCABULARIO = [
    "rona", "antracnosis", "riego", "regar", "ph", "suelo", "helada", "hueso",
    "barrenador", "acaro", "bronceado", "poda", "fertiliz", "trips", "fruto", "hoja",
]


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_acentos.lower()


class EmbeddingsPalabrasClave(Embeddings):
    def __init__(self):
        self.documentos_recibidos: list[str] = []
        self.consultas_recibidas: list[str] = []

    def _vector(self, texto: str) -> list[float]:
        palabras = re.findall(r"\w+", _normalizar(texto))
        # +1 fijo para que ningun vector sea cero (la similitud coseno lo exige)
        return [sum(p.startswith(clave) for p in palabras) for clave in VOCABULARIO] + [1.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.documentos_recibidos.extend(texts)
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.consultas_recibidas.append(text)
        return self._vector(text)


def contar_palabras(texto: str) -> int:
    """Contador de tokens falso: una palabra = un token (no necesita tokenizador)."""
    return len(texto.split())


class InMemoryConRelevancia(InMemoryVectorStore):
    """InMemoryVectorStore no define la funcion de relevancia (PGVector si).

    Su puntaje ya es la similitud coseno, que con estos vectores (no negativos) queda
    entre 0 y 1, asi que se usa tal cual.
    """

    def _select_relevance_score_fn(self):
        return lambda similitud: min(1.0, max(0.0, similitud))  # redondeo de coma flotante
