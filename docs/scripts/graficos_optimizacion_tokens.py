"""Genera los graficos de docs/optimizacion-tokens.md (PNG en docs/img/).

Todos los numeros son mediciones reales del servicio (Groq openai/gpt-oss-120b +
pgvector), tomadas en las ramas perf/optimizar-tokens (2 de noviembre de 2026) y
perf/optimizar-final (8 de noviembre de 2026). Cada bloque de datos indica de donde sale.

Uso (desde la raiz del repo):
    pip install matplotlib
    python docs/scripts/graficos_optimizacion_tokens.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

SALIDA = Path(__file__).resolve().parent.parent / "img"

# Paleta: dos colores categoricos validados para daltonismo y contraste (azul / naranja)
AZUL = "#2a78d6"
NARANJA = "#eb6834"
TEXTO = "#0b0b0b"
TEXTO_2 = "#52514e"
GRID = "#e4e4e0"
FONDO = "#ffffff"

plt.rcParams.update({
    "font.family": ["Calibri", "DejaVu Sans"],
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXTO_2,
    "xtick.color": TEXTO_2,
    "ytick.color": TEXTO,
})
miles = FuncFormatter(lambda v, _: f"{v:,.0f}")


def limpiar(ax):
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def guardar(fig, nombre):
    fig.savefig(SALIDA / nombre, dpi=200, bbox_inches="tight", facecolor=FONDO)
    plt.close(fig)
    print("generado", SALIDA / nombre)


def pct(antes, despues):
    return f"{(despues - antes) / antes:+.0%}".replace("-", "−")


# ---------------------------------------------------------------- 1. Tiempo
def grafico_tiempo():
    # Medicion por llamada (2 de noviembre, antes de optimizar). Las esperas son las que
    # anuncio el cliente de Groq al reintentar tras un 429 ("Retrying ... in N seconds").
    # La roña es de la linea base de perf/optimizar-tokens, con el minuto de Groq libre.
    casos = [
        ("¿Qué es la roña?\n(minuto de Groq libre)", 2.0, 0),
        ("Hojas bronceadas\n(1 respuesta 429)", 12.3, 8),
        ("pH de mi suelo 4.8\n(3 respuestas 429)", 40.2, 3 + 8 + 23),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    y = list(range(len(casos)))[::-1]
    modelo = [total - espera for _, total, espera in casos]
    esperas = [espera for *_, espera in casos]
    ax.barh(y, modelo, height=0.5, color=AZUL, edgecolor=FONDO, lw=1.5, label="Modelo y red")
    ax.barh(y, esperas, left=modelo, height=0.5, color=NARANJA, edgecolor=FONDO, lw=1.5,
            label="Espera por límite de Groq (429)")
    for yi, (_, total, espera) in zip(y, casos):
        ax.text(total + 0.6, yi, f"{total:.1f} s" + (f"  ({espera} s de espera)" if espera else ""),
                va="center", fontsize=9, color=TEXTO)
    ax.set_yticks(y, [c[0] for c in casos], fontsize=9)
    ax.set_xlim(0, 52)
    ax.set_xlabel("Segundos por pregunta")
    limpiar(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=2, frameon=False, fontsize=9)
    guardar(fig, "tiempo-por-pregunta.png")


# ---------------------------------------------------------------- 2. Contexto
def grafico_contexto():
    # Pregunta "Tengo manchas negras hundidas en el fruto", linea base del 2 de noviembre:
    # tokens de entrada de cada llamada al LLM. La parte fija (prompt + herramientas)
    # es lo que mide un "Hola" en la misma version: 2,300 tokens.
    llamadas = ["Llamada 1\n(decide usar reglas)", "Llamada 2\n(decide buscar)", "Llamada 3\n(redacta)"]
    total = [2307, 2527, 3423]
    fija = 2300
    fig, ax = plt.subplots(figsize=(7.2, 2.4))
    y = list(range(3))[::-1]
    ax.barh(y, [fija] * 3, height=0.5, color=AZUL, edgecolor=FONDO, lw=1.5,
            label="Parte fija: prompt + herramientas (≈2,300)")
    ax.barh(y, [t - fija for t in total], left=fija, height=0.5, color=NARANJA, edgecolor=FONDO, lw=1.5,
            label="Pregunta + resultados de herramientas acumulados")
    for yi, t in zip(y, total):
        ax.text(t + 40, yi, f"{t:,} tokens", va="center", fontsize=9, color=TEXTO)
    ax.set_yticks(y, llamadas, fontsize=9)
    ax.set_xlim(0, 4200)
    ax.xaxis.set_major_formatter(miles)
    ax.set_xlabel("Tokens de entrada")
    limpiar(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.25), ncol=2, frameon=False, fontsize=9)
    guardar(fig, "contexto-por-llamada.png")


# ---------------------------------------------------------------- 3 y 4. Antes/despues
def grafico_antes_despues(nombre, preguntas, antes, despues, titulo_antes, titulo_despues):
    fig, ax = plt.subplots(figsize=(7.2, 0.62 * len(preguntas) + 0.9))
    n = len(preguntas)
    alto = 0.36
    pos = list(range(n))[::-1]
    ax.barh([p + alto / 2 for p in pos], antes, height=alto, color=AZUL, edgecolor=FONDO, lw=1.5, label=titulo_antes)
    ax.barh([p - alto / 2 for p in pos], despues, height=alto, color=NARANJA, edgecolor=FONDO, lw=1.5, label=titulo_despues)
    ax.axvline(8000, color=TEXTO, lw=1.0, ls=(0, (4, 3)), zorder=1)
    fondo = dict(fc=FONDO, ec="none", pad=0.8)  # que la linea del limite no cruce las cifras
    for p, a, d in zip(pos, antes, despues):
        ax.text(a + 70, p + alto / 2, f"{a:,}", va="center", fontsize=8, color=TEXTO_2, bbox=fondo, zorder=3)
        ax.text(d + 70, p - alto / 2, f"{d:,}  ({pct(a, d)})", va="center", fontsize=8, color=TEXTO, bbox=fondo, zorder=3)
    ax.text(8080, -0.62, "Límite del plan gratuito: 8,000 tokens por minuto", ha="left", va="center",
            fontsize=8, color=TEXTO)
    ax.set_yticks(pos, preguntas, fontsize=9)
    ax.set_ylim(-0.85, n - 0.45)
    ax.set_xlim(0, 12500)
    ax.xaxis.set_major_formatter(miles)
    ax.set_xlabel("Tokens de entrada por pregunta (suma de todas sus llamadas al LLM)")
    limpiar(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.42, 1.0 + 0.55 / n), ncol=2, frameon=False, fontsize=9)
    guardar(fig, nombre)


def grafico_ronda_1():
    # perf/optimizar-tokens, cada pregunta con el minuto de Groq libre (2 de noviembre).
    # ¹ despues usa las dos herramientas que pide el prompt (3 llamadas en vez de 2).
    # ² despues medido en la corrida con RAG_TOP_K=3 (la pizza no usa el RAG).
    grafico_antes_despues(
        "ronda-1-antes-despues.png",
        ["¿Qué es la roña?", "Manchas negras hundidas", "pH de mi suelo 4.8 ¹", "¿Cada cuánto riego?", "Hola", "¿Cómo hago una pizza? ²"],
        [5325, 8257, 7134, 5432, 2300, 2304],
        [3847, 6084, 6531, 3868, 1605, 1579],
        "Antes de la ronda 1", "Después de la ronda 1",
    )


def grafico_ronda_2():
    # perf/optimizar-final, configuracion final, minuto de Groq libre (8 de noviembre).
    grafico_antes_despues(
        "ronda-2-antes-despues.png",
        ["¿Qué es la roña?", "Manchas y costras (ambiguo)", "Hojas bronceadas + manchas", "Hola"],
        [5735, 9768, 9126, 2475],
        [5165, 7854, 7976, 2190],
        "Antes de la ronda 2 (con Bayes)", "Después de la ronda 2",
    )


# ---------------------------------------------------------------- 5. Contexto fijo
def grafico_contexto_fijo():
    # Tokens de entrada de un "Hola" (una sola llamada, sin herramientas): equivale al
    # contexto fijo que se reenvia en cada llamada. Mediciones reales de cada version.
    versiones = ["RAG + reglas\n(inicio)", "Ronda 1", "+ Bayes\n(4.ª herramienta)", "Ronda 2"]
    tokens = [2300, 1605, 2475, 2190]
    colores = [AZUL, NARANJA, AZUL, NARANJA]
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    barras = ax.bar(versiones, tokens, width=0.55, color=colores, edgecolor=FONDO, lw=1.5)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=AZUL, label="Versión sin optimizar"),
                       Patch(color=NARANJA, label="Después de una ronda de optimización")],
              loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=2, frameon=False, fontsize=9)
    for b, t in zip(barras, tokens):
        ax.text(b.get_x() + b.get_width() / 2, t + 40, f"{t:,}", ha="center", fontsize=9, color=TEXTO)
    ax.set_ylim(0, 2900)
    ax.yaxis.set_major_formatter(miles)
    ax.set_ylabel("Tokens de entrada de un «Hola»")
    for lado in ("top", "right", "bottom"):
        ax.spines[lado].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=9, colors=TEXTO)
    guardar(fig, "contexto-fijo-por-version.png")


if __name__ == "__main__":
    SALIDA.mkdir(parents=True, exist_ok=True)
    grafico_tiempo()
    grafico_contexto()
    grafico_ronda_1()
    grafico_ronda_2()
    grafico_contexto_fijo()
