"""Persistencia y comprobación de las tablas limpias del ETL Airbnb Bogotá."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.config import SQLITE_PATH, TABLAS_SALIDA, XLSX_PATH
from src.logger import obtener_logger

logger = obtener_logger("carga")

# El calendario diario puede superar los siete millones de registros;
# se conserva completo en SQLite, pero no se exporta al libro de Excel.
TABLAS_EXCEL = tuple(nombre for nombre in TABLAS_SALIDA if nombre != "calendar")
FILAS_MAXIMAS_EXCEL = 1_048_576  # Incluye la fila de encabezados.
TAMANIO_LOTE_SQLITE = 10_000


class Carga:
    """Guarda seis DataFrames transformados en SQLite y cinco hojas XLSX.

    No lee MongoDB ni limpia los datos: esos pasos corresponden a otras
    clases. Comprueba la estructura de entrada y los registros almacenados.
    """

    def __init__(
        self,
        tablas: dict[str, pd.DataFrame],
        sqlite_path: Path = SQLITE_PATH,
        xlsx_path: Path = XLSX_PATH,
    ) -> None:
        """Recibe los datos transformados y las rutas de salida del proyecto."""
        self.tablas = tablas
        self.sqlite_path = Path(sqlite_path)
        self.xlsx_path = Path(xlsx_path)

    def _validar_tablas(self) -> None:
        """Exige el contrato de seis DataFrames acordado con transformación."""
        if not isinstance(self.tablas, dict):
            raise TypeError("La carga requiere un diccionario de DataFrames")

        esperadas = set(TABLAS_SALIDA)
        recibidas = set(self.tablas)
        faltantes = sorted(esperadas - recibidas)
        adicionales = sorted(recibidas - esperadas)
        if faltantes or adicionales:
            raise ValueError(
                f"Tablas incompatibles: faltantes={faltantes}, adicionales={adicionales}"
            )

        for nombre in TABLAS_SALIDA:
            df = self.tablas[nombre]
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"La tabla '{nombre}' no es un DataFrame")
            if df.columns.empty:
                raise ValueError(f"La tabla '{nombre}' no tiene columnas")
            if not df.columns.is_unique:
                raise ValueError(f"La tabla '{nombre}' contiene columnas duplicadas")

    def cargar_sqlite(self) -> None:
        """Inserta las seis tablas completas y comprueba los conteos en SQLite.

        Se utiliza chunksize para reducir la memoria temporal durante las
        inserciones. No se convierte toda columna object a string porque
        esa conversión convertiría valores faltantes en los textos 'None' o
        '<NA>'. Pandas puede escribir los nulos como NULL de SQLite.
        """
        self._validar_tablas()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Iniciando carga SQLite: %s", self.sqlite_path)

        try:
            with sqlite3.connect(self.sqlite_path) as conexion:
                for nombre in TABLAS_SALIDA:
                    df = self.tablas[nombre]
                    logger.info("Cargando '%s' (%s filas)", nombre, f"{len(df):,}")

                    df.to_sql(
                        nombre,
                        conexion,
                        if_exists="replace",
                        index=False,
                        chunksize=TAMANIO_LOTE_SQLITE,
                    )

                    # Los nombres provienen de una lista fija del proyecto,
                    # no de la entrada del usuario.
                    cargadas = conexion.execute(
                        f'SELECT COUNT(*) FROM "{nombre}"'
                    ).fetchone()[0]
                    if cargadas != len(df):
                        raise ValueError(
                            f"Verificación fallida en '{nombre}': "
                            f"se esperaban {len(df):,} filas y se cargaron {cargadas:,}"
                        )
                    logger.info("Tabla '%s' verificada: %s filas", nombre, f"{cargadas:,}")
        except Exception:
            logger.exception("Error al cargar o verificar SQLite")
            raise

        logger.info("Carga SQLite terminada correctamente")

    def exportar_xlsx(self) -> None:
        """Crea un XLSX con cinco hojas, excluyendo el calendario diario.

        Verifica el límite de filas de Excel para evitar una exportación
        incompleta que parezca exitosa.
        """
        self._validar_tablas()
        self.xlsx_path.parent.mkdir(parents=True, exist_ok=True)

        for nombre in TABLAS_EXCEL:
            cantidad_con_encabezado = len(self.tablas[nombre]) + 1
            if cantidad_con_encabezado > FILAS_MAXIMAS_EXCEL:
                raise ValueError(
                    f"'{nombre}' tiene {len(self.tablas[nombre]):,} filas; "
                    "supera el límite de una hoja Excel. "
                    "No se exportará una tabla truncada."
                )

        logger.info("Iniciando exportación a XLSX: %s", self.xlsx_path)
        try:
            with pd.ExcelWriter(self.xlsx_path, engine="openpyxl") as writer:
                for nombre in TABLAS_EXCEL:
                    df = self.tablas[nombre]
                    df.to_excel(writer, sheet_name=nombre, index=False)
                    logger.info("Hoja '%s' exportada: %s filas", nombre, f"{len(df):,}")
        except Exception:
            logger.exception("Error durante la exportación a Excel")
            raise

        logger.info("Excel generado correctamente (sin la tabla 'calendar')")

    def cargar_todo(self) -> None:
        """Ejecuta SQLite y después Excel; solo termina si ambos funcionan."""
        logger.info("Inicio de la etapa de carga")
        self.cargar_sqlite()
        self.exportar_xlsx()
        logger.info("Etapa de carga completada correctamente")
