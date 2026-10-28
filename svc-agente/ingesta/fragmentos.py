"""Fragmentado de los documentos en chunks para el vector store.

1. Se divide por encabezado "##" (cada seccion queda en sus propios chunks).
2. Si una seccion es larga, se divide por tokens con solapamiento.
3. Cada chunk empieza con "titulo del documento > seccion" para que conserve su
   contexto aunque se lea suelto, y ese encabezado cuenta dentro del maximo.

Las secciones "## Fuentes" se excluyen: la bibliografia no responde preguntas y las
fuentes ya viajan en los metadatos de cada chunk.
"""
import uuid
from collections.abc import Callable

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from ingesta.documentos import DocumentoFuente

# e5 trunca a 512 tokens (incluidos el prefijo "passage: " y los tokens especiales).
MAX_TOKENS = 450
SOLAPAMIENTO = 60
SECCIONES_EXCLUIDAS = {"fuentes"}
SECCION_INTRODUCCION = "Introducción"  # el texto antes del primer "##"

# Espacio de nombres fijo: el mismo archivo y posicion dan siempre el mismo id.
_NAMESPACE_IDS = uuid.UUID("3b5c1f0e-6a1d-4c55-9a43-6f1c2b7d8e90")

ContadorTokens = Callable[[str], int]


def contador_tokens_e5(modelo: str) -> ContadorTokens:
    """Cuenta tokens con el tokenizador real del modelo (descarga solo el tokenizador)."""
    from transformers import AutoTokenizer

    tokenizador = AutoTokenizer.from_pretrained(modelo)
    return lambda texto: len(tokenizador(texto, add_special_tokens=False)["input_ids"])


def id_de_chunk(archivo: str, indice: int) -> str:
    return str(uuid.uuid5(_NAMESPACE_IDS, f"{archivo}#{indice}"))


def _secciones(cuerpo: str) -> list[tuple[str, str]]:
    divisor = MarkdownHeaderTextSplitter([("#", "h1"), ("##", "h2")], strip_headers=True)
    secciones = []
    for parte in divisor.split_text(cuerpo):
        nombre = parte.metadata.get("h2") or SECCION_INTRODUCCION
        if nombre.strip().lower() in SECCIONES_EXCLUIDAS:
            continue
        secciones.append((nombre, parte.page_content.strip()))
    return secciones


def fragmentar_documento(
    doc: DocumentoFuente,
    contar_tokens: ContadorTokens,
    max_tokens: int = MAX_TOKENS,
    solapamiento: int = SOLAPAMIENTO,
) -> list[Document]:
    chunks = []
    for seccion, texto in _secciones(doc.cuerpo):
        if not texto:
            continue
        encabezado = f"{doc.titulo} > {seccion}\n"
        disponibles = max_tokens - contar_tokens(encabezado)
        divisor = RecursiveCharacterTextSplitter(
            chunk_size=disponibles,
            chunk_overlap=min(solapamiento, disponibles // 2),
            length_function=contar_tokens,
            separators=["\n\n", "\n- ", "\n", ". ", " ", ""],
        )
        for pedazo in divisor.split_text(texto):
            indice = len(chunks)
            chunks.append(
                Document(
                    id=id_de_chunk(doc.archivo, indice),
                    page_content=encabezado + pedazo,
                    metadata={
                        "tema": doc.tema,
                        "subtema": doc.subtema,
                        "tipo": doc.tipo,
                        "titulo": doc.titulo,
                        "fuentes": doc.fuentes,
                        "archivo": doc.archivo,
                        "seccion": seccion,
                        "chunk": indice,
                    },
                )
            )
    return chunks


def fragmentar(
    docs: list[DocumentoFuente],
    contar_tokens: ContadorTokens,
    max_tokens: int = MAX_TOKENS,
    solapamiento: int = SOLAPAMIENTO,
) -> list[Document]:
    return [
        chunk
        for doc in docs
        for chunk in fragmentar_documento(doc, contar_tokens, max_tokens, solapamiento)
    ]
