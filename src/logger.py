"""Módulo centralizado de logs del proceso ETL.

Cada ejecución genera un único archivo ``logs/log_YYYYMMDD_HHMM.txt`` que
comparten la extracción, la transformación y la carga. Cada clase obtiene
su logger con ``obtener_logger("nombre_modulo")`` y registra mensajes con
niveles INFO, WARNING y ERROR.
"""

import logging
from datetime import datetime

from src.config import LOG_DIR

_NOMBRE_RAIZ = "etl_airbnb"
_FORMATO = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"


def _configurar_raiz() -> logging.Logger:
    raiz = logging.getLogger(_NOMBRE_RAIZ)
    if raiz.handlers:
        return raiz

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    archivo = LOG_DIR / f"log_{datetime.now():%Y%m%d_%H%M}.txt"
    formato = logging.Formatter(_FORMATO, datefmt=_FORMATO_FECHA)

    manejador_archivo = logging.FileHandler(archivo, encoding="utf-8")
    manejador_archivo.setFormatter(formato)
    manejador_consola = logging.StreamHandler()
    manejador_consola.setFormatter(formato)

    raiz.addHandler(manejador_archivo)
    raiz.addHandler(manejador_consola)
    raiz.setLevel(logging.INFO)
    raiz.propagate = False
    return raiz


def obtener_logger(nombre: str) -> logging.Logger:
    """Devuelve un logger hijo que escribe en el archivo de la ejecución actual."""
    _configurar_raiz()
    return logging.getLogger(f"{_NOMBRE_RAIZ}.{nombre.split('.')[-1]}")
