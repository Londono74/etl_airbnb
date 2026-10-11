"""Fase de transformación del proceso ETL de Airbnb Bogotá.

Qué recibe y qué entrega
========================
Recibe el diccionario que devuelve ``Extraccion().extraer_todo()`` con tres
DataFrames crudos (``listings``, ``reviews`` y ``calendar``) y entrega a la
clase ``Carga`` seis tablas limpias:

- ``listings``: una fila por alojamiento, con precio numérico, categoría de
  precio, banderas de amenidades y fechas estandarizadas.
- ``hosts``: una fila por anfitrión (la información del host desanidada).
- ``amenities``: una fila por alojamiento y amenidad (la lista anidada
  expandida).
- ``reviews``: una fila por reseña, con texto limpio y variables de fecha.
- ``calendar``: una fila por alojamiento y día, con año, mes, día y trimestre.
- ``calendar_mensual``: la disponibilidad resumida por alojamiento y mes.

Uso::

    datos = Extraccion().extraer_todo()
    tablas = Transformacion(datos).transformar_todo()

Criterios generales y por qué se eligieron
==========================================
1. **Precios como número.** Inside Airbnb publica el precio como texto en
   formato estadounidense: ``"$284,294.01"``. Ahí la coma separa los miles y
   el punto separa los decimales. Mientras sea texto no se puede promediar,
   comparar ni graficar, así que se quitan el símbolo ``$`` y los separadores
   de miles y se convierte a número (``284294.01``). Los separadores de miles
   solo ayudan a leer la cifra; para el computador sobran. Es lo mismo que
   pasa con una cifra escrita a la colombiana como ``5.300.823``: esos puntos
   no son decimales, solo agrupan de a tres dígitos, y el valor real es
   ``5300823``. El punto del dataset *no* se elimina, porque en el formato de
   origen sí es el decimal: si se quitara, ``284,294.01`` se convertiría en
   ``28429401``, un precio cien veces mayor.

2. **Fechas en formato ``YYYY-MM-DD`` (ISO 8601).** Es el estándar
   internacional y no es ambiguo: ``03/04/2026`` puede ser 3 de abril o 4 de
   marzo según el país, mientras que ``2026-04-03`` solo tiene una lectura.
   Además, al ordenar este texto alfabéticamente queda ordenado
   cronológicamente, SQLite lo reconoce en sus funciones de fecha
   (``date()``, ``strftime()``) y Excel lo interpreta sin configuración
   regional. Los valores que no son fechas válidas quedan nulos, en vez de
   detener el proceso.

3. **Partes de la fecha como columnas.** De ``date`` se derivan ``anio``,
   ``mes``, ``dia`` y ``trimestre`` (más ``dia_semana`` y
   ``es_fin_de_semana``). Así se puede agrupar por mes o trimestre con un
   ``GROUP BY`` simple, sin recalcular la fecha en cada consulta.

4. **Nulos: no se inventan datos.** Cada columna se trata según lo que
   significa su vacío:

   - Las columnas casi vacías (95 % o más de nulos) se eliminan, porque
     cualquier relleno sería inventado.
   - Los textos opcionales se rellenan con un valor explícito
     (``""``, ``"Sin información"``, ``"Sin comentario"``).
   - Las cantidades físicas (habitaciones, camas, baños) se imputan con la
     mediana de su mismo tipo de habitación.
   - Los puntajes de reseñas se dejan nulos, porque un alojamiento sin
     reseñas no tiene calificación.

5. **Duplicados y huérfanos.** Se eliminan las filas repetidas por su llave
   natural, y las reseñas o días de calendario cuyo alojamiento no existe en
   ``listings``. Así se protege la integridad referencial que se espera en
   SQLite.

6. **Los atípicos se marcan, no se borran.** Un precio extremo puede ser un
   error de digitación o una propiedad de lujo real. Borrarlo también
   eliminaría el alojamiento de análisis que no dependen del precio
   (ubicación, reseñas, disponibilidad). Por eso se marca con una bandera y
   cada análisis decide si lo excluye.

7. **Separar lo anidado (normalización).** ``amenities`` llega como una lista
   JSON dentro de una celda, y los datos del anfitrión se repiten en cada uno
   de sus alojamientos. Ambos se separan en tablas propias unidas por llaves
   (``listing_id`` y ``host_id``). Así una celda guarda un solo valor y no se
   repite información.

8. **Tipos consistentes.** Al final, los textos quedan como ``string``, los
   booleanos como ``boolean`` y los enteros pequeños como ``Int8``/``Int16``
   (tipos de pandas que admiten nulos). Así un nulo no se convierte en el
   texto ``"nan"`` al cargar, y el calendario de 7 millones de filas no
   multiplica el uso de memoria.

9. **Logs.** Cada paso escribe en el log del proceso
   (``logs/log_YYYYMMDD_HHMM.txt``) qué hizo y cuántos registros afectó, con
   este criterio:

   - ``INFO`` para los pasos normales y los conteos antes y después de cada
     limpieza.
   - ``WARNING`` para los datos anómalos que se corrigieron o marcaron.
   - ``ERROR``, con el detalle de la excepción, si la fase no puede terminar.

   En los mensajes, las cantidades se escriben con separador de miles
   (``7,003,255``) solo para que se lean fácilmente. Los datos que se cargan
   no llevan separadores.
"""

