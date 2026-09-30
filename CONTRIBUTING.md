# Guía de contribución — AgroIA

Esta guía explica cómo está organizado el repositorio y cuál es el proceso para hacer cualquier modificación. Léela antes de empezar a trabajar.

## Ramas del repositorio

Cada cambio avanza de izquierda a derecha, siempre por medio de un Pull Request (PR):

```
feat/tu-tarea  ──PR──►  develop  ──PR──►  main
 (aquí trabajas)     (integración y pruebas)   (versión estable)
```

| Rama | Para qué sirve | Reglas |
|---|---|---|
| `main` | Versión estable: lo que se entrega o se presenta. | Protegida. Solo recibe cambios por PR desde `develop`, al cerrar una entrega o sprint. |
| `develop` | Rama de trabajo del equipo. Aquí se juntan y prueban las tareas. | Es la rama por defecto. Todas las ramas nuevas salen de aquí y sus PR regresan aquí. |
| `feat/...`, `fix/...` | Una rama por cada tarea o corrección. | Se crea desde `develop`, se fusiona con un PR y después se borra. |

### Protección de `main`

La rama `main` tiene un ruleset (`proteger-main`) con estas reglas, que aplican para todo el equipo, incluido el administrador:

- **Restrict deletions:** nadie puede borrar la rama.
- **Block force pushes:** nadie puede sobrescribir su historial.
- **Require a pull request before merging:** no se puede hacer push directo; los cambios solo llegan por PR.

## Primera vez

Si vas a clonar el repositorio:

```powershell
git clone https://github.com/BryanGEP/AgroIA.git
cd AgroIA
```

Al clonar quedarás automáticamente en `develop`. Después sigue el README de cada servicio para instalarlo (por ejemplo, [`svc-agente/README.md`](svc-agente/README.md)).

Si ya tenías una copia anterior del repositorio (de antes de que existiera `develop`), actualízala así:

```powershell
git status                 # debe decir: working tree clean
git switch main
git pull
git fetch --prune
git switch develop
```

## Proceso para hacer una modificación

### 1. Actualiza `develop` y crea tu rama

```powershell
git switch develop
git pull
git switch -c feat/nombre-de-la-tarea
```

### 2. Trabaja y haz commits

Commits pequeños y con mensajes claros:

```powershell
git status
git add .
git commit -m "feat(web): descripción corta del cambio"
```

### 3. Prueba antes de subir

Corre las pruebas del servicio que modificaste (por ejemplo, `pytest` dentro de `svc-agente`) y levántalo para revisar que todo funcione.

### 4. Sube tu rama

```powershell
git push -u origin feat/nombre-de-la-tarea
```

La primera vez se usa `-u`; después basta con `git push`.

### 5. Abre el Pull Request

1. En GitHub, da clic en **Compare & pull request**.
2. Verifica que diga **base: `develop` ← compare: `feat/tu-rama`**. Nunca abras un PR hacia `main`.
3. Llena la plantilla: qué cambió y cómo probarlo.
4. Asigna como revisor a **@BryanGEP** y crea el PR.

### 6. Revisión

El administrador probará tu rama. Si algo falla, dejará un comentario: corrígelo en tu misma rama, haz commit y `git push`. El PR se actualiza solo; no hace falta abrir otro.

### 7. Limpia tu rama después del merge

```powershell
git switch develop
git pull
git branch -d feat/nombre-de-la-tarea
```

## Nombres de ramas y commits

| Prefijo | Cuándo usarlo | Ejemplo |
|---|---|---|
| `feat/` | Funcionalidad nueva | `feat/svc-gestion` |
| `fix/` | Corrección de un error | `fix/validacion-preguntas` |
| `docs/` | Solo documentación | `docs/guia-instalacion` |
| `test/` | Agregar o arreglar pruebas | `test/endpoints-agente` |
| `refactor/` | Reorganizar código sin cambiar su funcionamiento | `refactor/estructura-app` |

Usa minúsculas y guiones, sin acentos ni espacios. Los mensajes de commit siguen el formato `tipo(área): descripción`, por ejemplo `fix(api): manejo de pregunta vacía`.

## Problemas comunes

| Situación | Solución |
|---|---|
| Trabajé en `develop` sin crear mi rama (sin commit). | Crea la rama en ese momento; los cambios se van contigo: `git switch -c feat/mi-tarea`. |
| Hice commits en `develop` o `main` que no subí. | Crea una rama con ellos (`git switch -c feat/mi-tarea`), súbela y abre el PR. Luego regresa la rama original a como está en GitHub: `git switch develop` y `git reset --hard origin/develop`. |
| Abrí el PR hacia `main` por error. | En el PR, da clic en **Edit** junto al título y cambia la base a `develop`. |
| GitHub rechaza mi push a `main`. | Es la protección funcionando. Sube tu trabajo en una rama y abre un PR hacia `develop`. |
| Mi rama está atrasada respecto a `develop`. | Desde tu rama: `git pull origin develop`. Si hay conflictos, resuélvelos, haz commit y `git push`. |
| No puedo cambiar de rama: *"your local changes would be overwritten"*. | Guarda los cambios con `git stash`, cambia de rama y recupéralos con `git stash pop`. |

## Reglas de oro

- Nunca trabajes directo en `develop` ni en `main`.
- Antes de crear una rama, haz `git pull` en `develop`.
- Una rama = una tarea.
- Revisa con `git status` antes de cambiar de rama.
- Prueba tu código antes de abrir el PR.
- No subas el archivo `.env`; solo `.env.example`.
- Si algo sale raro, pregunta antes de forzar cualquier comando.
