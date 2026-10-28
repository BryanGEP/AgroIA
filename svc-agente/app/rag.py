"""Recuperacion de la base de conocimiento (RAG): embeddings, vector store y busqueda.

Todo se expresa con las interfaces de LangChain (Embeddings y VectorStore), asi que
pgvector se puede cambiar por otro vector store sin tocar quien llama a
buscar_conocimiento. La ingesta (paquete ingesta/) usa estas mismas piezas para que
los documentos y las consultas se embeban con el mismo modelo y los mismos prefijos.

Aun no se usa en /chat: el agente lo integrara como herramienta en la siguiente fase.
"""
from dataclasses import dataclass, field
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from app.config import settings

# Prefijos que exige la familia e5: sin ellos la calidad de recuperacion baja.
PREFIJO_PASAJE = "passage: "
PREFIJO_CONSULTA = "query: "


class EmbeddingsE5(Embeddings):
    """Envuelve un modelo de embeddings y antepone el prefijo de e5 en cada caso.

    - embed_documents (indexar): "passage: <texto>"
    - embed_query (consultar):   "query: <texto>"

    El texto guardado en el vector store queda sin prefijo; solo se aplica al embeber.
    """

    def __init__(self, base: Embeddings):
        self.base = base

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.base.embed_documents([PREFIJO_PASAJE + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self.base.embed_query(PREFIJO_CONSULTA + text)


@lru_cache(maxsize=1)
def crear_embeddings() -> Embeddings:
    """Modelo local de embeddings (se descarga la primera vez y queda en la cache de HF)."""
    from langchain_huggingface import HuggingFaceEmbeddings

    base = HuggingFaceEmbeddings(
        model_name=settings.embeddings_model,
        encode_kwargs={"normalize_embeddings": True},
    )
    return EmbeddingsE5(base)


def crear_vector_store(embeddings: Embeddings | None = None, recrear: bool = False) -> VectorStore:
    """Vector store en pgvector (API clasica de langchain-postgres, metadatos en JSONB).

    Al construirse se conecta a Postgres y crea la extension y las tablas si faltan.
    Con recrear=True borra la coleccion antes de usarla (lo usa la ingesta).
    """
    from langchain_postgres import PGVector

    return PGVector(
        embeddings=embeddings or crear_embeddings(),
        collection_name=settings.rag_collection,
        connection=settings.database_url,
        use_jsonb=True,
        pre_delete_collection=recrear,
    )


@lru_cache(maxsize=1)
def vector_store_por_defecto() -> VectorStore:
    """Una sola conexion y un solo modelo cargado para todas las consultas."""
    return crear_vector_store()


@dataclass
class Fragmento:
    """Un chunk recuperado con lo necesario para citar su fuente."""

    texto: str
    relevancia: float
    titulo: str
    seccion: str
    archivo: str
    fuentes: list[str] = field(default_factory=list)
    tema: str | None = None
    subtema: str | None = None
    tipo: str | None = None


def buscar_conocimiento(
    consulta: str, k: int | None = None, store: VectorStore | None = None
) -> list[Fragmento]:
    """Devuelve los k chunks mas parecidos a la consulta, del mas al menos relevante.

    La relevancia va de 0 a 1 (mayor es mejor) sin importar el vector store. El prefijo
    "query:" lo aplica EmbeddingsE5, por eso el store debe usar crear_embeddings(). El
    store debe definir su funcion de relevancia (PGVector la define; InMemoryVectorStore
    no, ver tests/fakes_rag.py).
    """
    if not consulta or not consulta.strip():
        return []
    store = store or vector_store_por_defecto()
    resultados = store.similarity_search_with_relevance_scores(
        consulta.strip(), k=k or settings.rag_top_k
    )
    return [
        Fragmento(
            texto=doc.page_content,
            relevancia=round(float(score), 4),
            titulo=doc.metadata.get("titulo", ""),
            seccion=doc.metadata.get("seccion", ""),
            archivo=doc.metadata.get("archivo", ""),
            fuentes=list(doc.metadata.get("fuentes") or []),
            tema=doc.metadata.get("tema"),
            subtema=doc.metadata.get("subtema"),
            tipo=doc.metadata.get("tipo"),
        )
        for doc, score in resultados
    ]
