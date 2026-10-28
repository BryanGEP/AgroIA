"""Lectura de los .md de la base de conocimiento y de su frontmatter YAML."""
from dataclasses import dataclass
from pathlib import Path

import yaml

# Carpeta por defecto: svc-agente/conocimiento/
CARPETA_CONOCIMIENTO = Path(__file__).resolve().parent.parent / "conocimiento"

CAMPOS_OBLIGATORIOS = ("tema", "subtema", "titulo", "fuentes")


class DocumentoInvalido(ValueError):
    """Un .md sin frontmatter o sin alguno de los campos obligatorios."""


@dataclass
class DocumentoFuente:
    archivo: str  # ruta relativa a la carpeta, con "/" (ej. "enfermedades/rona.md")
    tema: str
    subtema: str
    titulo: str
    fuentes: list[str]
    tipo: str | None
    cuerpo: str  # el Markdown sin el frontmatter


def leer_documento(ruta: Path, carpeta: Path) -> DocumentoFuente:
    archivo = ruta.relative_to(carpeta).as_posix()
    texto = ruta.read_text(encoding="utf-8")
    if not texto.startswith("---"):
        raise DocumentoInvalido(f"{archivo}: falta el frontmatter YAML")
    try:
        _, frontmatter, cuerpo = texto.split("---", 2)
        datos = yaml.safe_load(frontmatter) or {}
    except (ValueError, yaml.YAMLError) as error:
        raise DocumentoInvalido(f"{archivo}: frontmatter mal formado ({error})") from error

    faltan = [campo for campo in CAMPOS_OBLIGATORIOS if not datos.get(campo)]
    if faltan:
        raise DocumentoInvalido(f"{archivo}: faltan campos en el frontmatter: {', '.join(faltan)}")

    return DocumentoFuente(
        archivo=archivo,
        tema=str(datos["tema"]),
        subtema=str(datos["subtema"]),
        titulo=str(datos["titulo"]),
        fuentes=[str(f) for f in datos["fuentes"]],
        tipo=datos.get("tipo"),
        cuerpo=cuerpo.strip(),
    )


def cargar_documentos(carpeta: Path = CARPETA_CONOCIMIENTO) -> list[DocumentoFuente]:
    """Todos los .md de la carpeta y sus subcarpetas, en orden, excepto los README."""
    rutas = sorted(p for p in carpeta.rglob("*.md") if p.name.lower() != "readme.md")
    return [leer_documento(ruta, carpeta) for ruta in rutas]
