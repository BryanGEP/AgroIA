"""Version de consola del agente AgroIA (ejecutable localmente).

Uso:
    python cli.py
"""
from app.agent import chat

SESSION = "cli"


def main():
    print("AgroIA - asistente para productores de aguacate")
    print("Escribe 'salir' para terminar.\n")
    while True:
        user_input = input("Tu: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "salir"):
            print("Hasta luego")
            break
        answer = chat(user_input, session_id=SESSION)
        print(f"AgroIA: {answer}\n")


if __name__ == "__main__":
    main()
