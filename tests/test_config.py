"""Pruebas unitarias para la configuración y contratos del ETL."""

import pytest

from src import config
from src.config import _leer_entero_positivo
from src.contratos import CLAVES_COLECCIONES, CampoDataset, ClaveColeccion


def test_contratos_claves_colecciones():
    assert ClaveColeccion.LISTINGS.value == "listings"
    assert ClaveColeccion.REVIEWS.value == "reviews"
    assert ClaveColeccion.CALENDAR.value == "calendar"
    assert len(CLAVES_COLECCIONES) == 3


def test_contratos_campos_dataset():
    assert CampoDataset.ID_MONGO.value == "_id"
    assert CampoDataset.ID_LISTING.value == "id"
    assert CampoDataset.LISTING_ID.value == "listing_id"


def test_leer_entero_positivo(monkeypatch):
    monkeypatch.setenv("TEST_VAR", "100")
    assert _leer_entero_positivo("TEST_VAR", 10) == 100

    monkeypatch.delenv("TEST_VAR", raising=False)
    assert _leer_entero_positivo("TEST_VAR", 50) == 50

    monkeypatch.setenv("TEST_VAR", "-5")
    with pytest.raises(ValueError, match="debe ser un entero positivo"):
        _leer_entero_positivo("TEST_VAR", 10)

    monkeypatch.setenv("TEST_VAR", "invalido")
    with pytest.raises(ValueError, match="debe ser un entero positivo"):
        _leer_entero_positivo("TEST_VAR", 10)


def test_config_rutas_y_colecciones():
    assert config.SQLITE_PATH.name == "airbnb_bogota.db"
    assert config.XLSX_PATH.name == "airbnb_bogota.xlsx"
    for clave in CLAVES_COLECCIONES:
        assert clave in config.COLECCIONES
        assert isinstance(config.COLECCIONES[clave], str)
