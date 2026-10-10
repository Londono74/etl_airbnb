"""Transformación de los datos de Airbnb Bogotá.

Recibe los DataFrames crudos que entrega la clase ``Extraccion`` en un
diccionario con las llaves ``listings``, ``reviews`` y ``calendar`` y
genera las tablas limpias que recibe la clase ``Carga``:

- ``listings``: una fila por propiedad, con precio numérico y categorizado.
- ``hosts``: una fila por anfitrión (información del host desanidada).
- ``amenities``: una fila por propiedad y amenidad (lista anidada expandida).
- ``reviews``: una fila por reseña, con fecha estándar y variables derivadas.
- ``calendar``: una fila por propiedad y día, con año, mes, día y trimestre.
- ``calendar_mensual``: disponibilidad resumida por propiedad y mes.

Uso::

    datos = Extraccion().extraer_todo()
    tablas = Transformacion(datos).transformar_todo()
"""

import json

import numpy as np
import pandas as pd

from src.logger import obtener_logger

logger = obtener_logger("transformacion")

FUENTES_REQUERIDAS = ("listings", "reviews", "calendar")

# Columnas con este porcentaje de nulos o más no aportan información y se eliminan.
UMBRAL_NULOS = 0.95

# URLs, imágenes, metadatos del scraping y el JSON crudo de la cotización
# (sus valores útiles ya vienen en price_quote_total_price y
# price_quote_price_per_night). No sirven para el análisis.
COLUMNAS_NO_ANALITICAS = [
    "listing_url", "scrape_id", "source", "picture_url", "host_url",
    "host_profile_id", "host_profile_url", "host_thumbnail_url",
    "host_picture_url", "price_quote_raw",
]

COLUMNAS_FECHA_LISTINGS = [
    "last_scraped", "host_since", "first_review", "last_review",
    "calendar_last_scraped", "price_quote_checkin_date", "price_quote_checkout_date",
]

# Rangos de precio por noche en COP. Los cortes se redondearon a partir de
# los cuartiles observados en el EDA (Q1 ≈ 110.000, mediana ≈ 160.000,
# Q3 ≈ 230.000) para que cada categoría sea interpretable por negocio.
RANGOS_PRECIO = [0, 100_000, 200_000, 400_000, np.inf]
CATEGORIAS_PRECIO = ["Económico", "Medio", "Alto", "Premium"]

# Amenidades relevantes para un huésped en Bogotá: se convierten en columnas
# booleanas para poder filtrar y agrupar sin recorrer la lista completa.
AMENIDADES_CLAVE = {
    "tiene_wifi": "wifi",
    "tiene_cocina": "kitchen",
    "tiene_parqueadero": "parking",
    "tiene_lavadora": "washer",
    "tiene_espacio_trabajo": "dedicated workspace",
    "permite_estadias_largas": "long term stays allowed",
}


