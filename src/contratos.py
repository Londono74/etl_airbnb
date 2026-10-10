"""Vocabulario compartido entre las fases del proceso ETL."""

from enum import StrEnum


class ClaveColeccion(StrEnum):
    """Llaves estables para los DataFrames extraídos de MongoDB."""

    LISTINGS = "listings"
    REVIEWS = "reviews"
    CALENDAR = "calendar"


class CampoDataset(StrEnum):
    """Campos de origen compartidos entre la carga y la extracción."""

    ID_MONGO = "_id"
    ID_LISTING = "id"
    LISTING_ID = "listing_id"


CLAVES_COLECCIONES = tuple(ClaveColeccion)
