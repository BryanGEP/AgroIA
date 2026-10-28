"""Configuracion del microservicio: lee variables de entorno desde .env.

Centralizar aqui la configuracion permite cambiar de proveedor de LLM o de
modelo sin tocar el resto del codigo.
"""
import logging
import os
from dataclasses import dataclass

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


settings = Settings()

if not settings.groq_api_key:
    logger.warning("[AgroIA] falta GROQ_API_KEY en el archivo .env")
