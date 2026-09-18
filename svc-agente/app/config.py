"""Configuracion del microservicio: lee variables de entorno desde .env.

Centralizar aqui la configuracion permite cambiar de proveedor de LLM o de
modelo sin tocar el resto del codigo.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")


settings = Settings()

if not settings.groq_api_key:
    print("[AgroIA] ADVERTENCIA: falta GROQ_API_KEY en el archivo .env")
