"""Tests de SimpleMemory, el respaldo por session_id para el CLI y /chat."""
from app.memory import SimpleMemory


def test_guarda_solo_los_ultimos_mensajes():
    memoria = SimpleMemory(max_messages=3)
    for i in range(5):
        memoria.add("s", "user", str(i))

    assert [m["content"] for m in memoria.get("s")] == ["2", "3", "4"]


def test_sesion_inexistente_devuelve_lista_vacia_sin_crearla():
    memoria = SimpleMemory()

    assert memoria.get("nueva") == []
    assert len(memoria) == 0


def test_limite_de_sesiones_descarta_la_menos_usada():
    memoria = SimpleMemory(max_sessions=2)
    memoria.add("a", "user", "x")
    memoria.add("b", "user", "x")
    memoria.get("a")  # "a" se usa de nuevo; "b" queda como la menos reciente
    memoria.add("c", "user", "x")

    assert len(memoria) == 2
    assert memoria.get("b") == []
    assert memoria.get("a") != []


def test_reset_borra_la_sesion():
    memoria = SimpleMemory()
    memoria.add("s", "user", "x")

    memoria.reset("s")

    assert memoria.get("s") == []
