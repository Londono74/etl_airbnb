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

## Ejemplo de ejecución

_Se completa con la salida real de `python main.py` y un extracto del log._
