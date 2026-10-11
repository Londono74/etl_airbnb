from __future__ import annotations

import time

import pandas as pd
from pymongo import MongoClient

from src.config import COLECCIONES, MONGO_DB, MONGO_URI
from src.logger import obtener_logger

logger = obtener_logger("extraccion")


class Extraccion:


    def __init__(self, uri: str = MONGO_URI, base_datos: str = MONGO_DB) -> None:
        self.uri = uri
        self.nombre_base = base_datos
        self._cliente: MongoClient | None = None
        self._db = None

    def conectar(self):
        """Abre la conexión con MongoDB y valida que responda."""
        self._cliente = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
        self._cliente.admin.command("ping")  # lanza excepción si no conecta
        self._db = self._cliente[self.nombre_base]
        logger.info("Conexión establecida con MongoDB (%s), base '%s'", self.uri, self.nombre_base)
        return self._db

    def cerrar(self) -> None:
        """Cierra la conexión con MongoDB."""
        if self._cliente is not None:
            self._cliente.close()
            logger.info("Conexión con MongoDB cerrada")
            self._cliente = None
            self._db = None

    def extraer_coleccion(self, llave: str) -> pd.DataFrame:

        if self._db is None:
            self.conectar()

        nombre = COLECCIONES[llave]
        inicio = time.perf_counter()
        documentos = list(self._db[nombre].find({}, {"_id": 0}))
        df = pd.DataFrame(documentos)
        segundos = time.perf_counter() - inicio

        logger.info(
            "Extracción de '%s': %s registros, %s columnas en %.2f s",
            nombre, f"{len(df):,}", df.shape[1], segundos,
        )
        return df

    def extraer_todo(self) -> dict[str, pd.DataFrame]:

        self.conectar()
        try:
            fuentes = {llave: self.extraer_coleccion(llave) for llave in COLECCIONES}
        finally:
            self.cerrar()

        total = sum(len(df) for df in fuentes.values())
        logger.info("Extracción finalizada. Total de registros extraídos: %s", f"{total:,}")
        return fuentes