import html
import json

import numpy as np
import pandas as pd

from src.logger import obtener_logger

logger = obtener_logger("transformacion")

FUENTES_REQUERIDAS = ("listings", "reviews", "calendar")

# Una columna con 95 % o más de nulos no permite ningún análisis confiable.
# En este corte de Inside Airbnb hay 13 columnas 100 % vacías
# (host_since, host_response_rate, neighbourhood, instant_bookable, ...).
UMBRAL_NULOS = 0.95

# URLs, imágenes y metadatos del scraping: identifican la página web, no el
# alojamiento. price_quote_raw es el JSON crudo de la cotización; sus valores
# útiles ya vienen separados en price_quote_total_price y
# price_quote_price_per_night.
COLUMNAS_NO_ANALITICAS = [
    "listing_url", "scrape_id", "source", "picture_url", "host_url",
    "host_profile_id", "host_profile_url", "host_thumbnail_url",
    "host_picture_url", "price_quote_raw",
]

COLUMNAS_TEXTO_LISTINGS = [
    "name", "description", "host_name", "host_location", "host_about",
    "neighbourhood_cleansed", "property_type", "room_type", "bathrooms_text",
]

COLUMNAS_FECHA_LISTINGS = [
    "last_scraped", "host_since", "first_review", "last_review",
    "calendar_last_scraped", "price_quote_checkin_date", "price_quote_checkout_date",
]

# Los precios de Bogotá tienen una cola derecha muy larga (mediana ≈ 160.000
# COP y máximo ≈ 448 millones). Con la regla IQR, el 7 % de los alojamientos
# quedaba como atípico, casi todos propiedades de lujo reales. El percentil 99
# (≈ 1,33 millones COP, el mismo umbral que se usó en el EDA) aísla solo los
# valores extremos, que son los candidatos a error de digitación.
PERCENTIL_ATIPICO = 0.99

# Las categorías se definen por cuartiles del precio: cada una agrupa el 25 %
# de los alojamientos. Los cortes se calculan con los datos de cada ejecución,
# así que se ajustan solos si cambia el corte de Inside Airbnb. Los valores de
# cada corte quedan en el log.
CATEGORIAS_PRECIO = ["Económico", "Moderado", "Alto", "Lujo"]

# Más de un año de estadía mínima no es una oferta real de alojamiento.
MAX_NOCHES = 365

# Amenidades que un huésped suele filtrar en Bogotá. Se vuelven columnas
# booleanas para filtrar y agrupar sin recorrer la lista completa.
AMENIDADES_CLAVE = {
    "tiene_wifi": "wifi",
    "tiene_cocina": "kitchen",
    "tiene_parqueadero": "parking",
    "tiene_lavadora": "washer",
    "tiene_espacio_trabajo": "dedicated workspace",
    "permite_estadias_largas": "long term stays allowed",
}


