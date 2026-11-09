"""Ingesta de la base de conocimiento al vector store (germen del futuro svc-ingesta).

Flujo: documentos.cargar_documentos -> fragmentos.fragmentar -> cargar.indexar.
Se ejecuta aparte del servicio: `python -m ingesta.cargar`.
"""
