# svc-agente — Agente conversacional AgroIA

Agente conversacional mínimo para productores de aguacate, construido con
**LangChain** y expuesto como microservicio con **FastAPI** (endpoint `/chat`).

## Estructura

```
svc-agente/
├── app/
│   ├── __init__.py
│   ├── agent.py       # Núcleo del agente (LangChain, tool-ready)
│   ├── config.py      # Configuración (lee .env)
│   ├── main.py        # API FastAPI: /health y POST /chat
│   ├── memory.py      # Memoria conversacional por sesión
│   └── prompt.py      # Prompt del sistema (rol y límites)
├── cli.py             # Versión de consola (ejecutable localmente)
├── requirements.txt
├── .env.example
└── Dockerfile
```

## Requisitos

- Python 3.10 o superior
- Una API key de Groq (gratuita): https://console.groq.com/keys

## 1. Instalación (entorno virtual)

Desde la carpeta `svc-agente/`:

```bash
# Crear y activar el entorno virtual
python -m venv venv

# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## 2. Configurar la API key

Copia el archivo de ejemplo y coloca tu clave:

```bash
# Windows
copy .env.example .env
# Linux / macOS
cp .env.example .env
```

Abre `.env` y reemplaza el valor de `GROQ_API_KEY` por tu clave real.

## 3. Ejecutar en consola

```bash
python cli.py
```

Escribe tus preguntas y `salir` para terminar.

## 4. Ejecutar como microservicio (FastAPI)

```bash
uvicorn app.main:app --reload
```

- Documentación interactiva: http://127.0.0.1:8000/docs
- Estado del servicio: http://127.0.0.1:8000/health

### Probar el endpoint /chat

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"¿Cada cuánto debo regar mi aguacate?\"}"
```

Respuesta (ejemplo):

```json
{
  "response": "...",
  "session_id": "..."
}
```

Para mantener el contexto de la conversación, reenvía el `session_id` que
devuelve la primera respuesta en las siguientes peticiones.

## 5. Ejecutar con Docker (opcional)

```bash
# Construir la imagen
docker build -t agroia-svc-agente .

# Ejecutar el contenedor (pasando la API key)
docker run -p 8000:8000 -e GROQ_API_KEY=tu_api_key agroia-svc-agente
```

El servicio quedará disponible en http://127.0.0.1:8000

## Notas

- El agente **no sustituye** el diagnóstico de un profesional; sus respuestas
  son orientativas y deben validarse en campo.
- Arquitectura *tool-ready*: en la Entrega 2 se agregarán herramientas (RAG,
  reglas, Bayes) y en la Entrega 3 el modelo de visión, sin reescribir el núcleo.
