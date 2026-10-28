"""Tests de la recuperacion: prefijos de e5, top-k y metadatos de fuente (sin Postgres)."""
import pytest

from app import rag
from app.config import Settings
from app.rag import EmbeddingsE5, Fragmento, buscar_conocimiento
from ingesta.cargar import indexar
from ingesta.documentos import cargar_documentos
from ingesta.fragmentos import fragmentar
from tests.fakes_rag import EmbeddingsPalabrasClave, InMemoryConRelevancia, contar_palabras


@pytest.fixture(scope="module")
def base():
    return EmbeddingsPalabrasClave()


@pytest.fixture(scope="module")
def store(base):
    store = InMemoryConRelevancia(EmbeddingsE5(base))
    indexar(store, fragmentar(cargar_documentos(), contar_palabras))
    return store


def test_prefijo_passage_al_indexar_y_query_al_consultar():
    base = EmbeddingsPalabrasClave()
    e5 = EmbeddingsE5(base)

    e5.embed_documents(["texto uno", "texto dos"])
    e5.embed_query("¿qué es la roña?")

    assert base.documentos_recibidos == ["passage: texto uno", "passage: texto dos"]
    assert base.consultas_recibidas == ["query: ¿qué es la roña?"]


def test_el_texto_guardado_no_lleva_prefijo(store):
    assert not any(d["text"].startswith("passage:") for d in store.store.values())


def test_buscar_aplica_query_y_devuelve_k_por_defecto(store, base):
    resultados = buscar_conocimiento("¿Qué es la roña del aguacate?", store=store)

    assert len(resultados) == rag.settings.rag_top_k == 4
    assert base.consultas_recibidas[-1] == "query: ¿Qué es la roña del aguacate?"


def test_k_configurable(store):
    assert len(buscar_conocimiento("riego", k=2, store=store)) == 2


@pytest.mark.parametrize(
    ("consulta", "archivo"),
    [
        ("¿Qué es la roña?", "enfermedades/rona.md"),
        ("¿Qué plaga se mete en el hueso? barrenador", "enfermedades/barrenadores-del-hueso.md"),
        ("¿Cómo protejo mis árboles de las heladas?", "manejo/heladas.md"),
    ],
)
def test_recupera_el_documento_correcto(store, consulta, archivo):
    assert buscar_conocimiento(consulta, k=1, store=store)[0].archivo == archivo


def test_fragmento_trae_la_fuente(store):
    primero = buscar_conocimiento("¿Qué es la roña?", store=store)[0]

    assert isinstance(primero, Fragmento)
    assert primero.titulo.startswith("Roña del aguacate")
    assert primero.subtema == "rona" and primero.tema == "enfermedades"
    assert primero.tipo == "enfermedad"
    assert primero.fuentes and primero.seccion
    assert primero.texto.startswith(f"{primero.titulo} > {primero.seccion}")


def test_resultados_ordenados_por_relevancia(store):
    relevancias = [f.relevancia for f in buscar_conocimiento("poda", store=store)]

    assert relevancias == sorted(relevancias, reverse=True)
    assert all(0 <= r <= 1 for r in relevancias)


@pytest.mark.parametrize("consulta", ["", "   "])
def test_consulta_vacia_no_busca(consulta):
    # Sin store: si intentara buscar, se conectaria a Postgres y fallaria.
    assert buscar_conocimiento(consulta) == []


def test_database_url_desde_postgres():
    config = Settings(
        database_url_env="",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="conocimiento",
        postgres_user="agroia",
        postgres_password="p@ss:w/rd",
    )

    assert config.database_url == "postgresql+psycopg://agroia:p%40ss%3Aw%2Frd@db:5432/conocimiento"


def test_database_url_explicita_tiene_prioridad():
    config = Settings(database_url_env="postgresql+psycopg://u:p@h:1/d", postgres_host="otro")

    assert config.database_url == "postgresql+psycopg://u:p@h:1/d"
