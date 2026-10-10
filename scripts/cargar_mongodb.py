"""Prepara la base MongoDB local con los datasets de Inside Airbnb Bogotá.

Paso previo al ETL (lo exige el taller): descarga los archivos ``.csv.gz``
si no existen en ``data/``, los importa como las colecciones Listings,
Reviews y Calendar y valida que la cantidad de documentos coincida con
la cantidad de filas del archivo.

Uso (desde la raíz del proyecto):
    python scripts/cargar_mongodb.py
"""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from pymongo import MongoClient

from src.config import COLECCIONES, DATA_DIR, MONGO_DB, MONGO_URI, URL_DATOS
from src.logger import obtener_logger

logger = obtener_logger("cargar_mongodb")
TAMANO_LOTE = 200_000
INDICES = {"reviews": "listing_id", "calendar": "listing_id", "listings": "id"}


def descargar_si_falta(nombre: str) -> Path:
    ruta = DATA_DIR / f"{nombre}.csv.gz"
    if ruta.exists():
        logger.info("Archivo %s ya existe, no se descarga", ruta.name)
        return ruta
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{URL_DATOS}/{nombre}.csv.gz"
    logger.info("Descargando %s", url)
    urllib.request.urlretrieve(url, ruta)
    return ruta


def importar(db, nombre: str, ruta: Path) -> None:
    coleccion = db[COLECCIONES[nombre]]
    coleccion.drop()
    filas = 0
    for lote in pd.read_csv(ruta, chunksize=TAMANO_LOTE, low_memory=False):
        lote = lote.astype(object).where(lote.notna(), None)
        coleccion.insert_many(lote.to_dict("records"), ordered=False)
        filas += len(lote)
        logger.info("%s: %s documentos insertados", COLECCIONES[nombre], f"{filas:,}")

    coleccion.create_index(INDICES[nombre])
    documentos = coleccion.count_documents({})
    if documentos == filas:
        logger.info("Validación OK %s: %s filas = %s documentos", COLECCIONES[nombre], f"{filas:,}", f"{documentos:,}")
    else:
        logger.error("Validación FALLÓ %s: %s filas vs %s documentos", COLECCIONES[nombre], filas, documentos)


def main() -> None:
    cliente = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    cliente.admin.command("ping")
    logger.info("Conectado a MongoDB %s, base %s", MONGO_URI, MONGO_DB)
    db = cliente[MONGO_DB]
    for nombre in COLECCIONES:
        importar(db, nombre, descargar_si_falta(nombre))
    cliente.close()
    logger.info("Base MongoDB lista para el ETL")


if __name__ == "__main__":
    main()
