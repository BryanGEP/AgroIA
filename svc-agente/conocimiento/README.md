# Base de conocimiento del aguacate

Documentos en Markdown que alimentan el RAG del agente AgroIA. Están redactados con nuestras palabras a partir de fuentes confiables, citadas al final de cada archivo. **No contienen texto copiado ni PDFs.**

> Este README es solo un índice para el equipo: **no debe incluirse en la ingesta del RAG.**

## Contenido

| Carpeta | Archivo | Tema |
| --- | --- | --- |
| `enfermedades/` | `antracnosis.md` | Antracnosis (*Colletotrichum*) |
| | `rona.md` | Roña del fruto (*Elsinoë perseae* / *Sphaceloma perseae*) |
| | `barrenadores-del-hueso.md` | Barrenadores del hueso (*Conotrachelus*, *Heilipus lauri*, *Stenoma catenifer*), plagas reglamentadas |
| | `trips.md` | Trips y su relación con la roña |
| | `arana-roja.md` | Araña roja y ácaros (*Oligonychus punicae*, *O. perseae*) |
| `riego/` | `frecuencia-y-laminas.md` | Cuándo y cuánto regar |
| | `estres-hidrico.md` | Señales de falta o exceso de agua |
| `suelo/` | `ph-y-drenaje.md` | pH, drenaje, textura, materia orgánica y salinidad |
| | `fertilizacion.md` | Fertilización básica (N, P, K) |
| `manejo/` | `poda.md` | Tipos de poda y buenas prácticas |
| | `heladas.md` | Sensibilidad al frío y protección |

La carpeta `enfermedades/` incluye también las plagas; el campo `tipo` del frontmatter las distingue (`enfermedad` o `plaga`).

## Formato de cada archivo

```yaml
---
tema: enfermedades          # nombre de la carpeta
tipo: enfermedad            # solo en enfermedades/: enfermedad | plaga
subtema: antracnosis        # nombre del archivo, sin .md
titulo: "Antracnosis del aguacate"
fuentes:
  - "Institución - título"
actualizado: 2026-10-27
---
```

Después, encabezados `##` claros (Síntomas, Prevención, Manejo, etc.), una nota de que la información es orientativa y una sección final `## Fuentes` con los enlaces consultados. Cada archivo es autocontenido, porque el RAG lo fragmentará.

## Reglas para agregar o editar

- Redacta con tus palabras y **cita la fuente**. No copies texto con derechos de autor.
- Prioriza fuentes oficiales y académicas: SENASICA, SADER, INIFAP, APEAM, FAO, universidades (Chapingo, UMSNH, UC).
- Si un dato no se puede verificar, **no lo inventes**: omítelo o márcalo con *Verificar*.
- No recomiendes productos comerciales ni dosis sin fuente; indica siempre usar productos **registrados en México para aguacate** y consultar a un técnico.
- Actualiza la fecha `actualizado` al cambiar un archivo.
