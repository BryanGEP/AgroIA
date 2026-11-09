# svc-agente — Agente conversacional AgroIA

Agente conversacional mínimo para productores de aguacate, construido con
**LangChain** y expuesto como microservicio con **FastAPI** (endpoint `/chat`).

## Estructura

```
svc-agente/
├── app/
│   ├── __init__.py
│   ├── agent.py       # Núcleo del agente (create_agent con herramientas, fuentes)
│   ├── bayes.py       # Razonamiento probabilístico (Teorema de Bayes) sobre síntomas
│   ├── config.py      # Configuración (lee .env)
│   ├── main.py        # API FastAPI: /health y POST /chat
│   ├── memory.py      # Memoria conversacional por sesión
│   ├── prompt.py      # Prompt del sistema (rol y límites)
│   ├── rag.py         # Recuperación del RAG: embeddings e5, pgvector, buscar_conocimiento
│   ├── reglas.py      # Sistema basado en reglas (SBR): síntomas y parámetros del huerto
│   └── tools.py       # Herramientas del agente (RAG, SBR y Bayes)
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
  "session_id": "...",
  "fuentes": [
    "Rocha-Arroyo, Salazar-García et al. (2011), INIFAP - Revista Mexicana de Ciencias Agrícolas 2(3): ...",
    "California Avocado Commission - Irrigating Avocado Trees"
  ]
}
```

`fuentes` lista las referencias de los documentos de la base de conocimiento que el agente usó para responder (sección 6). Va vacía en saludos y temas no técnicos, cuando la base no tiene la respuesta o cuando no se pudo consultar.

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

El agente recupera información de `conocimiento/` (Markdown con frontmatter YAML) guardada en **Postgres con pgvector**, a través de la herramienta `buscar_conocimiento` (ver "Cómo responde el agente" más abajo).

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

### Cómo responde el agente

El agente usa `create_agent` de LangChain con la herramienta `buscar_conocimiento` (`app/tools.py`), que envuelve la función de `app/rag.py`:

1. Ante una pregunta técnica, el prompt (`app/prompt.py`) obliga al modelo a buscar **antes** de responder; los saludos y lo no técnico no buscan.
2. La herramienta devuelve al modelo el texto de los fragmentos, cada uno con su etiqueta de archivo (`[enfermedades/rona.md] ...`). Los metadatos con las fuentes viajan aparte, como *artifact* del `ToolMessage`; el modelo no los ve.
3. El modelo responde solo con lo que dicen los fragmentos y termina con una línea `FUENTES: enfermedades/rona.md, ...` (o `FUENTES: ninguna` si los fragmentos no contenían la respuesta). No hay umbral de relevancia: el modelo decide si el contexto alcanza.
4. `app/agent.py` quita esa línea del texto y arma `fuentes` solo con los documentos citados, sin repetir. Tolera etiquetas acortadas o con acentos (`antracnosis.md`, `roña.md`). Si el modelo no escribe la línea, o cita algo irreconocible, se devuelven las fuentes de todo lo consultado.

**Si pgvector no está disponible**, `/chat` no falla: la herramienta avisa al modelo, que responde que no pudo consultar la base y sugiere intentar más tarde, con `fuentes: []` y código 200. La conexión tiene un tope de 5 s y se reintenta en la siguiente pregunta, así que el servicio se recupera solo cuando la base regresa. Si falla el LLM (o el agente supera 10 pasos), `/chat` responde 503 como antes.

Al arrancar, el servicio precarga en segundo plano el modelo de embeddings y la conexión a pgvector, para que la primera pregunta no pague esa carga (varios segundos).

**Tiempos medidos** (Groq `openai/gpt-oss-120b`): una pregunta técnica hace 2 llamadas al LLM más la búsqueda (~20 ms) y tardó entre 2 y 19 s; un saludo, menos de 1 s. `LLM_TIMEOUT` (30 s) aplica a cada llamada al LLM, no a la petición completa.

### Pruebas

Las pruebas del RAG (`tests/test_ingesta.py`, `tests/test_rag.py`, `tests/test_rag_agente.py`) usan un vector store en memoria, embeddings falsos y un modelo falso con `tool_calls` simulados: no necesitan Postgres, Groq ni descargan modelos.

## 7. Sistema basado en reglas (SBR)

