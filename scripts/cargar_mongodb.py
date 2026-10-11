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

from src import config
from src.contratos import CLAVES_COLECCIONES, ClaveColeccion
from src.logger import obtener_logger

logger = obtener_logger("cargar_mongodb")


def descargar_si_falta(nombre: ClaveColeccion) -> Path:
    """Descarga el dataset configurado solo cuando aún no existe localmente."""
    ruta = config.DATA_DIR / f"{nombre.value}{config.EXTENSION_DATASET}"
    if ruta.exists():
        logger.info("Archivo %s ya existe, no se descarga", ruta.name)
        return ruta
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{config.URL_DATOS}/{nombre.value}{config.EXTENSION_DATASET}"
    logger.info("Descargando %s", url)
    urllib.request.urlretrieve(url, ruta)
    return ruta


def importar(db, nombre: ClaveColeccion, ruta: Path) -> None:
    """Reemplaza una colección con los registros del CSV y crea su índice."""
    nombre_coleccion = config.COLECCIONES.get(nombre)
    campo_indice = config.CAMPOS_INDICE_MONGO.get(nombre)
    if not nombre_coleccion or not campo_indice:
        raise ValueError(
            f"Falta configurar la colección o su índice para {nombre.value}"
        )

    coleccion = db[nombre_coleccion]
    coleccion.drop()
    filas = 0
    for lote in pd.read_csv(
        ruta,
        chunksize=config.MONGO_IMPORT_BATCH_SIZE,
        low_memory=False,
    ):
        lote = lote.astype(object).where(lote.notna(), None)
        coleccion.insert_many(lote.to_dict("records"), ordered=False)
        filas += len(lote)
        logger.info("%s: %s documentos insertados", nombre_coleccion, f"{filas:,}")

    coleccion.create_index(campo_indice)
    documentos = coleccion.count_documents({})
    if documentos == filas:
        logger.info(
            "Validación OK %s: %s filas = %s documentos",
            nombre_coleccion,
            f"{filas:,}",
            f"{documentos:,}",
        )
    else:
        logger.error(
            "Validación FALLÓ %s: %s filas vs %s documentos",
            nombre_coleccion,
            filas,
            documentos,
        )
        raise RuntimeError(
            f"La validación de {nombre_coleccion} no coincide: "
            f"{filas} filas frente a {documentos} documentos"
        )


def main() -> None:
    """Carga y valida en MongoDB los tres datasets fuente del taller."""
    cliente = None
    try:
        cliente = MongoClient(
            config.MONGO_URI,
            serverSelectionTimeoutMS=config.MONGO_TIMEOUT_MS,
        )
        cliente.admin.command(config.MONGO_PING_COMMAND)
        logger.info("Conexión establecida con MongoDB; base: %s", config.MONGO_DB)
        db = cliente[config.MONGO_DB]
        for nombre in CLAVES_COLECCIONES:
            importar(db, nombre, descargar_si_falta(nombre))
        logger.info("Base MongoDB preparada para el ETL")
    except Exception:
        logger.exception("Error durante la carga inicial de MongoDB")
        raise
    finally:
        if cliente is not None:
            cliente.close()
            logger.info("Conexión con MongoDB cerrada")


if __name__ == "__main__":
    main()
