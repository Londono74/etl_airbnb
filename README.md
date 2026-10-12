# ETL Airbnb Bogotá

Proceso ETL (Extracción, Transformación y Carga) sobre los datasets de Inside Airbnb para Bogotá, Distrito Capital, Colombia. Los datos se almacenan en una base MongoDB local, se extraen con Python, se limpian y transforman con pandas y se cargan en SQLite y en archivos XLSX. Todo el proceso registra logs por ejecución.

Taller evaluativo 2 de Inteligencia de Negocios.

## Estructura

```
etl_airbnb/
├── src/
│   ├── config.py           # Conexión a MongoDB y rutas del proyecto
│   ├── logger.py           # Módulo centralizado de logs
│   ├── extraccion.py       # Clase Extraccion
│   ├── transformacion.py   # Clase Transformacion
│   └── carga.py            # Clase Carga
├── scripts/
│   └── cargar_mongodb.py   # Carga inicial de los CSV en MongoDB
├── notebooks/
│   └── exploracion_airbnb.ipynb
├── logs/                   # Un archivo log_YYYYMMDD_HHMM.txt por ejecución
├── main.py                 # Ejecuta Extracción → Transformación → Carga
├── README.md
└── requirements.txt
```

## Fuentes de datos

| Colección MongoDB | Archivo | Descripción |
|---|---|---|
| `Listings` | `listings.csv.gz` | Propiedades publicadas (19.187) |
| `Reviews` | `reviews.csv.gz` | Reseñas de huéspedes (527.731) |
| `Calendar` | `calendar.csv.gz` | Disponibilidad diaria por propiedad (7.003.255) |

Fuente: [Inside Airbnb](https://insideairbnb.com/get-the-data/), corte del 21 de junio de 2026.

## Instalación

Requisitos: Python 3.11 o superior y MongoDB Community Server corriendo en `localhost:27017`.

```powershell
# 1. Clonar el repositorio
git clone https://github.com/Londono74/etl_airbnb.git
cd etl_airbnb

# 2. Crear y activar el entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1        # Linux/macOS: source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. (Opcional) Configurar la conexión
copy .env.example .env            # Linux/macOS: cp .env.example .env
```

## Ejecución

```powershell
# 1. Cargar los datasets en MongoDB (descarga los archivos si no existen)
python scripts/cargar_mongodb.py

# 2. Ejecutar el proceso ETL completo
python main.py
```

Cada ejecución genera un archivo en `logs/` con el formato `log_YYYYMMDD_HHMM.txt`.

Al finalizar, el proceso deja en `output/`:

- `airbnb_bogota.db` — base SQLite con las tablas `listings`, `hosts`, `amenities`, `reviews`, `calendar` y `calendar_mensual`.
- `airbnb_bogota.xlsx` — el mismo contenido exportado, una hoja por tabla.

## Integrantes y responsabilidades

| Integrante | Responsabilidad |
|---|---|
| Luis David Lopera | Coordinación, descripción de datasets, extracción (`extraccion.py`), consolidación del informe. |
| Felipe | Análisis exploratorio de datos y gráficas (`notebooks/exploracion_airbnb.ipynb`, secciones 3 y 4 del informe). |
| Miguel Londoño | Transformación (`transformacion.py`), reglas de limpieza y derivación de variables. |
| Simón | Carga a SQLite y exportación XLSX (`carga.py`), generación del log de ejecución. |

## Ejemplo de ejecución

Salida real de una ejecución completa de `python main.py`:

```
2026-10-11 19:28:59 | INFO    | etl_airbnb.pipeline | === Inicio del proceso ETL Airbnb Bogotá ===
2026-10-11 19:28:59 | INFO    | etl_airbnb.extraccion | Conexión establecida con MongoDB; base: airbnb_bogota_etl
2026-10-11 19:29:01 | INFO    | etl_airbnb.extraccion | Extracción completada: colección Listings, 19,187 registros y 90 columnas en 2.07 segundos
2026-10-11 19:29:08 | INFO    | etl_airbnb.extraccion | Extracción completada: colección Reviews, 527,731 registros y 6 columnas en 6.60 segundos
2026-10-11 19:30:26 | INFO    | etl_airbnb.extraccion | Extracción completada: colección Calendar, 7,003,255 registros y 5 columnas en 78.30 segundos
2026-10-11 19:30:26 | INFO    | etl_airbnb.transformacion | Inicio de la transformación
2026-10-11 19:30:27 | WARNING | etl_airbnb.transformacion | listings: 13 columnas con >= 95% nulos eliminadas: [...]
2026-10-11 19:30:28 | INFO    | etl_airbnb.transformacion | listings: price normalizado a numérico (mediana 161,460 COP, máximo 448,176,567 COP)
2026-10-11 19:30:28 | WARNING | etl_airbnb.transformacion | listings: 190 precios atípicos (> p99 = 1,330,087 COP) marcados en precio_atipico; se conservan
2026-10-11 19:30:28 | INFO    | etl_airbnb.transformacion | listings: minimum_nights dentro del rango [1, 365] (regla sin efecto)
2026-10-11 19:31:02 | INFO    | etl_airbnb.transformacion | calendar: fechas de 2026-06-21 a 2027-06-21 estandarizadas a YYYY-MM-DD; derivadas anio, mes, dia, trimestre, dia_semana y es_fin_de_semana
2026-10-11 19:31:04 | INFO    | etl_airbnb.transformacion | Transformación finalizada
2026-10-11 19:31:06 | INFO    | etl_airbnb.carga | Tabla 'listings' cargada: 19,187 registros (verificado)
2026-10-11 19:31:43 | INFO    | etl_airbnb.carga | Tabla 'calendar' cargada: 7,003,255 registros (verificado)
2026-10-11 19:43:08 | INFO    | etl_airbnb.carga | Exportación a 'airbnb_bogota.xlsx' finalizada
2026-10-11 19:43:08 | INFO    | etl_airbnb.pipeline | === Proceso ETL finalizado con éxito en 849.6 segundos ===
```

> Extracto de `logs/log_20261011_1928.txt`; el archivo completo registra cada paso
> de las tres fases. Los tiempos dependen del equipo.