Lógica determinística "SI ... ENTONCES ..." que **orienta y clasifica** a partir de hechos; el RAG **explica y fundamenta**. El agente puede combinarlos: primero las reglas para orientar y después la base de conocimiento para explicar la causa.

- **Motor (`app/reglas.py`):** módulo puro, sin LLM ni dependencias del agente. Las reglas son datos (listas `REGLAS_SINTOMAS`, `RANGOS` y `REGLAS_PARAMETROS`): agregar una regla es agregar un elemento.
- **Herramientas (`app/tools.py`):** dos, una por capacidad, para que el modelo sepa cuál usar:
  - `diagnosticar_sintomas(sintomas, otros_sintomas)`: el modelo traduce lo que describe el productor a códigos de un catálogo (`SINTOMAS`) que van como `enum` en el esquema de la herramienta. Lo que no encaja va como texto en `otros_sintomas` y se avisa que no se evaluó.
  - `evaluar_huerto(ph_suelo, ph_agua, tipo_suelo, encharcamiento, edad_arboles, hectareas)`: solo los datos que dio el productor.

### A) Diagnóstico por síntomas

Cada regla tiene `si` (hechos obligatorios), `apoyan` (refuerzan, no obligatorios) y `excluye`. Se derivan de la base de conocimiento, y cada conclusión indica su documento para que el agente la explique con el RAG.

| Si se observa | Orienta a |
|---|---|
| Manchas oscuras hundidas en el fruto (apoyan: pulpa podrida, esporas rosadas) | Antracnosis |
| Costras ásperas, corchosas y levantadas | Roña |
| Cicatrices ásperas o plateadas en la cáscara | Trips |
| Hojas bronceadas, **sin** manchas plateadas en el envés | Araña roja / ácaros |
| Manchas plateadas en el envés bajo telarañas | Ácaro persea |
| Daño o galerías en el hueso | Barrenador del hueso (grave, plaga reglamentada) |
| Marchitez + raíces dañadas + encharcamiento | Posible Phytophthora (grave) |

Reglas transversales: con **más de una causa** se pide validar en campo; con una regla a medias se reporta como **datos incompletos** y se dice qué falta; si **nada coincide** no se fuerza una conclusión; si hay una causa **grave** se pide acudir a un profesional. Siempre se recuerda que es orientativo y no indica tratamientos.

### B) Parámetros del huerto

| Parámetro | Rangos | Origen |
|---|---|---|
| pH del suelo | < 5.5 ácido · 5.5–7.0 adecuado · 7.0–7.5 límite superior · > 7.5 alcalino (riesgo de clorosis) | `suelo/ph-y-drenaje.md` (marcado *verificar*) |
| pH del agua de riego | 6.5–7.5 adecuada; fuera, conviene ajustar | acordado con el equipo, sin fuente en la base |
| Tipo de suelo | arcilloso: drenaje deficiente, riesgo alto de Phytophthora · arenoso · franco · volcánico | `suelo/ph-y-drenaje.md` |
| Encharcamiento | sí: riesgo alto de Phytophthora | `suelo/ph-y-drenaje.md`, `riego/estres-hidrico.md` |
| Edad de los árboles | < 3 años joven · ≥ 3 en producción | acordado con el equipo |
| Hectáreas | solo contexto, no dispara reglas | — |

**Los rangos numéricos son orientativos y provisionales** (no confirmados con una fuente oficial para Michoacán): el resultado siempre recomienda confirmarlos con un análisis de suelo o agua en laboratorio y con un técnico. No agregues umbrales que no estén en la base ni acordados con el equipo.

El SBR **nunca da dosis, productos ni recetas**: eso lo define el técnico o agrónomo. Las fuentes de `/chat` siguen saliendo solo del RAG.

**Límite de Groq:** con las herramientas del SBR, cada llamada al LLM manda unos 2.3–3.3k tokens y una pregunta que combina reglas y RAG hace 3–4 llamadas. En el plan gratuito eso provoca respuestas `429` y el cliente reintenta tras esperar de 3 a 23 s, así que una pregunta puede tardar más de 30 s aunque el modelo responda en 1–2 s por llamada.

Pruebas: `tests/test_reglas.py` (motor solo) y `tests/test_reglas_agente.py` (herramientas con el modelo falso).

## 8. Razonamiento probabilístico (Teorema de Bayes)

