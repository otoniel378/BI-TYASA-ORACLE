
"""
create_market_tables.py — Crea las tablas de mercado en BigQuery y carga datos históricos.
Ejecutar UNA SOLA VEZ para inicializar. Requiere: pip install yfinance pandas google-cloud-bigquery
"""

import pandas as pd
import numpy as np
from google.cloud import bigquery
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

PROJECT_ID = "project-d0cf2519-d089-47d3-930"
DATASET    = "tyasa_bi"
CLIENT     = bigquery.Client(project=PROJECT_ID)

TICKERS = {
    'BZ=F'    : ('Brent_USD',          'Energía'),
    'CL=F'    : ('WTI_USD',            'Energía'),
    'NG=F'    : ('Gas_HenryHub_USD',   'Energía'),
    'TTF=F'   : ('Gas_TTF_Europa',     'Energía'),
    'TIO=F'   : ('Mineral_Hierro',     'Insumos_Acero'),
    'HG=F'    : ('Cobre_USD',          'Insumos_Acero'),
    'ALI=F'   : ('Aluminio_USD',       'Insumos_Acero'),
    'SLX'     : ('ETF_Acero_Global',   'Sector_Acero'),
    'TX'      : ('Ternium_MX',         'Sector_Acero'),
    'MT'      : ('ArcelorMittal',      'Sector_Acero'),
    'NUE'     : ('Nucor_EAF',          'Sector_Acero'),
    'STLD'    : ('SteelDynamics_EAF',  'Sector_Acero'),
    'BDRY'    : ('ETF_Flete_Seco',     'Logistica'),
    'ZIM'     : ('ZIM_Contenedor',     'Logistica'),
    'MATX'    : ('Matson_Pacifico',    'Logistica'),
    'SBLK'    : ('StarBulk',           'Logistica'),
    '^VIX'    : ('VIX',               'Riesgo_Mercados'),
    '^GSPC'   : ('SP500',             'Riesgo_Mercados'),
    'GC=F'    : ('Oro_USD',           'Riesgo_Mercados'),
    'DX-Y.NYB': ('Dolar_Index',       'Riesgo_Mercados'),
    'TLT'     : ('Bonos_20y',         'Riesgo_Mercados'),
    '^N225'   : ('Nikkei_Japon',      'Asia'),
    '^KS11'   : ('KOSPI_Corea',       'Asia'),
    'FXI'     : ('ETF_China',         'Asia'),
    'EWJ'     : ('ETF_Japon',         'Asia'),
    'EWY'     : ('ETF_Corea',         'Asia'),
    'EWG'     : ('ETF_Alemania',      'Europa'),
    'EEM'     : ('ETF_Emergentes',    'Europa'),
    'EWW'     : ('ETF_Mexico',        'Mexico'),
    'MXN=X'   : ('USD_MXN',          'Mexico'),
}

