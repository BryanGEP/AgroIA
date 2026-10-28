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
│   ├── prompt.py      # Prompt del sistema (rol y límites)
│   └── rag.py         # Recuperación del RAG: embeddings e5, pgvector, buscar_conocimiento
├── conocimiento/      # Base de conocimiento del aguacate (Markdown con frontmatter)
├── ingesta/           # Ingesta del RAG (se corre aparte: python -m ingesta.cargar)
│   ├── documentos.py  # Lee los .md y su frontmatter
│   ├── fragmentos.py  # Divide en chunks por sección y por tokens
│   └── cargar.py      # Script: lee, fragmenta, embebe y guarda en pgvector
├── cli.py             # Versión de consola (ejecutable localmente)
├── requirements.txt
├── .env.example
├── docker-compose.yml # Agente + Postgres con pgvector
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
3. Conserva las marcas de plataforma: `uvloop` solo se instala en Linux; `colorama` y `tzdata`, solo en Windows.
   `torch` va en su versión solo CPU (`torch==...+cpu`) desde el índice de PyTorch, declarado con `--extra-index-url` al inicio de `requirements.txt`. Ese índice no tiene ruedas para macOS.
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

Con `docker compose up -d --build` se levantan el agente y su Postgres con pgvector (ver la sección 6). Para solo el agente:

```bash
# Construir la imagen
docker build -t agroia-svc-agente .

# Ejecutar el contenedor (pasando la API key)
docker run -p 8000:8000 -e GROQ_API_KEY=tu_api_key agroia-svc-agente
```

El servicio quedará disponible en http://127.0.0.1:8000

## 6. Base de conocimiento (RAG)

El agente recupera información de `conocimiento/` (Markdown con frontmatter YAML) guardada en **Postgres con pgvector**. Todavía no se usa en `/chat`; la función de recuperación está lista para integrarse como herramienta del agente.

- **Embeddings:** modelo local `intfloat/multilingual-e5-small` (384 dimensiones), elegido en un bake-off contra e5-base y bge-m3. Se descarga la primera vez (unos 470 MB) en la caché de Hugging Face. e5 exige prefijos: los chunks se embeben como `passage: <texto>` y las consultas como `query: <texto>`; lo hace `EmbeddingsE5` en `app/rag.py`.
- **Vector store:** `PGVector` de `langchain-postgres` (API clásica, metadatos en JSONB), colección `conocimiento_aguacate`. El código usa la interfaz `VectorStore` de LangChain, así que se puede cambiar de vector store sin tocar a quien busca.

### Levantar pgvector

1. En `.env` define al menos `POSTGRES_PASSWORD` (ver `.env.example`; los demás tienen valores por defecto).
2. Desde `svc-agente/`:

```bash
docker compose up -d postgres
docker compose ps   # postgres debe decir (healthy)
```

La base queda en `127.0.0.1:5433` (5433 para no chocar con el Postgres de AgroIA-Web) y sus datos en el volumen `pgvector-datos`. Si cambias la contraseña después de crear el volumen, bórralo con `docker compose down -v` para que se cree de nuevo.

### Correr la ingesta

```bash
python -m ingesta.cargar
# Documentos leidos: 11 | chunks generados: 67
# Coleccion 'conocimiento_aguacate' recreada con 67 chunks (...)
```

O dentro de Docker: `docker compose run --rm svc-agente python -m ingesta.cargar`.

Qué hace:

1. Lee los `.md` de `conocimiento/` (excepto `README.md`) y valida su frontmatter (`tema`, `subtema`, `titulo` y `fuentes` son obligatorios).
2. Divide cada documento por encabezado `##` y, si una sección es larga, por tokens del tokenizador de e5: máximo 450 tokens por chunk (e5 trunca a 512) con 60 de solapamiento. Cada chunk empieza con `título del documento > sección`. Las secciones `## Fuentes` no se indexan.
3. Guarda en cada chunk los metadatos `tema`, `subtema`, `tipo`, `titulo`, `fuentes`, `archivo`, `seccion` y `chunk`, para poder citar la fuente.
4. Escribe los chunks en pgvector.

**Es idempotente:** cada corrida **recrea la colección** (borra sus chunks y los vuelve a escribir), así que nunca duplica y un documento borrado o acortado no deja chunks viejos. Corre la ingesta otra vez cada que cambie `conocimiento/`. En la primera corrida PGVector muestra `Collection not found`: es normal, todavía no había colección que borrar.

### Recuperar

```python
from app.rag import buscar_conocimiento

for f in buscar_conocimiento("¿Qué es la roña?"):        # k por defecto: RAG_TOP_K (4)
    print(f.relevancia, f.archivo, f.seccion, f.fuentes)
# 0.853 enfermedades/rona.md Qué es ['Ramírez Dávila et al. (2013), ...', ...]
```

Devuelve una lista de `Fragmento` (texto, relevancia de 0 a 1, título, sección, archivo, fuentes, tema, subtema, tipo), del más al menos relevante. `k` es configurable y se puede pasar otro `store` (las pruebas usan uno en memoria). Con e5 las relevancias quedan muy juntas (una pregunta fuera de tema saca alrededor de 0.78), así que no sirven como umbral fijo para decidir si la respuesta está en la base.

### Pruebas

Las pruebas del RAG (`tests/test_ingesta.py`, `tests/test_rag.py`) usan un vector store en memoria y embeddings falsos: no necesitan Postgres ni descargan modelos.

## Notas

- El agente **no sustituye** el diagnóstico de un profesional; sus respuestas
  son orientativas y deben validarse en campo.
- Arquitectura *tool-ready*: en la Entrega 2 se agregarán herramientas (RAG,
  reglas, Bayes; la ingesta y la recuperación del RAG ya están en `ingesta/` y `app/rag.py`) y en la Entrega 3 el modelo de visión, sin reescribir el núcleo.
