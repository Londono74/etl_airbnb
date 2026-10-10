"""Configuración central del proyecto ETL Airbnb Bogotá.

Los valores de conexión se pueden sobrescribir con un archivo ``.env``
en la raíz del proyecto (ver ``.env.example``).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from src.contratos import CampoDataset, ClaveColeccion

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _leer_entero_positivo(nombre: str, valor_predeterminado: int) -> int:
    """Lee una variable entera positiva y da un error claro si está mal configurada."""
    valor = os.getenv(nombre)
    if valor is None:
        return valor_predeterminado
    try:
        numero = int(valor)
    except ValueError as error:
        raise ValueError(f"La variable {nombre} debe ser un entero positivo") from error
    if numero <= 0:
        raise ValueError(f"La variable {nombre} debe ser un entero positivo")
    return numero


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "airbnb_bogota_etl")
MONGO_BATCH_SIZE_DEFAULT = 50_000
MONGO_IMPORT_BATCH_SIZE_DEFAULT = 200_000
MONGO_TIMEOUT_MS_DEFAULT = 5_000
MONGO_BATCH_SIZE = _leer_entero_positivo("MONGO_BATCH_SIZE", MONGO_BATCH_SIZE_DEFAULT)
MONGO_IMPORT_BATCH_SIZE = _leer_entero_positivo(
    "MONGO_IMPORT_BATCH_SIZE",
    MONGO_IMPORT_BATCH_SIZE_DEFAULT,
)
MONGO_TIMEOUT_MS = _leer_entero_positivo("MONGO_TIMEOUT_MS", MONGO_TIMEOUT_MS_DEFAULT)
MONGO_PING_COMMAND = "ping"
MONGO_ID_FIELD = CampoDataset.ID_MONGO.value
MONGO_PROJECTION_EXCLUDE_ID = {MONGO_ID_FIELD: 0}
EXTENSION_DATASET = ".csv.gz"

# Llave compartida del proyecto -> nombre de la colección en MongoDB.
COLECCIONES: dict[ClaveColeccion, str] = {
    ClaveColeccion.LISTINGS: "Listings",
    ClaveColeccion.REVIEWS: "Reviews",
    ClaveColeccion.CALENDAR: "Calendar",
}

CAMPOS_INDICE_MONGO: dict[ClaveColeccion, str] = {
    ClaveColeccion.LISTINGS: CampoDataset.ID_LISTING.value,
    ClaveColeccion.REVIEWS: CampoDataset.LISTING_ID.value,
    ClaveColeccion.CALENDAR: CampoDataset.LISTING_ID.value,
}

URL_DATOS = "https://data.insideairbnb.com/colombia/dc/bogot%C3%A1/2026-06-21/data"

DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
SQLITE_PATH = OUTPUT_DIR / "airbnb_bogota.db"