SCHEMA_VARIABLES = [
    bigquery.SchemaField("fecha",      "DATE",    mode="REQUIRED"),
    bigquery.SchemaField("ticker",     "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("nombre",     "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("categoria",  "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("valor",      "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("cargado_en", "TIMESTAMP", mode="REQUIRED"),
]

SCHEMA_QUIEBRES = [
    bigquery.SchemaField("id",           "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("variable",     "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("categoria",    "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("fecha_corte",  "DATE",    mode="REQUIRED"),
    bigquery.SchemaField("fecha_detect", "DATE",    mode="REQUIRED"),
    bigquery.SchemaField("F_stat",       "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("p_value",      "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("sigma",        "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("cambio_pct",   "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("media_pre",    "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("media_post",   "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("severidad",    "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("activo",       "BOOL",    mode="REQUIRED"),
]

SCHEMA_NOTICIAS = [
    bigquery.SchemaField("id",           "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("quiebre_id",   "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("variable",     "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("titulo",       "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("descripcion",  "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("fuente",       "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("url",          "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("fecha_pub",    "DATE",    mode="NULLABLE"),
    bigquery.SchemaField("fecha_carga",  "TIMESTAMP", mode="REQUIRED"),
]


def crear_tabla(nombre_tabla: str, schema: list, descripcion: str = ""):
    table_id = f"{PROJECT_ID}.{DATASET}.{nombre_tabla}"
    table = bigquery.Table(table_id, schema=schema)
    table.description = descripcion
    try:
        CLIENT.get_table(table_id)
        print(f"  ✓ Tabla {nombre_tabla} ya existe — omitiendo")
    except Exception:
        CLIENT.create_table(table)
        print(f"  ✓ Tabla {nombre_tabla} creada")


def descargar_y_cargar_variables():
    try:
        import yfinance as yf
    except ImportError:
        print("Instala yfinance: pip install yfinance")
        return

    print("\nDescargando datos históricos (2024-01-01 → hoy)...")
    rows = []
    ahora = datetime.utcnow()

    for ticker, (nombre, categoria) in TICKERS.items():
        try:
            df_t = yf.download(ticker, start="2024-01-01",
                               progress=False, auto_adjust=True)
            if len(df_t) < 10:
                print(f"  ✗ {nombre}: sin datos")
                continue
            s = df_t['Close'].squeeze()
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = s.dropna()
            for fecha, valor in s.items():
                rows.append({
                    "fecha":      fecha.date(),
                    "ticker":     ticker,
                    "nombre":     nombre,
                    "categoria":  categoria,
                    "valor":      float(valor) if not np.isnan(valor) else None,
                    "cargado_en": ahora,
                })
            print(f"  ✓ {nombre}: {len(s)} obs")
        except Exception as e:
            print(f"  ✗ {nombre}: {e}")

    if not rows:
        print("Sin datos para cargar.")
        return

    df_load = pd.DataFrame(rows)
    table_id = f"{PROJECT_ID}.{DATASET}.gold_variables_mercado"

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=SCHEMA_VARIABLES,
    )
    job = CLIENT.load_table_from_dataframe(df_load, table_id, job_config=job_config)
    job.result()
    print(f"\n✓ Cargadas {len(df_load):,} filas en gold_variables_mercado")


def cargar_quiebre_ormuz():
    """Inserta el quiebre de Ormuz ya analizado como registro inicial."""
    quiebres = [
        ("ormuz_Brent_USD",         "Brent_USD",         "Energía",         945.3, 0.0000, 4.8, 35.7,  73.46,  99.70, "Crítico"),
        ("ormuz_WTI_USD",           "WTI_USD",           "Energía",         707.0, 0.0000, 4.4, 31.2,  69.68,  91.40, "Crítico"),
        ("ormuz_Gas_TTF_Europa",    "Gas_TTF_Europa",    "Energía",          65.7, 0.0000, 3.9, 49.2,  35.29,  52.64, "Crítico"),
        ("ormuz_Gas_HenryHub_USD",  "Gas_HenryHub_USD",  "Energía",           0.9, 0.4331, 0.3, -1.1,   3.06,   3.03, "Sin quiebre"),
        ("ormuz_Aluminio_USD",      "Aluminio_USD",      "Insumos_Acero",    78.1, 0.0000, 3.6, 29.3, 2517.81,3255.59, "Crítico"),
        ("ormuz_Mineral_Hierro",    "Mineral_Hierro",    "Insumos_Acero",     9.1, 0.0001, 2.1, -1.6,  105.97, 104.23, "Alto"),
        ("ormuz_Cobre_USD",         "Cobre_USD",         "Insumos_Acero",     6.7, 0.0014, 1.8, 22.3,    4.62,   5.65, "Alto"),
        ("ormuz_ETF_Acero_Global",  "ETF_Acero_Global",  "Sector_Acero",     27.8, 0.0000, 3.2, 33.0,   68.45,  91.01, "Crítico"),
        ("ormuz_Ternium_MX",        "Ternium_MX",        "Sector_Acero",     12.4, 0.0000, 2.4, 18.3,   33.26,  39.33, "Alto"),
        ("ormuz_ArcelorMittal",     "ArcelorMittal",     "Sector_Acero",     32.7, 0.0000, 3.5, 76.4,   30.48,  53.79, "Crítico"),
        ("ormuz_Nucor_EAF",         "Nucor_EAF",         "Sector_Acero",     21.4, 0.0000, 2.9, 12.9,  147.69, 166.80, "Alto"),
        ("ormuz_SteelDynamics_EAF", "SteelDynamics_EAF","Sector_Acero",      22.2, 0.0000, 2.9, 32.7,  133.80, 177.61, "Alto"),
        ("ormuz_ZIM_Contenedor",    "ZIM_Contenedor",    "Logistica",        79.1, 0.0000, 5.1, 94.2,   13.73,  26.66, "Crítico"),
        ("ormuz_ETF_Flete_Seco",    "ETF_Flete_Seco",   "Logistica",        31.8, 0.0000, 3.0, 15.6,    9.12,  10.54, "Crítico"),
        ("ormuz_Matson_Pacifico",   "Matson_Pacifico",  "Logistica",        39.1, 0.0000, 3.3, 30.6,  121.64, 158.90, "Crítico"),
        ("ormuz_BDI_Baltic_Dry",    "BDI_Baltic_Dry",   "Logistica",         2.7, 0.0679, 1.1, 18.3, 1731.45,2047.45, "Moderado"),
        ("ormuz_VIX",               "VIX",              "Riesgo_Mercados",  18.5, 0.0000, 3.1, 47.5,   17.30,  25.52, "Crítico"),
        ("ormuz_SP500",             "SP500",            "Riesgo_Mercados",  23.6, 0.0000, 2.8, 12.8, 5899.62,6652.11, "Alto"),
        ("ormuz_Oro_USD",           "Oro_USD",          "Riesgo_Mercados",  42.7, 0.0000, 3.5, 58.7, 3058.64,4854.15, "Crítico"),
        ("ormuz_Dolar_Index",       "Dolar_Index",      "Riesgo_Mercados",   4.2, 0.0150, 1.4, -2.6,  102.16,  99.48, "Alto"),
        ("ormuz_Nikkei_Japon",      "Nikkei_Japon",     "Asia",             21.2, 0.0000, 2.8, 31.2,41120.58,53964.90,"Alto"),
        ("ormuz_KOSPI_Corea",       "KOSPI_Corea",      "Asia",             74.9, 0.0000, 4.2, 81.9, 3037.24, 5524.28, "Crítico"),
        ("ormuz_ETF_China",         "ETF_China",        "Asia",            142.4, 0.0000, 4.8, 13.7,   31.61,  35.95, "Crítico"),
        ("ormuz_ETF_Japon",         "ETF_Japon",        "Asia",              9.2, 0.0001, 2.2, 21.6,   69.70,  84.78, "Alto"),
        ("ormuz_ETF_Corea",         "ETF_Corea",        "Asia",             71.3, 0.0000, 4.1, 87.8,   68.75, 129.11, "Crítico"),
        ("ormuz_ETF_Alemania",      "ETF_Alemania",     "Europa",           91.2, 0.0000, 4.3, 12.7,   35.62,  40.15, "Crítico"),
        ("ormuz_ETF_Emergentes",    "ETF_Emergentes",   "Europa",            8.3, 0.0003, 2.1, 27.4,   45.14,  57.51, "Alto"),
        ("ormuz_ETF_Mexico",        "ETF_Mexico",       "Mexico",           14.8, 0.0000, 2.8, 26.9,   58.16,  73.82, "Alto"),
        ("ormuz_USD_MXN",           "USD_MXN",          "Mexico",           13.8, 0.0000, 2.6, -4.8,   18.65,  17.76, "Alto"),
    ]

    ahora = datetime.utcnow()
    rows = []
    for q in quiebres:
        rows.append({
            "id":           q[0],
            "variable":     q[1],
            "categoria":    q[2],
            "fecha_corte":  datetime(2026, 2, 28).date(),
            "fecha_detect": datetime(2026, 3, 1).date(),
            "F_stat":       q[3],
            "p_value":      q[4],
            "sigma":        q[5],
            "cambio_pct":   q[6],
            "media_pre":    q[7],
            "media_post":   q[8],
            "severidad":    q[9],
            "activo":       True,
        })

    df_q = pd.DataFrame(rows)
    table_id = f"{PROJECT_ID}.{DATASET}.gold_quiebres_detectados"
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=SCHEMA_QUIEBRES,
    )
    job = CLIENT.load_table_from_dataframe(df_q, table_id, job_config=job_config)
    job.result()
    print(f"✓ {len(rows)} quiebres del evento Ormuz cargados en gold_quiebres_detectados")


if __name__ == "__main__":
    print("=" * 55)
    print("TYASA BI — Inicialización tablas de mercado")
    print("=" * 55)

    print("\n1. Creando tablas en BigQuery...")
    crear_tabla("gold_variables_mercado",  SCHEMA_VARIABLES, "Series diarias de variables de mercado global")
    crear_tabla("gold_quiebres_detectados", SCHEMA_QUIEBRES, "Quiebres estructurales detectados automáticamente")
    crear_tabla("gold_noticias_vinculadas", SCHEMA_NOTICIAS,  "Noticias vinculadas a cada quiebre de mercado")

    print("\n2. Cargando datos históricos desde yfinance...")
    descargar_y_cargar_variables()

    print("\n3. Cargando quiebres del evento Ormuz (28-Feb-2026)...")
    cargar_quiebre_ormuz()

    print("\n" + "=" * 55)
    print("✓ Inicialización completada")
    print("  Siguiente paso: python scripts/update_market_data.py")
    print("=" * 55)
