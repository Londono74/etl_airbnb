import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "airbnb_bogota_etl")

# Llave interna del proyecto -> nombre de la colección en MongoDB
COLECCIONES = {
    "listings": "Listings",
    "reviews": "Reviews",
    "calendar": "Calendar",
}

URL_DATOS = "https://data.insideairbnb.com/colombia/dc/bogot%C3%A1/2026-06-21/data"

DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
SQLITE_PATH = OUTPUT_DIR / "airbnb_bogota.db"
XLSX_PATH = OUTPUT_DIR / "airbnb_bogota.xlsx"

# Tablas que produce la fase de transformación y que se cargan en SQLite / XLSX
TABLAS_SALIDA = [
    "listings",
    "hosts",
    "amenities",
    "reviews",
    "calendar",
    "calendar_mensual",
]
