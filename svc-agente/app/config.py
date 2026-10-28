"""Configuracion del microservicio: lee variables de entorno desde .env.

Centralizar aqui la configuracion permite cambiar de proveedor de LLM o de
modelo sin tocar el resto del codigo.
"""
import logging
import os
from dataclasses import dataclass
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    # Segundos maximos por llamada al LLM y reintentos ante errores transitorios.
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "30"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # Postgres con pgvector para la base de conocimiento (RAG). Los valores por
    # defecto apuntan al docker-compose de svc-agente desde esta computadora.
    # Si DATABASE_URL tiene valor, se usa tal cual y se ignoran los POSTGRES_*.
    database_url_env: str = os.getenv("DATABASE_URL", "")
    postgres_host: str = os.getenv("POSTGRES_HOST", "127.0.0.1")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5433"))
    postgres_db: str = os.getenv("POSTGRES_DB", "conocimiento")
    postgres_user: str = os.getenv("POSTGRES_USER", "agroia")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")

    # RAG: modelo local de embeddings, coleccion en pgvector y fragmentos por consulta.
    embeddings_model: str = os.getenv("EMBEDDINGS_MODEL", "intfloat/multilingual-e5-small")
    rag_collection: str = os.getenv("RAG_COLLECTION", "conocimiento_aguacate")
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "4"))

    @property
    def database_url(self) -> str:
        """URL de SQLAlchemy con el driver psycopg 3, la que espera PGVector."""
        if self.database_url_env:
            return self.database_url_env
        usuario = quote(self.postgres_user, safe="")
        contrasena = quote(self.postgres_password, safe="")
        return (
            f"postgresql+psycopg://{usuario}:{contrasena}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()

if not settings.groq_api_key:
    logger.warning("[AgroIA] falta GROQ_API_KEY en el archivo .env")
