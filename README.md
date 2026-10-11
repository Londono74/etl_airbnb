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
2026-10-10 18:41:32 | INFO    | etl_airbnb.pipeline      | === Inicio del proceso ETL Airbnb Bogotá ===
2026-10-10 18:41:32 | INFO    | etl_airbnb.extraccion    | Conexión establecida con MongoDB (mongodb://localhost:27017), base 'airbnb_bogota_etl'
2026-10-10 18:41:34 | INFO    | etl_airbnb.extraccion    | Extracción de 'Listings': 19.187 registros, 90 columnas
2026-10-10 18:41:36 | INFO    | etl_airbnb.extraccion    | Extracción de 'Reviews': 527.731 registros, 6 columnas
2026-10-10 18:41:49 | INFO    | etl_airbnb.extraccion    | Extracción de 'Calendar': 7.003.255 registros, 5 columnas
2026-10-10 18:41:49 | INFO    | etl_airbnb.transformacion| Listings: 13 columnas 100% vacías descartadas
2026-10-10 18:41:49 | WARNING | etl_airbnb.transformacion| Listings: 190 precios marcados como atípicos (> p99); se conservan
2026-10-10 18:41:49 | INFO    | etl_airbnb.transformacion| Listings: 0 registros con minimum_nights > 365 (regla sin efecto)
2026-10-10 18:41:51 | INFO    | etl_airbnb.carga         | Tabla 'listings' cargada: 19.187 registros (verificado)
2026-10-10 18:42:28 | INFO    | etl_airbnb.carga         | Exportación a 'airbnb_bogota.xlsx' finalizada
2026-10-10 18:42:28 | INFO    | etl_airbnb.pipeline      | === Proceso ETL finalizado con éxito ===
```

> Los conteos de `Reviews` y `Calendar` del ejemplo corresponden a una ejecución
> sobre el dataset completo. Los tiempos dependen del equipo.