Cuando hay **varios síntomas o son ambiguos**, el agente expresa la incertidumbre como probabilidades («antracnosis 49 %, roña 49 %: no es concluyente»). Las tres herramientas se complementan:

| Herramienta | Para qué |
|---|---|
| `diagnosticar_sintomas` (reglas) | Clasificar de forma determinista cuando el caso es claro |
| `estimar_probabilidades_sintomas` (Bayes) | Cuantificar la duda cuando hay varias causas posibles |
| `buscar_conocimiento` (RAG) | Explicar y fundamentar la causa o causas |

- **Módulo (`app/bayes.py`):** puro, sin LLM. Para cada causa calcula `P(causa|síntomas) = P(síntomas|causa) · P(causa) / P(síntomas)`, con el supuesto de Bayes ingenuo (síntomas independientes dada la causa), y normaliza para que los posteriores sumen 1. Cada `TerminoBayes` guarda el prior, la verosimilitud, el numerador y el posterior, para poder revisar el cálculo.
- **Catálogo compartido:** usa los mismos códigos de síntomas que el SBR (`app/reglas.py`), al que se añadió `fruto_manchas_sin_detalle` para las manchas que el productor no sabe describir. Las causas son las del SBR más **«otra causa no incluida»**, para que un síntoma general (como marchitez) no se atribuya con falsa seguridad a la única causa del catálogo que lo explica.
- **Solo cuentan los síntomas reportados:** que el productor no mencione un síntoma no significa que no esté.
- **Veredicto:** «dominante» si la causa principal llega al 80 %, «probable» entre 50 y 80 %, «no concluyente» por debajo del 50 %.

**Las probabilidades son orientativas y provisionales.** Los priors (`PRIORS_CUALITATIVOS`) y las verosimilitudes (`VEROSIMILITUDES`) no son datos clínicos ni epidemiológicos medidos. Son una escala cualitativa derivada de la base de conocimiento:

| Nivel | Valor | Uso |
|---|---|---|
| Muy alta | 0.9 | Síntoma típico de la causa |
| Alta | 0.7 | Síntoma frecuente |
| Media | 0.4 | Síntoma que aparece a veces |
| Baja | 0.15 | Síntoma posible pero poco característico |
| Muy baja | 0.01 | Síntoma no relacionado (valor por omisión; no es cero para no anular el producto) |

Sirven para ordenar las causas y expresar la duda, no como porcentajes exactos, y deben calibrarse con un especialista o con datos de campo. El resultado nunca da dosis ni tratamientos.

Pruebas: `tests/test_bayes.py` (el teorema con casos calculados a mano, las tablas reales y la herramienta con el modelo falso).

### Tokens: qué recibe el modelo

Cada llamada al LLM reenvía el prompt y los esquemas de las cuatro herramientas, así que se mantienen compactos:

- **Catálogo de síntomas una sola vez:** las dos herramientas de síntomas aceptan los mismos códigos, pero la descripción de cada síntoma solo va en el esquema de `estimar_probabilidades_sintomas`; `diagnosticar_sintomas` remite a él. Dejar solo los códigos, sin descripciones, hizo que el modelo omitiera síntomas que el productor sí mencionó, por eso se conservan una vez.
- **Contenido y artifact:** igual que el RAG, las reglas y Bayes devuelven al modelo solo lo esencial (causa, gravedad, siguiente paso, probabilidades, veredicto y avisos específicos). El detalle va en el *artifact* del `ToolMessage`, que el modelo no ve: las reglas disparadas con sus apoyos, y el cálculo bayesiano completo (prior, verosimilitud, numerador, evidencia y posterior de cada causa).
- **Fuentes:** se unifican las que son la misma obra escrita distinto (misma autoría y año) y, si el modelo no escribe la línea `FUENTES`, se toman solo los 2 documentos más relevantes de cada búsqueda.
- **Etiquetas:** `app/agent.py` quita del texto final cualquier etiqueta de fragmento (`[enfermedades/rona.md]`, `【…】`) que el modelo copie por error.

## Notas

- El agente **no sustituye** el diagnóstico de un profesional; sus respuestas
  son orientativas y deben validarse en campo.
- Arquitectura *tool-ready*: el RAG, el SBR y Bayes ya son herramientas del agente
  (`TOOLS` en `app/agent.py`); en la Entrega 3 se agregará el modelo de visión, sin
  reescribir el núcleo.
