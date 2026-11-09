"""Tests de la ingesta: lectura, fragmentado, metadatos e idempotencia (sin Postgres)."""
import pytest
from langchain_core.vectorstores import InMemoryVectorStore

from ingesta.cargar import indexar
from ingesta.documentos import DocumentoInvalido, cargar_documentos
from ingesta.fragmentos import MAX_TOKENS, fragmentar
from tests.fakes_rag import EmbeddingsPalabrasClave, contar_palabras

FRONTMATTER = """---
tema: riego
subtema: prueba
titulo: "Documento de prueba"
fuentes:
  - "Fuente A"
actualizado: 2026-10-27
---
"""


def escribir(carpeta, nombre, texto):
    ruta = carpeta / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


@pytest.fixture(scope="module")
def docs_reales():
    return cargar_documentos()


@pytest.fixture(scope="module")
def chunks_reales(docs_reales):
    return fragmentar(docs_reales, contar_palabras)


def test_carga_la_base_real_sin_el_readme(docs_reales):
    archivos = [d.archivo for d in docs_reales]

    assert len(docs_reales) == 11
    assert "README.md" not in archivos
    assert "enfermedades/rona.md" in archivos
    assert all("/" in a for a in archivos)


def test_frontmatter_se_conserva(docs_reales):
    rona = next(d for d in docs_reales if d.subtema == "rona")
    poda = next(d for d in docs_reales if d.subtema == "poda")

    assert rona.tema == "enfermedades" and rona.tipo == "enfermedad"
    assert rona.titulo.startswith("Roña del aguacate")
    assert rona.fuentes and all(isinstance(f, str) for f in rona.fuentes)
    assert poda.tipo is None  # solo enfermedades/ lleva tipo
    assert not rona.cuerpo.startswith("---")


def test_documento_sin_campos_obligatorios_falla(tmp_path):
    escribir(tmp_path, "malo.md", "---\ntema: riego\n---\n# Sin titulo\n")

    with pytest.raises(DocumentoInvalido, match="malo.md.*subtema.*titulo.*fuentes"):
        cargar_documentos(tmp_path)


def test_documento_sin_frontmatter_falla(tmp_path):
    escribir(tmp_path, "sin.md", "# Solo texto\n")

    with pytest.raises(DocumentoInvalido, match="sin.md"):
        cargar_documentos(tmp_path)


def test_cada_chunk_empieza_con_titulo_y_seccion(chunks_reales):
    for chunk in chunks_reales:
        m = chunk.metadata
        assert chunk.page_content.startswith(f"{m['titulo']} > {m['seccion']}\n")


def test_excluye_las_secciones_de_fuentes(chunks_reales):
    assert all(c.metadata["seccion"] != "Fuentes" for c in chunks_reales)
    # Las referencias con enlace solo aparecen en "## Fuentes"
    assert not any("https://" in c.page_content for c in chunks_reales)


def test_metadatos_para_citar_la_fuente(chunks_reales):
    claves = {"tema", "subtema", "tipo", "titulo", "fuentes", "archivo", "seccion", "chunk"}
    for chunk in chunks_reales:
        assert set(chunk.metadata) == claves
        assert chunk.metadata["fuentes"]
        assert chunk.metadata["archivo"].endswith(".md")


def test_ningun_chunk_pasa_el_maximo_de_tokens(chunks_reales):
    assert max(contar_palabras(c.page_content) for c in chunks_reales) <= MAX_TOKENS


def test_seccion_larga_se_divide_con_solapamiento(tmp_path):
    oraciones = " ".join(f"Oracion numero {i} sobre el riego del huerto." for i in range(60))
    escribir(tmp_path, "riego/largo.md", FRONTMATTER + "# Doc\n\n## Larga\n\n" + oraciones)

    chunks = fragmentar(cargar_documentos(tmp_path), contar_palabras, max_tokens=60, solapamiento=15)

    assert len(chunks) > 3
    assert all(contar_palabras(c.page_content) <= 60 for c in chunks)
    assert all(c.page_content.startswith("Documento de prueba > Larga\n") for c in chunks)
    for anterior, siguiente in zip(chunks, chunks[1:]):
        cola = anterior.page_content.split()[-3:]
        assert " ".join(cola) in siguiente.page_content  # comparten texto


def test_texto_antes_del_primer_encabezado_es_introduccion(tmp_path):
    escribir(tmp_path, "a.md", FRONTMATTER + "# Doc\n\nAviso inicial.\n\n## Uno\n\nTexto uno.\n")

    chunks = fragmentar(cargar_documentos(tmp_path), contar_palabras)

    assert [c.metadata["seccion"] for c in chunks] == ["Introducción", "Uno"]


def test_ids_deterministas_y_unicos(docs_reales, chunks_reales):
    otra_vez = fragmentar(docs_reales, contar_palabras)
    ids = [c.id for c in chunks_reales]

    assert ids == [c.id for c in otra_vez]
    assert len(set(ids)) == len(ids)


def test_reindexar_no_duplica(chunks_reales):
    store = InMemoryVectorStore(EmbeddingsPalabrasClave())

    indexar(store, chunks_reales)
    indexar(store, chunks_reales)

    assert len(store.store) == len(chunks_reales)
