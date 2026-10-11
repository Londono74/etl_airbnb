
from __future__ import annotations

import sqlite3

import pandas as pd

from src.config import SQLITE_PATH, XLSX_PATH
from src.logger import obtener_logger

logger = obtener_logger("carga")


class Carga:
    """Carga las tablas transformadas en SQLite y en un archivo XLSX."""

    def __init__(self, tablas: dict[str, pd.DataFrame],
                 sqlite_path=SQLITE_PATH, xlsx_path=XLSX_PATH) -> None:
        self.tablas = tablas
        self.sqlite_path = sqlite_path
        self.xlsx_path = xlsx_path


    def cargar_sqlite(self) -> None:
        """Inserta cada tabla en SQLite y verifica el conteo de registros."""
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as conexion:
            logger.info("Conexión a SQLite '%s' abierta", self.sqlite_path.name)
            for nombre, df in self.tablas.items():

                df_sql = df.copy()
                for col in df_sql.columns:
                    if df_sql[col].dtype == "object" or str(df_sql[col].dtype) == "category":
                        df_sql[col] = df_sql[col].astype(str)
                df_sql.to_sql(nombre, conexion, if_exists="replace", index=False)
                cargados = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {nombre}", conexion)["n"][0]
                if cargados == len(df):
                    logger.info("Tabla '%s' cargada: %s registros (verificado)", nombre, f"{cargados:,}")
                else:
                    logger.error("Tabla '%s': %s esperados vs %s cargados", nombre, len(df), cargados)
        logger.info("Carga a SQLite finalizada")

   
    def exportar_xlsx(self) -> None:
        """Exporta todas las tablas a un XLSX, una hoja por tabla."""
        self.xlsx_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(self.xlsx_path, engine="openpyxl") as writer:
            for nombre, df in self.tablas.items():

                hoja = df
                if len(df) > 1_000_000:
                    hoja = df.head(1_000_000)
                    logger.warning("Tabla '%s' truncada a 1.000.000 filas para el XLSX", nombre)
                hoja.to_excel(writer, sheet_name=nombre[:31], index=False)
                logger.info("Hoja '%s' exportada al XLSX (%s filas)", nombre, f"{len(hoja):,}")
        logger.info("Exportación a '%s' finalizada", self.xlsx_path.name)

    def cargar_todo(self) -> None:
        self.cargar_sqlite()
        self.exportar_xlsx()
