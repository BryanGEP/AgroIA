# AgroIA

Agente conversacional para apoyo al cultivo del aguacate.

Proyecto académico (Ingeniería en Sistemas Computacionales — TecNM Jiquilpan). Metodología Scrum, gestión en Jira. Repositorio monorepo.

## Estructura

| Carpeta | Descripción | Instalación |
|---|---|---|
| `svc-agente/` | Microservicio del agente conversacional (LangChain + FastAPI). | [README](svc-agente/README.md) |
| `svc-gestion/` | (Entrega 2) Backend de gestión con Django/DRF. | Próximamente |
| `svc-ingesta/` | (Entrega 4) Pipeline de ingesta para RAG. | Próximamente |
| `docs/` | Documentación del proyecto (sprints, entregables). | — |

## Entregas

- **Entrega 1:** el agente mínimo vive en [`svc-agente/`](svc-agente/). Consulta su [README](svc-agente/README.md) para instalar y ejecutar.

## Cómo contribuir

El equipo trabaja con ramas por tarea que se integran en `develop` mediante Pull Requests; `main` está protegida y solo contiene versiones estables.

Antes de hacer cualquier cambio, lee la [guía de contribución](CONTRIBUTING.md).
