"""
setup_market_tables_oracle.py — Crea tablas de mercado en Oracle ADW y carga datos iniciales.

Tablas creadas:
  - GOLD_VARIABLES_MERCADO      — series diarias yfinance (31 variables)
  - GOLD_QUIEBRES_DETECTADOS    — quiebres estructurales detectados
  - GOLD_NOTICIAS_VINCULADAS    — noticias vinculadas a quiebres
  - GOLD_SENTIMIENTO_NOTICIAS   — noticias con análisis de sentimiento
  - GOLD_INDICADORES_INEGI      — indicadores macro INEGI

Uso:
    python scripts/setup_market_tables_oracle.py
    python scripts/setup_market_tables_oracle.py --recreate
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import math
from datetime import datetime
import numpy as np
import pandas as pd
import oracledb
from dotenv import load_dotenv

load_dotenv()

TICKERS = {
    'BZ=F'    : ('Brent_USD',          'Energia'),
    'CL=F'    : ('WTI_USD',            'Energia'),
    'NG=F'    : ('Gas_HenryHub_USD',   'Energia'),
    'TTF=F'   : ('Gas_TTF_Europa',     'Energia'),
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
    '^VIX'    : ('VIX',                'Riesgo_Mercados'),
    '^GSPC'   : ('SP500',              'Riesgo_Mercados'),
    'GC=F'    : ('Oro_USD',            'Riesgo_Mercados'),
    'DX-Y.NYB': ('Dolar_Index',        'Riesgo_Mercados'),
    'TLT'     : ('Bonos_20y',          'Riesgo_Mercados'),
    '^N225'   : ('Nikkei_Japon',       'Asia'),
    '^KS11'   : ('KOSPI_Corea',        'Asia'),
    'FXI'     : ('ETF_China',          'Asia'),
    'EWJ'     : ('ETF_Japon',          'Asia'),
    'EWY'     : ('ETF_Corea',          'Asia'),
    'EWG'     : ('ETF_Alemania',       'Europa'),
    'EEM'     : ('ETF_Emergentes',     'Europa'),
    'EWW'     : ('ETF_Mexico',         'Mexico'),
    'MXN=X'   : ('USD_MXN',           'Mexico'),
}

TABLES_DDL = {
    "GOLD_VARIABLES_MERCADO": """
        CREATE TABLE ADMIN.GOLD_VARIABLES_MERCADO (
            FECHA       DATE          NOT NULL,
            TICKER      VARCHAR2(20)  NOT NULL,
            NOMBRE      VARCHAR2(100) NOT NULL,
            CATEGORIA   VARCHAR2(50)  NOT NULL,
            VALOR       NUMBER,
            CARGADO_EN  TIMESTAMP
        )
    """,
    "GOLD_QUIEBRES_DETECTADOS": """
        CREATE TABLE ADMIN.GOLD_QUIEBRES_DETECTADOS (
            ID           VARCHAR2(100) NOT NULL,
            VARIABLE     VARCHAR2(100) NOT NULL,
            CATEGORIA    VARCHAR2(50)  NOT NULL,
            FECHA_CORTE  DATE          NOT NULL,
            FECHA_DETECT DATE          NOT NULL,
            F_STAT       NUMBER,
            P_VALUE      NUMBER,
            SIGMA        NUMBER,
            CAMBIO_PCT   NUMBER,
            MEDIA_PRE    NUMBER,
            MEDIA_POST   NUMBER,
            SEVERIDAD    VARCHAR2(50),
            ACTIVO       NUMBER(1)     DEFAULT 1
        )
    """,
    "GOLD_NOTICIAS_VINCULADAS": """
        CREATE TABLE ADMIN.GOLD_NOTICIAS_VINCULADAS (
            ID           VARCHAR2(100) NOT NULL,
            QUIEBRE_ID   VARCHAR2(100) NOT NULL,
            VARIABLE     VARCHAR2(100) NOT NULL,
            TITULO       VARCHAR2(1000),
            DESCRIPCION  VARCHAR2(4000),
            FUENTE       VARCHAR2(200),
            URL          VARCHAR2(2000),
            FECHA_PUB    DATE,
            FECHA_CARGA  TIMESTAMP
        )
    """,
    "GOLD_SENTIMIENTO_NOTICIAS": """
        CREATE TABLE ADMIN.GOLD_SENTIMIENTO_NOTICIAS (
            ID                  VARCHAR2(100),
            TITULO              VARCHAR2(1000),
            DESCRIPCION         VARCHAR2(4000),
            FUENTE              VARCHAR2(200),
            URL                 VARCHAR2(2000),
            FECHA_PUB           DATE,
            FECHA_ANALISIS      TIMESTAMP,
            SENTIMIENTO         VARCHAR2(20),
            SCORE               NUMBER,
            VARIABLE_PRINCIPAL  VARCHAR2(100),
            ALCANCE             VARCHAR2(50),
            GRUPO_TEMATICO      VARCHAR2(50)
        )
    """,
    "GOLD_INDICADORES_INEGI": """
        CREATE TABLE ADMIN.GOLD_INDICADORES_INEGI (
            CLAVE   VARCHAR2(20)  NOT NULL,
            NOMBRE  VARCHAR2(200),
            FECHA   VARCHAR2(10),
            VALOR   NUMBER
        )
    """,
}


def get_conn() -> oracledb.Connection:
    wallet_dir = os.environ.get("ORACLE_WALLET_DIR", "")
    params = {
        "user":     os.environ.get("ORACLE_USER", "ADMIN"),
        "password": os.environ.get("ORACLE_PASSWORD", ""),
        "dsn":      os.environ.get("ORACLE_DSN", ""),
    }
    if wallet_dir:
        params["config_dir"]      = wallet_dir
        params["wallet_location"] = wallet_dir
        wallet_pw = os.environ.get("ORACLE_WALLET_PASSWORD", "")
        if wallet_pw:
            params["wallet_password"] = wallet_pw
    return oracledb.connect(**params)


def drop_table(cursor, name: str):
    try:
        cursor.execute(f"DROP TABLE ADMIN.{name}")
    except oracledb.DatabaseError:
        pass


def create_tables(recreate: bool = False):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        for name, ddl in TABLES_DDL.items():
            if recreate:
                drop_table(cursor, name)
            cursor.execute(ddl.strip())
            conn.commit()
            print(f"  CREATE {name}")
    finally:
        cursor.close()
        conn.close()


def _to_python(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(val, "item"):
        return val.item()
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime()
    return val


def load_yfinance(batch_size: int = 5000):
    try:
        import yfinance as yf
    except ImportError:
        print("Instala yfinance: pip install yfinance")
        return

    print("\nDescargando series de yfinance (2024-01-01 -> hoy)...")
    rows = []
    ahora = datetime.utcnow()

    for ticker, (nombre, categoria) in TICKERS.items():
        try:
            df_t = yf.download(ticker, start="2024-01-01", progress=False, auto_adjust=True)
            if len(df_t) < 5:
                print(f"  Sin datos: {nombre}")
                continue
            s = df_t["Close"].squeeze()
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = s.dropna()
            for fecha, valor in s.items():
                rows.append((
                    fecha.date(),
                    ticker,
                    nombre,
                    categoria,
                    float(valor) if not np.isnan(float(valor)) else None,
                    ahora,
                ))
            print(f"  OK {nombre}: {len(s)} obs")
        except Exception as e:
            print(f"  ERROR {nombre}: {e}")

    if not rows:
        print("Sin datos para cargar.")
        return

    INSERT = """
        INSERT INTO ADMIN.GOLD_VARIABLES_MERCADO
            (FECHA, TICKER, NOMBRE, CATEGORIA, VALOR, CARGADO_EN)
        VALUES (:1,:2,:3,:4,:5,:6)
    """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("TRUNCATE TABLE ADMIN.GOLD_VARIABLES_MERCADO")
        conn.commit()
        n_batches = math.ceil(len(rows) / batch_size)
        for i in range(n_batches):
            batch = rows[i * batch_size:(i + 1) * batch_size]
            cursor.executemany(INSERT, batch)
            conn.commit()
        print(f"  OK {len(rows):,} filas en GOLD_VARIABLES_MERCADO")
    finally:
        cursor.close()
        conn.close()


def load_quiebres():
    quiebres = [
        ("ormuz_Brent_USD",         "Brent_USD",         "Energia",         945.3, 0.0000, 4.8, 35.7,  73.46,  99.70, "Critico"),
        ("ormuz_WTI_USD",           "WTI_USD",           "Energia",         707.0, 0.0000, 4.4, 31.2,  69.68,  91.40, "Critico"),
        ("ormuz_Gas_TTF_Europa",    "Gas_TTF_Europa",    "Energia",          65.7, 0.0000, 3.9, 49.2,  35.29,  52.64, "Critico"),
        ("ormuz_Gas_HenryHub_USD",  "Gas_HenryHub_USD",  "Energia",           0.9, 0.4331, 0.3, -1.1,   3.06,   3.03, "Sin quiebre"),
        ("ormuz_Aluminio_USD",      "Aluminio_USD",      "Insumos_Acero",    78.1, 0.0000, 3.6, 29.3, 2517.81,3255.59, "Critico"),
        ("ormuz_Mineral_Hierro",    "Mineral_Hierro",    "Insumos_Acero",     9.1, 0.0001, 2.1, -1.6,  105.97, 104.23, "Alto"),
        ("ormuz_Cobre_USD",         "Cobre_USD",         "Insumos_Acero",     6.7, 0.0014, 1.8, 22.3,    4.62,   5.65, "Alto"),
        ("ormuz_ETF_Acero_Global",  "ETF_Acero_Global",  "Sector_Acero",     27.8, 0.0000, 3.2, 33.0,   68.45,  91.01, "Critico"),
        ("ormuz_Ternium_MX",        "Ternium_MX",        "Sector_Acero",     12.4, 0.0000, 2.4, 18.3,   33.26,  39.33, "Alto"),
        ("ormuz_ArcelorMittal",     "ArcelorMittal",     "Sector_Acero",     32.7, 0.0000, 3.5, 76.4,   30.48,  53.79, "Critico"),
        ("ormuz_Nucor_EAF",         "Nucor_EAF",         "Sector_Acero",     21.4, 0.0000, 2.9, 12.9,  147.69, 166.80, "Alto"),
        ("ormuz_SteelDynamics_EAF", "SteelDynamics_EAF","Sector_Acero",      22.2, 0.0000, 2.9, 32.7,  133.80, 177.61, "Alto"),
        ("ormuz_ZIM_Contenedor",    "ZIM_Contenedor",    "Logistica",        79.1, 0.0000, 5.1, 94.2,   13.73,  26.66, "Critico"),
        ("ormuz_ETF_Flete_Seco",    "ETF_Flete_Seco",   "Logistica",        31.8, 0.0000, 3.0, 15.6,    9.12,  10.54, "Critico"),
        ("ormuz_Matson_Pacifico",   "Matson_Pacifico",  "Logistica",        39.1, 0.0000, 3.3, 30.6,  121.64, 158.90, "Critico"),
        ("ormuz_VIX",               "VIX",              "Riesgo_Mercados",  18.5, 0.0000, 3.1, 47.5,   17.30,  25.52, "Critico"),
        ("ormuz_SP500",             "SP500",            "Riesgo_Mercados",  23.6, 0.0000, 2.8, 12.8, 5899.62,6652.11, "Alto"),
        ("ormuz_Oro_USD",           "Oro_USD",          "Riesgo_Mercados",  42.7, 0.0000, 3.5, 58.7, 3058.64,4854.15, "Critico"),
        ("ormuz_Dolar_Index",       "Dolar_Index",      "Riesgo_Mercados",   4.2, 0.0150, 1.4, -2.6,  102.16,  99.48, "Alto"),
        ("ormuz_Nikkei_Japon",      "Nikkei_Japon",     "Asia",             21.2, 0.0000, 2.8, 31.2,41120.58,53964.90,"Alto"),
        ("ormuz_KOSPI_Corea",       "KOSPI_Corea",      "Asia",             74.9, 0.0000, 4.2, 81.9, 3037.24, 5524.28, "Critico"),
        ("ormuz_ETF_China",         "ETF_China",        "Asia",            142.4, 0.0000, 4.8, 13.7,   31.61,  35.95, "Critico"),
        ("ormuz_ETF_Japon",         "ETF_Japon",        "Asia",              9.2, 0.0001, 2.2, 21.6,   69.70,  84.78, "Alto"),
        ("ormuz_ETF_Corea",         "ETF_Corea",        "Asia",             71.3, 0.0000, 4.1, 87.8,   68.75, 129.11, "Critico"),
        ("ormuz_ETF_Alemania",      "ETF_Alemania",     "Europa",           91.2, 0.0000, 4.3, 12.7,   35.62,  40.15, "Critico"),
        ("ormuz_ETF_Emergentes",    "ETF_Emergentes",   "Europa",            8.3, 0.0003, 2.1, 27.4,   45.14,  57.51, "Alto"),
        ("ormuz_ETF_Mexico",        "ETF_Mexico",       "Mexico",           14.8, 0.0000, 2.8, 26.9,   58.16,  73.82, "Alto"),
        ("ormuz_USD_MXN",           "USD_MXN",          "Mexico",           13.8, 0.0000, 2.6, -4.8,   18.65,  17.76, "Alto"),
    ]

    INSERT = """
        INSERT INTO ADMIN.GOLD_QUIEBRES_DETECTADOS
            (ID, VARIABLE, CATEGORIA, FECHA_CORTE, FECHA_DETECT,
             F_STAT, P_VALUE, SIGMA, CAMBIO_PCT, MEDIA_PRE, MEDIA_POST, SEVERIDAD, ACTIVO)
        VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13)
    """
    fecha_corte  = datetime(2026, 2, 28).date()
    fecha_detect = datetime(2026, 3, 1).date()

    rows = [
        (q[0], q[1], q[2], fecha_corte, fecha_detect,
         q[3], q[4], q[5], q[6], q[7], q[8], q[9], 1)
        for q in quiebres
    ]

    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("TRUNCATE TABLE ADMIN.GOLD_QUIEBRES_DETECTADOS")
        conn.commit()
        cursor.executemany(INSERT, rows)
        conn.commit()
        print(f"  OK {len(rows)} quiebres cargados en GOLD_QUIEBRES_DETECTADOS")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true",
                        help="Elimina y re-crea las tablas de mercado")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    print("\n1. Creando tablas de mercado...")
    create_tables(recreate=args.recreate)

    print("\n2. Cargando quiebres estructurales (evento Ormuz)...")
    load_quiebres()

    print("\n3. Descargando series de mercado desde yfinance...")
    load_yfinance()

    print("\nSetup de tablas de mercado completado.")
    print("Siguiente: python scripts/update_market_data.py")
