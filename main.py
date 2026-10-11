import time

from src.carga import Carga
from src.extraccion import Extraccion
from src.logger import obtener_logger
from src.transformacion import Transformacion

logger = obtener_logger("pipeline")


def main() -> None:
    inicio = time.perf_counter()
    logger.info("=== Inicio del proceso ETL Airbnb Bogotá ===")
    try:
        #Extracción
        fuentes = Extraccion().extraer_todo()

        #Transformación
        tablas = Transformacion(fuentes).transformar_todo()

        #Carga
        Carga(tablas).cargar_todo()

        segundos = time.perf_counter() - inicio
        logger.info("=== Proceso ETL finalizado con éxito en %.1f segundos ===", segundos)
    except Exception:
        logger.exception("El proceso ETL terminó con un error")
        raise


if __name__ == "__main__":
    main()
