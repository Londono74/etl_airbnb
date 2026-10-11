from __future__ import annotations

import ast
import re

import numpy as np
import pandas as pd

from src.logger import obtener_logger

logger = obtener_logger("transformacion")

MAX_NOCHES = 365

AMENIDADES_CLAVE = {
    "wifi": "tiene_wifi",
    "kitchen": "tiene_cocina",
    "parking": "tiene_parqueadero",
    "pool": "tiene_piscina",
    "air conditioning": "tiene_aire",
    "washer": "tiene_lavadora",
}


class Transformacion:

    def __init__(self, fuentes: dict[str, pd.DataFrame]) -> None:

        self.listings = fuentes["listings"].copy()
        self.reviews = fuentes["reviews"].copy()
        self.calendar = fuentes["calendar"].copy()
        self.salida: dict[str, pd.DataFrame] = {}


    @staticmethod
    def _precio_a_numero(serie: pd.Series) -> pd.Series:
        """Convierte '$284,294.01' -> 284294.01 (float)."""
        limpia = serie.astype(str).str.replace(r"[^\d.]", "", regex=True).replace("", np.nan)
        return pd.to_numeric(limpia, errors="coerce")

    @staticmethod
    def _derivar_fechas(df: pd.DataFrame, columna: str) -> pd.DataFrame:
        """Convierte ``columna`` a datetime y deriva year, month, day, quarter."""
        df[columna] = pd.to_datetime(df[columna], errors="coerce")
        df["year"] = df[columna].dt.year
        df["month"] = df[columna].dt.month
        df["day"] = df[columna].dt.day
        df["quarter"] = df[columna].dt.quarter
        return df

    def transformar_listings(self) -> pd.DataFrame:
        df = self.listings
        n0 = len(df)

        vacias = [c for c in df.columns if df[c].isna().all()]
        df = df.drop(columns=vacias)
        logger.info("Listings: %s columnas 100%% vacías descartadas", len(vacias))

        df["price"] = self._precio_a_numero(df["price"])
        logger.info("Listings: columna 'price' normalizada a numérico")

        validos = df["price"].dropna()
        p99 = validos.quantile(0.99)
        df["price_outlier"] = df["price"] > p99
        logger.warning(
            "Listings: %s precios marcados como atípicos (> p99 = %.0f); se conservan",
            int(df["price_outlier"].sum()), p99,
        )

        df["price_tier"] = pd.qcut(
            df["price"], 4, labels=["Economico", "Moderado", "Alto", "Lujo"]
        )

        imposibles = int((df["minimum_nights"] > MAX_NOCHES).sum())
        if imposibles:
            logger.warning("Listings: %s registros con minimum_nights > %s", imposibles, MAX_NOCHES)
        else:
            logger.info("Listings: 0 registros con minimum_nights > %s (regla sin efecto)", MAX_NOCHES)

        self.salida["listings"] = df
        logger.info("Listings transformado: %s -> %s registros", f"{n0:,}", f"{len(df):,}")
        return df


    def construir_hosts(self) -> pd.DataFrame:
        df = self.salida.get("listings", self.listings)
        cols = [c for c in ["host_id", "host_name", "host_is_superhost",
                            "host_identity_verified", "host_listings_count"] if c in df.columns]
        hosts = df[cols].drop_duplicates("host_id").reset_index(drop=True)
        self.salida["hosts"] = hosts
        logger.info("Hosts construido: %s anfitriones únicos", f"{len(hosts):,}")
        return hosts

 
    def construir_amenities(self) -> pd.DataFrame:
        df = self.salida.get("listings", self.listings)
        if "amenities" not in df.columns:
            self.salida["amenities"] = pd.DataFrame(columns=["id"])
            return self.salida["amenities"]

        def parsear(valor):
            try:
                return [a.lower() for a in ast.literal_eval(valor)]
            except (ValueError, SyntaxError):
                return [a.strip().strip('"').lower() for a in re.sub(r"[\[\]]", "", str(valor)).split(",")]

        listas = df["amenities"].apply(parsear)
        amen = pd.DataFrame({"id": df["id"].values})
        for palabra, columna in AMENIDADES_CLAVE.items():
            amen[columna] = listas.apply(lambda xs: any(palabra in x for x in xs))
        self.salida["amenities"] = amen
        logger.info("Amenities expandido: %s amenidades clave por alojamiento", len(AMENIDADES_CLAVE))
        return amen

    def transformar_reviews(self) -> pd.DataFrame:
        df = self.reviews
        n0 = len(df)
        df = self._derivar_fechas(df, "date")
        df["comments"] = df["comments"].fillna("Sin comentario")
        self.salida["reviews"] = df
        logger.info("Reviews transformado: %s -> %s registros", f"{n0:,}", f"{len(df):,}")
        return df

    def transformar_calendar(self) -> pd.DataFrame:
        df = self.calendar
        n0 = len(df)
        df = self._derivar_fechas(df, "date")
        df["disponible"] = (df["available"] == "t")
        df["ocupado"] = (df["available"] == "f")
        if "price" in df.columns:
            df["price"] = self._precio_a_numero(df["price"])
        self.salida["calendar"] = df
        logger.info("Calendar transformado: %s -> %s registros", f"{n0:,}", f"{len(df):,}")

        mensual = (
            df.assign(periodo=df["date"].dt.to_period("M").astype(str))
            .groupby("periodo")
            .agg(dias=("ocupado", "size"),
                 dias_ocupados=("ocupado", "sum"),
                 pct_ocupacion=("ocupado", lambda s: round(s.mean() * 100, 2)))
            .reset_index()
        )
        self.salida["calendar_mensual"] = mensual
        logger.info("Calendar agregado por mes: %s periodos", len(mensual))
        return df

    def transformar_todo(self) -> dict[str, pd.DataFrame]:
        logger.info("Iniciando fase de transformación")
        self.transformar_listings()
        self.construir_hosts()
        self.construir_amenities()
        self.transformar_reviews()
        self.transformar_calendar()
        logger.info("Transformación finalizada. Tablas producidas: %s", list(self.salida))
        return self.salida
