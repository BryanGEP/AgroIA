"""Permite que pytest encuentre el paquete 'app' sin importar desde donde se invoque."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