class Transformacion:
    """Limpia, estandariza y enriquece los datos extraídos de MongoDB.

    Args:
        datos: diccionario con los DataFrames crudos ``listings``,
            ``reviews`` y ``calendar``.

    Raises:
        ValueError: si falta alguna de las tres fuentes. Se valida antes de
            empezar para no producir tablas incompletas.
    """

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
        """Elimina el ``_id`` interno de MongoDB si llegara a venir.

        Es un identificador técnico de la base de datos, no un dato del
        negocio; la llave del dataset es ``id`` / ``listing_id``.
        """
        return df.drop(columns=["_id"], errors="ignore")

    @staticmethod
    def _registrar_conteo(tabla: str, antes: int, despues: int) -> None:
        """Deja en el log cuántos registros había antes y después de limpiar."""
        eliminados = antes - despues
        logger.info("%s: %s registros antes, %s después (%s eliminados)",
                    tabla, f"{antes:,}", f"{despues:,}", f"{eliminados:,}")

    @staticmethod
    def _eliminar_duplicados(df: pd.DataFrame, llave: list[str], tabla: str) -> pd.DataFrame:
        """Elimina filas repetidas por su llave natural y lo registra.

        Se usa la llave natural (``id`` o ``listing_id`` + ``date``) en lugar
        de comparar la fila completa: dos versiones de un mismo alojamiento
        con algún campo distinto siguen siendo un duplicado. Se conserva la
        primera aparición.
        """
        duplicados = int(df.duplicated(subset=llave).sum())
        if duplicados:
            logger.warning("%s: %s duplicados por %s eliminados", tabla, f"{duplicados:,}", llave)
        else:
            logger.info("%s: sin duplicados por %s", tabla, llave)
        return df.drop_duplicates(subset=llave, keep="first")

    @staticmethod
    def _limpiar_texto(serie: pd.Series) -> pd.Series:
        """Deja el texto libre listo para analizar y exportar.

        - Las descripciones traen HTML (``<br />``, ``<b>``), que es formato
          de la página web y no contenido; se reemplaza por un espacio.
        - Las entidades HTML (``&amp;``, ``&quot;``) vuelven a su carácter
          real (``&``, ``"``).
        - Los caracteres de control invisibles (``\\x00``-``\\x1f``) se
          eliminan: no aportan nada y Excel rechaza las celdas que los
          contienen.
        - Los espacios repetidos y los de los extremos se quitan, para que
          ``"Chapinero "`` y ``"Chapinero"`` cuenten como el mismo valor al
          agrupar.
        """
        return (
            serie.astype("string")
            .str.replace(r"<[^>]+>", " ", regex=True)
            .map(html.unescape, na_action="ignore")
            .astype("string")
            .str.replace(r"[\x00-\x1f\x7f]", " ", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )

    @staticmethod
    def _a_fecha_estandar(serie: pd.Series) -> pd.Series:
        """Convierte una columna de fechas a texto ``YYYY-MM-DD`` (ISO 8601).

        ``errors="coerce"`` deja como nulo lo que no sea una fecha válida, en
        vez de detener todo el proceso por un valor mal escrito.
        """
        return pd.to_datetime(serie, errors="coerce").dt.strftime("%Y-%m-%d").astype("string")

    @staticmethod
    def normalizar_precio(serie: pd.Series) -> pd.Series:
        """Convierte un precio en texto a número: ``"$284,294.01"`` → ``284294.01``.

        Se quitan:

        - ``$``: es el símbolo de la moneda, no parte del valor.
        - ``,``: en el formato de origen (estadounidense) separa los miles.
          Igual que los puntos de ``5.300.823`` en notación colombiana, solo
          facilitan la lectura y le sobran al número.
        - Los espacios.

        El punto se conserva porque en este formato es el separador decimal.

        ``errors="coerce"`` deja como nulo un precio que no se pueda
        interpretar, en lugar de inventarle un valor o romper la ejecución.
        """
        texto = serie.astype("string").str.replace(r"[$,\s]", "", regex=True)
        return pd.to_numeric(texto, errors="coerce")

    @staticmethod
    def categorizar_precio(precio: pd.Series) -> tuple[pd.Series, list[float]]:
        """Asigna a cada precio su cuartil: Económico, Moderado, Alto o Lujo.

        Devuelve la categoría y los cortes calculados, para registrarlos en
        el log. Los alojamientos sin precio quedan en ``"Sin precio"`` para no
        mezclarlos con ninguna categoría real.
        """
        categoria, cortes = pd.qcut(precio, q=4, labels=CATEGORIAS_PRECIO, retbins=True)
        return categoria.astype("string").fillna("Sin precio"), cortes.tolist()

    @staticmethod
    def derivar_fecha(df: pd.DataFrame, columna: str = "date") -> pd.DataFrame:
        """Agrega año, mes, día, trimestre y día de la semana a partir de ``columna``.

        Se guardan como enteros pequeños (``Int16``/``Int8``) porque el
        calendario tiene 7 millones de filas; con ``int64`` cada columna
        ocuparía 8 veces más memoria.
        """
        fechas = pd.to_datetime(df[columna], errors="coerce")
        df["anio"] = fechas.dt.year.astype("Int16")
        df["mes"] = fechas.dt.month.astype("Int8")
        df["dia"] = fechas.dt.day.astype("Int8")
        df["trimestre"] = fechas.dt.quarter.astype("Int8")
        df["dia_semana"] = fechas.dt.dayofweek.astype("Int8")  # 0 = lunes, 6 = domingo
        df["es_fin_de_semana"] = (fechas.dt.dayofweek >= 5).astype("boolean")
        return df

    @staticmethod
    def _tipar_texto(df: pd.DataFrame) -> pd.DataFrame:
        """Convierte las columnas ``object`` restantes al tipo ``string`` de pandas.

        Con ``object``, un nulo puede terminar escrito como el texto
        ``"None"`` o ``"nan"`` al exportar. Con ``string`` sigue siendo un
        nulo real en SQLite y una celda vacía en Excel.
        """
        for columna in df.columns[df.dtypes == object]:
            df[columna] = df[columna].astype("string")
        return df

    # ------------------------------------------------------------------
    # Listings, hosts y amenities
    # ------------------------------------------------------------------
    def transformar_listings(self) -> pd.DataFrame:
        """Limpia los alojamientos y genera también las tablas ``hosts`` y ``amenities``."""
        df = self._quitar_id_mongo(self.datos["listings"])
        antes = len(df)
        logger.info("listings: %s registros y %s columnas recibidos", f"{antes:,}", df.shape[1])
        df = self._eliminar_duplicados(df, ["id"], "listings")

        # 1. Columnas sin información (ver UMBRAL_NULOS y COLUMNAS_NO_ANALITICAS).
        porcentaje_nulos = df.isna().mean()
        vacias = porcentaje_nulos[porcentaje_nulos >= UMBRAL_NULOS].index.tolist()
        if vacias:
            logger.warning("listings: %s columnas con >= %.0f%% nulos eliminadas: %s",
                           len(vacias), UMBRAL_NULOS * 100, vacias)
        no_analiticas = [c for c in COLUMNAS_NO_ANALITICAS if c in df and c not in vacias]
        df = df.drop(columns=vacias + no_analiticas)
        logger.info("listings: %s columnas técnicas (URLs, imágenes, scraping) eliminadas",
                    len(no_analiticas))

        # 2. Texto libre: HTML, entidades y espacios sobrantes.
        for columna in COLUMNAS_TEXTO_LISTINGS:
            if columna in df:
                df[columna] = self._limpiar_texto(df[columna])
        # Una descripción vacía significa "el anfitrión no escribió nada"; un
        # texto vacío lo expresa sin introducir nulos en los análisis de texto.
        df["description"] = df["description"].fillna("")
        if "host_location" in df:
            df["host_location"] = df["host_location"].fillna("Sin información")
        logger.info("listings: texto limpio (HTML, entidades y espacios) en %s columnas",
                    len([c for c in COLUMNAS_TEXTO_LISTINGS if c in df]))

        # 3. Booleanos: Airbnb codifica sí/no como "t"/"f". Con True/False se
        #    puede sumar y filtrar directamente (p. ej. contar superhosts).
        #    Las columnas se detectan por su contenido para no depender de
        #    una lista que cambie entre cortes del dataset.
        convertidas = []
        for columna in df.columns[df.dtypes == object]:
            valores = set(df[columna].dropna().unique())
            if valores and valores <= {"t", "f"}:
                df[columna] = df[columna].map({"t": True, "f": False}).astype("boolean")
                convertidas.append(columna)
        logger.info("listings: %s columnas t/f convertidas a booleanas: %s",
                    len(convertidas), convertidas)

        # 4. Precio: de texto a número (ver normalizar_precio).
        df["price"] = self.normalizar_precio(df["price"])
        sin_precio = int(df["price"].isna().sum())
        if sin_precio:
            logger.warning("listings: %s alojamientos sin precio publicado; se conservan "
                           "con categoría 'Sin precio'", f"{sin_precio:,}")
        no_positivos = df["price"] <= 0
        if no_positivos.any():
            # Un precio de 0 o negativo no es una tarifa real; se trata como desconocido.
            df.loc[no_positivos, "price"] = np.nan
            logger.warning("listings: %s precios <= 0 convertidos a nulo",
                           f"{int(no_positivos.sum()):,}")
        logger.info("listings: price normalizado a numérico (mediana %s COP, máximo %s COP)",
                    f"{df['price'].median():,.0f}", f"{df['price'].max():,.0f}")

        # 5. Atípicos de precio: se marcan, no se eliminan (ver PERCENTIL_ATIPICO).
        limite = df["price"].quantile(PERCENTIL_ATIPICO)
        df["precio_atipico"] = (df["price"] > limite).astype("boolean")
        logger.warning("listings: %s precios atípicos (> p99 = %s COP) marcados en "
                       "precio_atipico; se conservan", f"{int(df['precio_atipico'].sum()):,}",
                       f"{limite:,.0f}")

        # 6. Categoría de precio por cuartiles (ver CATEGORIAS_PRECIO).
        df["categoria_precio"], cortes = self.categorizar_precio(df["price"])
        logger.info("listings: categoria_precio por cuartiles, cortes en COP %s; distribución %s",
                    [f"{c:,.0f}" for c in cortes], df["categoria_precio"].value_counts().to_dict())

        # 7. Rangos válidos: una estadía mínima de más de un año o una
        #    disponibilidad fuera de 0-365 días no son posibles. Se anulan en
        #    lugar de borrar el alojamiento.
        for columna, minimo, maximo in [("minimum_nights", 1, MAX_NOCHES),
                                        ("availability_365", 0, 365)]:
            fuera = ~df[columna].between(minimo, maximo) & df[columna].notna()
            if fuera.any():
                df.loc[fuera, columna] = np.nan
                logger.warning("listings: %s valores de %s fuera de [%s, %s] convertidos a nulo",
                               f"{int(fuera.sum()):,}", columna, minimo, maximo)
            else:
                logger.info("listings: %s dentro del rango [%s, %s] (regla sin efecto)",
                            columna, minimo, maximo)

        # 8. Fechas a YYYY-MM-DD (ver criterio 2 del módulo).
        for columna in COLUMNAS_FECHA_LISTINGS:
            if columna in df:
                df[columna] = self._a_fecha_estandar(df[columna])
        logger.info("listings: fechas convertidas a formato YYYY-MM-DD")

        # 9. Baños: cuando "bathrooms" es nulo, el número suele estar en
        #    "bathrooms_text" ("1.5 shared baths" -> 1.5, "Half-bath" -> 0.5).
        #    Se aprovecha antes de imputar, porque es un dato real del anfitrión.
        texto_banos = df["bathrooms_text"].str.lower()
        banos_texto = pd.to_numeric(texto_banos.str.extract(r"([\d.]+)")[0], errors="coerce")
        banos_texto = banos_texto.mask(texto_banos.str.contains("half", na=False) & banos_texto.isna(), 0.5)
        completados = int((df["bathrooms"].isna() & banos_texto.notna()).sum())
        df["bathrooms"] = df["bathrooms"].fillna(banos_texto)
        df["bano_compartido"] = texto_banos.str.contains("shared", na=False).astype("boolean")
        logger.info("listings: %s valores de bathrooms completados desde bathrooms_text",
                    f"{completados:,}")

        # 10. Habitaciones, camas y baños restantes: mediana del mismo
        #     room_type. Un apartamento entero y un cuarto compartido tienen
        #     tamaños muy distintos, así que la mediana global distorsionaría
        #     ambos. Se usa la mediana y no el promedio porque no la mueven
        #     los valores extremos.
        for columna in ["bedrooms", "beds", "bathrooms"]:
            nulos = int(df[columna].isna().sum())
            mediana = df.groupby("room_type")[columna].transform("median")
            df[columna] = df[columna].fillna(mediana).fillna(df[columna].median())
            logger.info("listings: %s nulos de %s imputados con la mediana por room_type",
                        f"{nulos:,}", columna)

        # 11. Reseñas: si un alojamiento no tiene reseñas, su frecuencia
        #     mensual es 0 (el nulo era un "no aplica"). Los puntajes
        #     review_scores_* se dejan nulos, porque imputar una calificación
        #     inventaría una opinión que nadie dio.
        sin_resenas = df["number_of_reviews"] == 0
        df.loc[sin_resenas, "reviews_per_month"] = 0
        logger.info("listings: %s alojamientos sin reseñas; reviews_per_month = 0 y "
                    "puntajes conservados como nulos", f"{int(sin_resenas.sum()):,}")

        if "license" in df:
            df["tiene_licencia"] = df["license"].notna().astype("boolean")
            logger.info("listings: %s alojamientos reportan licencia (registro nacional de turismo)",
                        f"{int(df['tiene_licencia'].sum()):,}")

        # 12. Campos anidados: amenities (lista JSON) y datos del anfitrión.
        df, amenities = self._expandir_amenities(df)
        df, hosts = self._separar_hosts(df)

        self._registrar_conteo("listings", antes, len(df))
        self.tablas["amenities"] = amenities
        self.tablas["hosts"] = self._tipar_texto(hosts)
        return self._tipar_texto(df).reset_index(drop=True)

    def _expandir_amenities(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Expande ``amenities``, un texto JSON con una lista, en una tabla larga.

        En el origen, cada celda guarda algo como
        ``'["Wifi", "Kitchen", "Hair dryer"]'``. Así no se puede contar cuántos
        alojamientos tienen wifi ni cruzar amenidades con el precio. Se
        generan:

        - En ``listings``: ``cantidad_amenities`` y una bandera booleana por
          cada amenidad clave (ver ``AMENIDADES_CLAVE``).
        - La tabla ``amenities`` (``listing_id``, ``amenity``): una fila por
          cada amenidad de cada alojamiento, con el detalle completo.

        Se usa ``json.loads`` porque el campo es JSON válido. Un registro
        malformado se trata como una lista vacía y se avisa en el log, en vez
        de detener la fase.
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

        df["cantidad_amenities"] = listas.str.len().astype("Int16")
        # Se busca en minúsculas y por subcadena: "Wifi", "Fast wifi – 300 Mbps"
        # y "Free parking on premises" deben contar como wifi y parqueadero.
        en_minuscula = listas.apply(lambda items: " | ".join(items).lower())
        for columna, palabra in AMENIDADES_CLAVE.items():
            df[columna] = en_minuscula.str.contains(palabra, regex=False).astype("boolean")

        amenities = (
            pd.DataFrame({"listing_id": df["id"], "amenity": listas})
            .explode("amenity")
            .dropna(subset=["amenity"])
            .drop_duplicates()
            .reset_index(drop=True)
        )
        amenities["amenity"] = self._limpiar_texto(amenities["amenity"])
        logger.info("amenities: campo anidado expandido de %s alojamientos a %s filas "
                    "(%s amenidades distintas)", f"{len(df):,}", f"{len(amenities):,}",
                    f"{amenities['amenity'].nunique():,}")
        return df.drop(columns=["amenities"]), amenities

    def _separar_hosts(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Separa la información del anfitrión en la tabla ``hosts``.

        Un anfitrión puede administrar decenas de alojamientos. Si sus datos
        (nombre, si es superhost, cuántos alojamientos tiene...) se quedan en
        ``listings``, se repiten en cada fila, y si uno cambia hay que
        corregirlo en todas. En ``listings`` solo queda ``host_id`` como llave
        hacia ``hosts``.
        """
        columnas_host = [c for c in df.columns
                         if c.startswith("host") or c.startswith("calculated_host")]
        hosts = (
            df[columnas_host]
            .drop_duplicates(subset=["host_id"], keep="first")
            .reset_index(drop=True)
        )
        logger.info("hosts: %s anfitriones únicos extraídos de %s alojamientos (%s columnas)",
                    f"{len(hosts):,}", f"{len(df):,}", hosts.shape[1])
        columnas_a_quitar = [c for c in columnas_host if c != "host_id"]
        return df.drop(columns=columnas_a_quitar), hosts

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------
    def transformar_reviews(self, ids_listings: pd.Series) -> pd.DataFrame:
        """Limpia las reseñas y deriva variables de su fecha."""
        df = self._quitar_id_mongo(self.datos["reviews"])
        antes = len(df)
        logger.info("reviews: %s registros recibidos", f"{antes:,}")
        df = self._eliminar_duplicados(df, ["id"], "reviews")
        df = self._descartar_huerfanos(df, ids_listings, "reviews")

        # Una reseña sin texto sigue siendo una estadía real: se conserva y se
        # marca de forma explícita, en lugar de dejar un nulo ambiguo.
        sin_comentario = int(df["comments"].isna().sum())
        df["comments"] = self._limpiar_texto(df["comments"]).fillna("Sin comentario")
        df["reviewer_name"] = self._limpiar_texto(df["reviewer_name"])
        logger.info("reviews: %s comentarios vacíos marcados como 'Sin comentario'",
                    f"{sin_comentario:,}")

        # La longitud del comentario sirve como medida simple de qué tan
        # detallada es la opinión del huésped.
        df["longitud_comentario"] = df["comments"].str.len().astype("Int32")

        df = self._fecha_y_derivadas(df, "reviews")
        self._registrar_conteo("reviews", antes, len(df))
        return self._tipar_texto(df).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------
    def transformar_calendar(self, ids_listings: pd.Series) -> pd.DataFrame:
        """Limpia el calendario diario y genera su resumen mensual."""
        df = self._quitar_id_mongo(self.datos["calendar"])
        antes = len(df)
        logger.info("calendar: %s registros recibidos", f"{antes:,}")
        # Un alojamiento solo puede tener un estado por día.
        df = self._eliminar_duplicados(df, ["listing_id", "date"], "calendar")
        df = self._descartar_huerfanos(df, ids_listings, "calendar")

        df["available"] = df["available"].map({"t": True, "f": False}).astype("boolean")
        logger.info("calendar: available convertido de t/f a booleano")
        for columna in ["minimum_nights", "maximum_nights"]:
            df[columna] = pd.to_numeric(df[columna], errors="coerce").astype("Int32")

        fuera = (df["minimum_nights"] > MAX_NOCHES).fillna(False)
        if fuera.any():
            df.loc[fuera, "minimum_nights"] = pd.NA
            logger.warning("calendar: %s valores de minimum_nights > %s convertidos a nulo",
                           f"{int(fuera.sum()):,}", MAX_NOCHES)
        else:
            logger.info("calendar: minimum_nights <= %s en todos los días (regla sin efecto)",
                        MAX_NOCHES)

        df = self._fecha_y_derivadas(df, "calendar")
        self.tablas["calendar_mensual"] = self._resumir_calendario(df)
        self._registrar_conteo("calendar", antes, len(df))
        return self._tipar_texto(df).reset_index(drop=True)

    def _resumir_calendario(self, df: pd.DataFrame) -> pd.DataFrame:
        """Agrupa el calendario por alojamiento y mes.

        El detalle diario (unos 7 millones de filas) supera el límite de
        Excel (1.048.576 filas por hoja). Además, la ocupación se analiza por
        mes y no por día. ``tasa_disponibilidad`` es el porcentaje de días del
        mes en que el alojamiento estaba libre; 100 menos ese valor
        aproxima la ocupación.
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
        mensual["minimo_noches_promedio"] = mensual["minimo_noches_promedio"].astype(float).round(1)
        logger.info("calendar_mensual: calendario resumido de %s días a %s filas "
                    "(alojamiento x mes)", f"{len(df):,}", f"{len(mensual):,}")
        return mensual

    # ------------------------------------------------------------------
    # Pasos compartidos por reviews y calendar
    # ------------------------------------------------------------------
    @staticmethod
    def _descartar_huerfanos(df: pd.DataFrame, ids_listings: pd.Series, tabla: str) -> pd.DataFrame:
        """Elimina los registros cuyo ``listing_id`` no existe en ``listings``.

        Una reseña o un día de calendario de un alojamiento desconocido no se
        puede relacionar con precio, barrio ni anfitrión. Además, rompería la
        relación entre tablas en la base de datos destino.
        """
        huerfanos = ~df["listing_id"].isin(ids_listings)
        if huerfanos.any():
            logger.warning("%s: %s registros sin alojamiento en listings eliminados",
                           tabla, f"{int(huerfanos.sum()):,}")
            return df[~huerfanos].copy()
        logger.info("%s: todos los registros tienen su alojamiento en listings", tabla)
        return df

    def _fecha_y_derivadas(self, df: pd.DataFrame, tabla: str) -> pd.DataFrame:
        """Valida ``date``, deriva sus partes y la deja en formato YYYY-MM-DD.

        A diferencia de ``listings``, aquí la fecha es la esencia del
        registro (cuándo se escribió la reseña o a qué día corresponde la
        disponibilidad). Por eso un registro con fecha inválida se elimina en
        lugar de conservarse con un nulo.
        """
        fechas = pd.to_datetime(df["date"], errors="coerce")
        invalidas = int(fechas.isna().sum())
        if invalidas:
            logger.warning("%s: %s registros con fecha inválida eliminados", tabla, f"{invalidas:,}")
            df = df[fechas.notna()]
            fechas = fechas[fechas.notna()]
        df = df.assign(date=fechas)
        df = self.derivar_fecha(df, "date")
        df["date"] = fechas.dt.strftime("%Y-%m-%d").astype("string")
        logger.info("%s: fechas de %s a %s estandarizadas a YYYY-MM-DD; derivadas anio, mes, "
                    "dia, trimestre, dia_semana y es_fin_de_semana",
                    tabla, f"{fechas.min():%Y-%m-%d}", f"{fechas.max():%Y-%m-%d}")
        return df

    # ------------------------------------------------------------------
    # Orquestación
    # ------------------------------------------------------------------
    def transformar_todo(self) -> dict[str, pd.DataFrame]:
        """Ejecuta todas las transformaciones y devuelve las tablas para la carga.

        ``listings`` va primero porque sus ``id`` limpios son la referencia
        para descartar huérfanos en ``reviews`` y ``calendar``. Si cualquier
        paso falla, se registra el error completo y se vuelve a lanzar: el
        proceso no debe cargar tablas a medio transformar.
        """
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
