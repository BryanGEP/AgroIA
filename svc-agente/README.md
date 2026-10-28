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

- **Python 3.12**, la misma versión que la imagen de Docker (`python:3.12-slim`). Con otra versión las dependencias fijadas pueden no instalarse o comportarse distinto.
- Una API key de Groq (gratuita): https://console.groq.com/keys

## 1. Instalación (entorno virtual)

Desde la carpeta `svc-agente/`:

```bash
# Windows (PowerShell): el lanzador py elige la versión 3.12 aunque tengas otras
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3.12 -m venv venv
source venv/bin/activate

# Comprobar la versión: debe decir Python 3.12.x
python --version

# Instalar dependencias (requirements-dev.txt incluye requirements.txt y pytest)
pip install -r requirements-dev.txt
```

Si ya tenías un `venv` con otra versión de Python, bórralo y créalo de nuevo con estos pasos. En Windows, si no tienes Python 3.12, instálalo desde https://www.python.org/downloads/ (no hace falta quitar las otras versiones).

### Dependencias

`requirements.txt` y `requirements-dev.txt` tienen versiones **exactas** (`==`), directas y transitivas, para que el venv local y la imagen de Docker instalen exactamente lo mismo. Se generaron con `pip freeze` en un entorno limpio de Python 3.12, tomando como referencia la imagen que ya respondió preguntas reales.

Para agregar o actualizar una dependencia:

1. Crea un venv limpio de 3.12 e instala solo las dependencias directas con su nueva versión.
2. Corre `pip freeze` y copia el resultado a `requirements.txt` (las directas arriba, las transitivas abajo). Las de pruebas van en `requirements-dev.txt`.
3. Conserva las marcas de plataforma: `uvloop` solo se instala en Linux y `colorama` solo en Windows.
4. Corre `pytest`, prueba `/chat` con una pregunta real y haz `docker build`.

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
