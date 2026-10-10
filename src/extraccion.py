"""Extracción de las colecciones de Airbnb Bogotá desde MongoDB.

La clase consulta las colecciones configuradas en ``src/config.py`` y devuelve
un DataFrame de pandas por colección. Los documentos se conservan tal como
están en MongoDB, salvo el identificador interno ``_id``, que se excluye
porque no forma parte de los datos del dataset.

Uso desde la raíz del proyecto::

    datos = Extraccion().extraer_todo()
    listings = datos[ClaveColeccion.LISTINGS.value]
"""

from time import perf_counter

import pandas as pd
from pymongo import MongoClient

from src import config
from src.contratos import CLAVES_COLECCIONES, ClaveColeccion
from src.logger import obtener_logger

logger = obtener_logger("extraccion")


class Extraccion:
    """Lee Listings, Reviews y Calendar de la base MongoDB local.

    ``batch_size`` limita la cantidad de documentos que MongoDB entrega en
    cada lote de red. Los resultados se devuelven como DataFrames completos,
    como requiere el contrato con la clase ``Transformacion``; por eso el
    tamaño total de los datos sigue determinando la memoria necesaria.
    """

    def __init__(
        self,
        batch_size: int | None = None,
        timeout_ms: int | None = None,
    ):
        """Prepara los parámetros de consulta sin abrir aún una conexión.

        Args:
            batch_size: documentos por lote; usa ``config.MONGO_BATCH_SIZE`` si
                no se especifica.
            timeout_ms: espera máxima del servidor; usa
                ``config.MONGO_TIMEOUT_MS`` si no se especifica.

        Raises:
            ValueError: si el tamaño de lote o el tiempo de espera no son positivos.
        """
        batch_size = config.MONGO_BATCH_SIZE if batch_size is None else batch_size
        timeout_ms = config.MONGO_TIMEOUT_MS if timeout_ms is None else timeout_ms

        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size <= 0
        ):
            raise ValueError("batch_size debe ser un entero positivo")
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms <= 0
        ):
            raise ValueError("timeout_ms debe ser un entero positivo")

        self.batch_size = batch_size
        self.timeout_ms = timeout_ms

    def extraer_todo(self) -> dict[str, pd.DataFrame]:
        """Extrae las tres colecciones y cierra la conexión al finalizar.

        Devuelve exactamente las llaves ``listings``, ``reviews`` y
        ``calendar``. Cada DataFrame conserva los nombres y valores de sus
        columnas de origen, sin el campo interno ``_id`` de MongoDB.

        Raises:
            Exception: vuelve a lanzar los errores de conexión o consulta para
                impedir que el pipeline continúe con una extracción incompleta.
        """
        logger.info("Inicio de extracción desde MongoDB; base: %s", config.MONGO_DB)
        cliente: MongoClient | None = None

        try:
            claves_faltantes = [
                clave.value
                for clave in CLAVES_COLECCIONES
                if clave not in config.COLECCIONES
            ]
            if claves_faltantes:
                raise KeyError(
                    "Faltan colecciones en src/config.py para las llaves: "
                    f"{', '.join(claves_faltantes)}"
                )

            cliente = MongoClient(
                config.MONGO_URI,
                serverSelectionTimeoutMS=self.timeout_ms,
            )
            # MongoClient conecta de forma diferida; ping valida la conexión
            # antes de empezar a consultar las colecciones.
            cliente.admin.command(config.MONGO_PING_COMMAND)
            logger.info("Conexión establecida con MongoDB; base: %s", config.MONGO_DB)

            base = cliente[config.MONGO_DB]
            datos: dict[str, pd.DataFrame] = {}
            for clave in CLAVES_COLECCIONES:
                nombre_coleccion = config.COLECCIONES[clave]
                if (
                    not isinstance(nombre_coleccion, str)
                    or not nombre_coleccion.strip()
                ):
                    raise ValueError(
                        f"El nombre de la colección {clave.value} está vacío en src/config.py"
                    )
                logger.info("Extrayendo colección %s", nombre_coleccion)
                inicio = perf_counter()
                cursor = base[nombre_coleccion].find(
                    {},
                    config.MONGO_PROJECTION_EXCLUDE_ID,
                    batch_size=self.batch_size,
                )
                try:
                    dataframe = pd.DataFrame.from_records(cursor)
                finally:
                    cursor.close()
                datos[clave.value] = dataframe
                logger.info(
                    "Extracción completada: colección %s, %s registros y %s columnas "
                    "en %.2f segundos",
                    nombre_coleccion,
                    f"{len(dataframe):,}",
                    dataframe.shape[1],
                    perf_counter() - inicio,
                )

            return datos
        except Exception:
            logger.exception("Error durante la extracción desde MongoDB")
            raise
        finally:
            if cliente is not None:
                cliente.close()
                logger.info("Conexión con MongoDB cerrada")