class Transformacion:
    """Limpia, estandariza y enriquece los datos extraídos de MongoDB."""

    def __init__(self, datos: dict[str, pd.DataFrame]):
        faltantes = [fuente for fuente in FUENTES_REQUERIDAS if fuente not in datos]
        if faltantes:
            logger.error("Faltan fuentes para transformar: %s", faltantes)
            raise ValueError(f"Faltan fuentes para transformar: {faltantes}")
        self.datos = datos
        self.tablas: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Utilidades reutilizables
    # ------------------------------------------------------------------
    @staticmethod
    def _quitar_id_mongo(df: pd.DataFrame) -> pd.DataFrame:
        """Elimina el ``_id`` interno de MongoDB, que no es un dato del negocio."""
        return df.drop(columns=["_id"], errors="ignore")

    @staticmethod
    def _registrar_conteo(tabla: str, antes: int, despues: int) -> None:
        eliminados = antes - despues
        logger.info("%s: %s registros antes, %s después (%s eliminados)",
                    tabla, f"{antes:,}", f"{despues:,}", f"{eliminados:,}")

    @staticmethod
    def _eliminar_duplicados(df: pd.DataFrame, llave: list[str], tabla: str) -> pd.DataFrame:
        """Elimina filas repetidas por su llave natural y lo deja en el log."""
        duplicados = int(df.duplicated(subset=llave).sum())
        if duplicados:
            logger.warning("%s: %s duplicados por %s eliminados", tabla, f"{duplicados:,}", llave)
        else:
            logger.info("%s: sin duplicados por %s", tabla, llave)
        return df.drop_duplicates(subset=llave, keep="first")

    @staticmethod
    def _limpiar_texto(serie: pd.Series) -> pd.Series:
        """Quita etiquetas HTML (``<br />``), espacios repetidos y espacios en los extremos."""
        return (
            serie.astype("string")
            .str.replace(r"<[^>]+>", " ", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )

    @staticmethod
    def _a_fecha_estandar(serie: pd.Series) -> pd.Series:
        """Convierte a texto ``YYYY-MM-DD``; las fechas inválidas quedan como nulo."""
        return pd.to_datetime(serie, errors="coerce").dt.strftime("%Y-%m-%d")

    @staticmethod
    def normalizar_precio(serie: pd.Series) -> pd.Series:
        """Convierte textos como ``"$284,294.01"`` en el número ``284294.01``.

        Se eliminan el símbolo ``$`` y el separador de miles ``,``; los valores
        que no se puedan convertir quedan como nulo en lugar de romper el proceso.
        """
        texto = serie.astype("string").str.replace(r"[$,\s]", "", regex=True)
        return pd.to_numeric(texto, errors="coerce")

    @staticmethod
    def categorizar_precio(precio: pd.Series) -> pd.Series:
        """Asigna el rango de precio; las propiedades sin precio quedan como ``Sin precio``."""
        categoria = pd.cut(precio, bins=RANGOS_PRECIO, labels=CATEGORIAS_PRECIO, right=False)
        return categoria.astype("object").fillna("Sin precio")

    @staticmethod
    def derivar_fecha(df: pd.DataFrame, columna: str = "date") -> pd.DataFrame:
        """Agrega año, mes, día, trimestre y día de la semana a partir de ``columna``.

        Se usan enteros pequeños para no multiplicar la memoria en el calendario
        (7 millones de filas).
        """
        fechas = pd.to_datetime(df[columna], errors="coerce")
        df["anio"] = fechas.dt.year.astype("Int16")
        df["mes"] = fechas.dt.month.astype("Int8")
        df["dia"] = fechas.dt.day.astype("Int8")
        df["trimestre"] = fechas.dt.quarter.astype("Int8")
        df["dia_semana"] = fechas.dt.dayofweek.astype("Int8")  # 0 = lunes
        df["es_fin_de_semana"] = fechas.dt.dayofweek >= 5
        return df

    # ------------------------------------------------------------------
    # Listings, hosts y amenities
    # ------------------------------------------------------------------
    def transformar_listings(self) -> pd.DataFrame:
        """Limpia las propiedades y genera también las tablas ``hosts`` y ``amenities``."""
        df = self._quitar_id_mongo(self.datos["listings"])
        antes = len(df)
        df = self._eliminar_duplicados(df, ["id"], "listings")

        # Columnas vacías: en este corte de Inside Airbnb varias columnas
        # (p. ej. host_response_rate, neighbourhood, instant_bookable) vienen
        # 100 % nulas; imputarlas sería inventar datos.
        porcentaje_nulos = df.isna().mean()
        vacias = porcentaje_nulos[porcentaje_nulos >= UMBRAL_NULOS].index.tolist()
        if vacias:
            logger.warning("listings: %s columnas con >= %.0f%% nulos eliminadas: %s",
                           len(vacias), UMBRAL_NULOS * 100, vacias)
        df = df.drop(columns=vacias + COLUMNAS_NO_ANALITICAS, errors="ignore")

        # Texto: nombres y descripciones traen HTML y espacios sobrantes.
        for columna in ["name", "description", "host_name", "host_location", "host_about",
                        "neighbourhood_cleansed", "property_type", "room_type", "bathrooms_text"]:
            if columna in df:
                df[columna] = self._limpiar_texto(df[columna])
        df["description"] = df["description"].fillna("")
        if "host_location" in df:
            df["host_location"] = df["host_location"].fillna("Sin información")

        # Booleanos: Airbnb usa "t"/"f"; se convierten a True/False.
        for columna in df.columns:
            valores = set(df[columna].dropna().unique()) if df[columna].dtype == object else set()
            if valores and valores <= {"t", "f"}:
                df[columna] = df[columna].map({"t": True, "f": False})
        logger.info("listings: columnas t/f convertidas a booleanas")

        # Precio: de texto con $ y comas a número.
        df["price"] = self.normalizar_precio(df["price"])
        sin_precio = int(df["price"].isna().sum())
        if sin_precio:
            logger.warning("listings: %s propiedades sin precio; se conservan con categoría 'Sin precio'",
                           f"{sin_precio:,}")

        # Atípicos de precio (regla IQR). Se marcan en lugar de eliminarse para
        # no perder la propiedad en los análisis que no dependen del precio.
        q1, q3 = df["price"].quantile([0.25, 0.75])
        limite_superior = q3 + 1.5 * (q3 - q1)
        df["precio_atipico"] = df["price"] > limite_superior
        logger.warning("listings: %s precios atípicos (> %s COP) marcados en precio_atipico",
                       f"{int(df['precio_atipico'].sum()):,}", f"{limite_superior:,.0f}")
        df["categoria_precio"] = self.categorizar_precio(df["price"])
        logger.info("listings: distribución de categoria_precio %s",
                    df["categoria_precio"].value_counts().to_dict())

        for columna in COLUMNAS_FECHA_LISTINGS:
            if columna in df:
                df[columna] = self._a_fecha_estandar(df[columna])
        logger.info("listings: fechas convertidas a formato YYYY-MM-DD")

        # Baños: cuando "bathrooms" es nulo se toma el número de "bathrooms_text"
        # ("1.5 shared baths" -> 1.5, "Half-bath" -> 0.5).
        texto_banos = df["bathrooms_text"].str.lower()
        banos_texto = pd.to_numeric(texto_banos.str.extract(r"([\d.]+)")[0], errors="coerce")
        banos_texto = banos_texto.mask(texto_banos.str.contains("half", na=False) & banos_texto.isna(), 0.5)
        completados = int((df["bathrooms"].isna() & banos_texto.notna()).sum())
        df["bathrooms"] = df["bathrooms"].fillna(banos_texto)
        df["bano_compartido"] = texto_banos.str.contains("shared", na=False)
        logger.info("listings: %s valores de bathrooms completados desde bathrooms_text", f"{completados:,}")

        # Habitaciones y camas: se imputa la mediana del mismo tipo de
        # habitación, porque un apartamento entero y un cuarto privado
        # tienen tamaños muy distintos.
        for columna in ["bedrooms", "beds", "bathrooms"]:
            nulos = int(df[columna].isna().sum())
            mediana = df.groupby("room_type")[columna].transform("median")
            df[columna] = df[columna].fillna(mediana).fillna(df[columna].median())
            logger.info("listings: %s nulos de %s imputados con la mediana por room_type",
                        f"{nulos:,}", columna)

        # Reseñas: si no hay reseñas, reviews_per_month es 0. Los puntajes
        # (review_scores_*) se dejan nulos: no existe una calificación que imputar.
        sin_resenas = df["number_of_reviews"] == 0
        df.loc[sin_resenas, "reviews_per_month"] = 0
        logger.info("listings: %s propiedades sin reseñas; puntajes se conservan nulos",
                    f"{int(sin_resenas.sum()):,}")

        if "license" in df:
            df["tiene_licencia"] = df["license"].notna()

        df, amenities = self._expandir_amenities(df)
        df, hosts = self._separar_hosts(df)

        self._registrar_conteo("listings", antes, len(df))
        self.tablas["amenities"] = amenities
        self.tablas["hosts"] = hosts
        return df.reset_index(drop=True)

    def _expandir_amenities(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Desanida ``amenities`` (texto JSON con una lista) en una tabla larga.

        En ``listings`` quedan solo el conteo y algunas banderas de amenidades
        clave; el detalle completo queda en la tabla ``amenities``
        (``listing_id``, ``amenity``).
        """
        errores = 0

        def leer_lista(valor) -> list[str]:
            nonlocal errores
            if not isinstance(valor, str) or not valor.strip():
                return []
            try:
                return [str(item).strip() for item in json.loads(valor) if str(item).strip()]
            except json.JSONDecodeError:
                errores += 1
                return []

        listas = df["amenities"].apply(leer_lista)
        if errores:
            logger.warning("amenities: %s registros con JSON inválido tratados como lista vacía", errores)

        df["cantidad_amenities"] = listas.str.len()
        en_minuscula = listas.apply(lambda items: " | ".join(items).lower())
        for columna, palabra in AMENIDADES_CLAVE.items():
            df[columna] = en_minuscula.str.contains(palabra, regex=False)

        amenities = (
            pd.DataFrame({"listing_id": df["id"], "amenity": listas})
            .explode("amenity")
            .dropna(subset=["amenity"])
            .drop_duplicates()
            .reset_index(drop=True)
        )
        logger.info("amenities: campo anidado expandido a %s filas (%s amenidades distintas)",
                    f"{len(amenities):,}", f"{amenities['amenity'].nunique():,}")
        return df.drop(columns=["amenities"]), amenities

    def _separar_hosts(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Separa la información del anfitrión en su propia tabla.

        Un anfitrión puede administrar muchas propiedades; dejar sus datos en
        ``listings`` los repite en cada fila. En ``listings`` solo queda
        ``host_id`` como llave hacia ``hosts``.
        """
        columnas_host = [c for c in df.columns
                         if c.startswith("host") or c.startswith("calculated_host")]
        hosts = (
            df[columnas_host]
            .drop_duplicates(subset=["host_id"], keep="first")
            .reset_index(drop=True)
        )
        logger.info("hosts: %s anfitriones únicos extraídos de %s propiedades",
                    f"{len(hosts):,}", f"{len(df):,}")
        columnas_a_quitar = [c for c in columnas_host if c != "host_id"]
        return df.drop(columns=columnas_a_quitar), hosts

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------
    def transformar_reviews(self, ids_listings: pd.Series) -> pd.DataFrame:
        """Limpia las reseñas y deriva variables de la fecha."""
        df = self._quitar_id_mongo(self.datos["reviews"])
        antes = len(df)
        df = self._eliminar_duplicados(df, ["id"], "reviews")
        df = self._descartar_huerfanos(df, ids_listings, "reviews")

        sin_comentario = int(df["comments"].isna().sum())
        df["comments"] = self._limpiar_texto(df["comments"]).fillna("Sin comentario")
        df["reviewer_name"] = self._limpiar_texto(df["reviewer_name"])
        df["longitud_comentario"] = df["comments"].str.len().astype("Int32")
        logger.info("reviews: %s comentarios vacíos marcados como 'Sin comentario'", f"{sin_comentario:,}")

        df = self._fecha_y_derivadas(df, "reviews")
        self._registrar_conteo("reviews", antes, len(df))
        return df.reset_index(drop=True)

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------
    def transformar_calendar(self, ids_listings: pd.Series) -> pd.DataFrame:
        """Limpia el calendario diario y genera su resumen mensual."""
        df = self._quitar_id_mongo(self.datos["calendar"])
        antes = len(df)
        df = self._eliminar_duplicados(df, ["listing_id", "date"], "calendar")
        df = self._descartar_huerfanos(df, ids_listings, "calendar")

        df["available"] = df["available"].map({"t": True, "f": False})
        for columna in ["minimum_nights", "maximum_nights"]:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")

        df = self._fecha_y_derivadas(df, "calendar")
        self.tablas["calendar_mensual"] = self._resumir_calendario(df)
        self._registrar_conteo("calendar", antes, len(df))
        return df.reset_index(drop=True)

    def _resumir_calendario(self, df: pd.DataFrame) -> pd.DataFrame:
        """Agrupa el calendario por propiedad y mes.

        El detalle diario (7 millones de filas) supera el límite de Excel
        (1.048.576 filas); este resumen sí se puede exportar y es el nivel
        al que se analiza la disponibilidad.
        """
        mensual = (
            df.groupby(["listing_id", "anio", "mes"], observed=True)
            .agg(
                dias_totales=("available", "size"),
                dias_disponibles=("available", "sum"),
                minimo_noches_promedio=("minimum_nights", "mean"),
            )
            .reset_index()
        )
        mensual["tasa_disponibilidad"] = (
            mensual["dias_disponibles"] / mensual["dias_totales"] * 100
        ).round(2)
        mensual["minimo_noches_promedio"] = mensual["minimo_noches_promedio"].round(1)
        logger.info("calendar_mensual: calendario resumido a %s filas (propiedad x mes)",
                    f"{len(mensual):,}")
        return mensual

    # ------------------------------------------------------------------
    # Pasos compartidos por reviews y calendar
    # ------------------------------------------------------------------
    @staticmethod
    def _descartar_huerfanos(df: pd.DataFrame, ids_listings: pd.Series, tabla: str) -> pd.DataFrame:
        """Elimina registros cuyo ``listing_id`` no existe en ``listings``."""
        huerfanos = ~df["listing_id"].isin(ids_listings)
        if huerfanos.any():
            logger.warning("%s: %s registros sin propiedad en listings eliminados",
                           tabla, f"{int(huerfanos.sum()):,}")
            return df[~huerfanos].copy()
        logger.info("%s: todos los registros tienen su propiedad en listings", tabla)
        return df

    def _fecha_y_derivadas(self, df: pd.DataFrame, tabla: str) -> pd.DataFrame:
        """Valida ``date``, descarta fechas inválidas, deriva sus partes y la deja en YYYY-MM-DD."""
        fechas = pd.to_datetime(df["date"], errors="coerce")
        invalidas = int(fechas.isna().sum())
        if invalidas:
            logger.warning("%s: %s registros con fecha inválida eliminados", tabla, f"{invalidas:,}")
            df = df[fechas.notna()]
            fechas = fechas[fechas.notna()]
        df = df.assign(date=fechas)
        df = self.derivar_fecha(df, "date")
        df["date"] = fechas.dt.strftime("%Y-%m-%d")
        logger.info("%s: fecha estandarizada a YYYY-MM-DD y derivadas anio, mes, dia, trimestre", tabla)
        return df

    # ------------------------------------------------------------------
    # Orquestación
    # ------------------------------------------------------------------
    def transformar_todo(self) -> dict[str, pd.DataFrame]:
        """Ejecuta todas las transformaciones y devuelve las tablas listas para la carga."""
        logger.info("Inicio de la transformación")
        self.tablas = {}
        try:
            listings = self.transformar_listings()
            self.tablas["listings"] = listings
            self.tablas["reviews"] = self.transformar_reviews(listings["id"])
            self.tablas["calendar"] = self.transformar_calendar(listings["id"])
        except Exception:
            logger.exception("Error durante la transformación")
            raise

        for nombre, tabla in self.tablas.items():
            logger.info("Tabla lista para carga: %s (%s filas x %s columnas)",
                        nombre, f"{len(tabla):,}", tabla.shape[1])
        logger.info("Transformación finalizada")
        return self.tablas
