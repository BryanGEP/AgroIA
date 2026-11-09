"""Script de ingesta: lee la base de conocimiento y la guarda en pgvector.

Uso (desde svc-agente/):
    python -m ingesta.cargar
    python -m ingesta.cargar --carpeta otra/carpeta

Es idempotente: cada corrida RECREA la coleccion (borra sus chunks y los vuelve a
escribir). Asi un documento borrado o acortado no deja chunks viejos, y volver a
correrla nunca duplica. Ademas los ids son deterministas (archivo + posicion).
"""
import argparse
import time
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

from app.config import settings
from ingesta.documentos import CARPETA_CONOCIMIENTO, cargar_documentos
from ingesta.fragmentos import contador_tokens_e5, fragmentar


def indexar(store: VectorStore, chunks: list[Document]) -> list[str]:
    """Escribe los chunks con sus ids; con el mismo id el vector store sobrescribe."""
    return store.add_documents(chunks, ids=[c.id for c in chunks])


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de la base de conocimiento a pgvector.")
    parser.add_argument("--carpeta", type=Path, default=CARPETA_CONOCIMIENTO)
    args = parser.parse_args()

    # Importado aqui para que importar ingesta.cargar no cargue el modelo ni Postgres.
    from app.rag import crear_embeddings, crear_vector_store

    inicio = time.perf_counter()
    docs = cargar_documentos(args.carpeta)
    chunks = fragmentar(docs, contador_tokens_e5(settings.embeddings_model))
    print(f"Documentos leidos: {len(docs)} | chunks generados: {len(chunks)}")

    store = crear_vector_store(crear_embeddings(), recrear=True)
    indexar(store, chunks)
    print(
        f"Coleccion '{settings.rag_collection}' recreada con {len(chunks)} chunks "
        f"({settings.embeddings_model}) en {time.perf_counter() - inicio:.1f} s"
    )


if __name__ == "__main__":
    main()
