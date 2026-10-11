"""Pruebas unitarias para la clase Extraccion."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.contratos import ClaveColeccion
from src.extraccion import Extraccion


class CursorSimulado:
    """Simula un cursor de PyMongo como iterador."""

    def __init__(self, documentos):
        self._iter = iter(documentos)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iter)

    def close(self):
        pass


def test_extraccion_init_validaciones():
    ext = Extraccion(batch_size=1000, timeout_ms=3000)
    assert ext.batch_size == 1000
    assert ext.timeout_ms == 3000

    with pytest.raises(ValueError, match="batch_size debe ser un entero positivo"):
        Extraccion(batch_size=-1)

    with pytest.raises(ValueError, match="batch_size debe ser un entero positivo"):
        Extraccion(batch_size=0)

    with pytest.raises(ValueError, match="timeout_ms debe ser un entero positivo"):
        Extraccion(timeout_ms=-10)

    with pytest.raises(ValueError, match="timeout_ms debe ser un entero positivo"):
        Extraccion(timeout_ms=True)


@patch("src.extraccion.MongoClient")
def test_extraccion_extraer_todo_exitoso(mock_mongo_client_cls):
    mock_client = MagicMock()
    mock_mongo_client_cls.return_value = mock_client

    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    mock_db.__getitem__.return_value.find.side_effect = [
        CursorSimulado([{"id": 1, "name": "Alojamiento 1"}]),
        CursorSimulado([{"id": 2, "comments": "Excelente"}]),
        CursorSimulado([{"listing_id": 1, "available": "t"}]),
    ]

    ext = Extraccion()
    datos = ext.extraer_todo()

    # Validar llaves requeridas por el contrato
    assert set(datos.keys()) == {"listings", "reviews", "calendar"}
    for clave, df in datos.items():
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    assert datos["listings"]["id"].iloc[0] == 1
    assert datos["reviews"]["comments"].iloc[0] == "Excelente"
    assert datos["calendar"]["listing_id"].iloc[0] == 1

    # Validar ping y cierre de conexión
    mock_client.admin.command.assert_called_with("ping")
    mock_client.close.assert_called_once()


@patch("src.extraccion.MongoClient")
def test_extraccion_extraer_coleccion(mock_mongo_client_cls):
    mock_client = MagicMock()
    mock_mongo_client_cls.return_value = mock_client

    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db
    mock_db.__getitem__.return_value.find.return_value = CursorSimulado([{"id": 10, "comments": "Excelente"}])

    ext = Extraccion()
    df = ext.extraer_coleccion(ClaveColeccion.REVIEWS)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df["comments"].iloc[0] == "Excelente"
    mock_client.close.assert_called_once()
