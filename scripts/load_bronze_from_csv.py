"""
load_bronze_from_csv.py — Carga el CSV de ventas a BRONZE_VENTAS_RAW en Oracle ADW.

Uso:
    python scripts/load_bronze_from_csv.py --csv "C:/datos/ventas.csv"
    python scripts/load_bronze_from_csv.py --csv "C:/datos/ventas.csv" --truncate
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import math
import oracledb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATE_COLS    = ["FECHAEMB", "FHEMBARQUE"]
NUMERIC_COLS = ["SECUENCIA", "CALIBRE", "ANCHO", "PESO", "PIEZAS",
                "LARGO", "ESPESOR_REAL", "ESPESOR", "PESOBRUTO"]
STR_COLS     = ["CVECLIENTE", "CLIENTE", "PEDIDO", "POSICION", "CVESAP",
                "EMBARQUE", "REMISION", "PLACAS", "CVEMAT_PROD", "PRODUCTO",
                "COLADA", "PARTE_CLIENTE", "NIV_CALIDAD", "TARIMA", "PROCESO"]

COLS_ORDER = [
    "FECHAEMB", "FHEMBARQUE", "CVECLIENTE", "CLIENTE", "PEDIDO", "POSICION",
    "CVESAP", "EMBARQUE", "REMISION", "PLACAS", "CVEMAT_PROD", "PRODUCTO",
    "SECUENCIA", "CALIBRE", "ANCHO", "PESO", "COLADA", "PIEZAS", "LARGO",
    "PARTE_CLIENTE", "ESPESOR_REAL", "ESPESOR", "PESOBRUTO",
    "NIV_CALIDAD", "TARIMA", "PROCESO",
]

INSERT_SQL = """
    INSERT INTO ADMIN.BRONZE_VENTAS_RAW (
        FECHAEMB, FHEMBARQUE, CVECLIENTE, CLIENTE, PEDIDO, POSICION,
        CVESAP, EMBARQUE, REMISION, PLACAS, CVEMAT_PROD, PRODUCTO,
        SECUENCIA, CALIBRE, ANCHO, PESO, COLADA, PIEZAS, LARGO,
        PARTE_CLIENTE, ESPESOR_REAL, ESPESOR, PESOBRUTO,
        NIV_CALIDAD, TARIMA, PROCESO
    ) VALUES (
        :1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,
        :13,:14,:15,:16,:17,:18,:19,:20,:21,:22,:23,:24,:25,:26
    )
"""


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


def read_file(path: str) -> pd.DataFrame:
    """Lee CSV o Excel automáticamente según la extensión."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, engine="openpyxl")
        print(f"  Excel leido | {len(df):,} filas | {len(df.columns)} columnas")
        return df
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(path, encoding=enc, sep=None, engine="python",
                             low_memory=False)
            print(f"  Encoding: {enc} | {len(df):,} filas | {len(df.columns)} columnas")
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo leer el archivo (probados: xlsx, utf-8, latin-1, cp1252)")


def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().upper() for c in df.columns]

    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in STR_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None})

    for col in COLS_ORDER:
        if col not in df.columns:
            df[col] = None

    return df[COLS_ORDER]


def _to_python(val):
    """Convierte valores numpy/pandas a tipos nativos de Python para oracledb."""
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


def load(csv_path: str, truncate: bool = False, batch_size: int = 5000):
    print(f"Leyendo archivo: {csv_path}")
    df = read_file(csv_path)
    df = clean_df(df)

    rows = [
        tuple(_to_python(v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]
    total    = len(rows)
    n_batches = math.ceil(total / batch_size)

    print("Conectando a Oracle ADW...")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if truncate:
            cursor.execute("TRUNCATE TABLE ADMIN.BRONZE_VENTAS_RAW")
            conn.commit()
            print("  TRUNCATE BRONZE_VENTAS_RAW")

        print(f"  Insertando {total:,} filas en {n_batches} lotes de {batch_size}...")
        for i in range(n_batches):
            batch = rows[i * batch_size : (i + 1) * batch_size]
            cursor.executemany(INSERT_SQL, batch)
            conn.commit()
            pct = round((i + 1) / n_batches * 100)
            print(f"    Lote {i+1}/{n_batches} ({pct}%)")

        print(f"\nOK {total:,} filas cargadas en BRONZE_VENTAS_RAW")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga el CSV a BRONZE_VENTAS_RAW")
    parser.add_argument("--csv",      required=True, help="Ruta al archivo CSV")
    parser.add_argument("--truncate", action="store_true",
                        help="Vacía la tabla antes de insertar (evita duplicados)")
    args = parser.parse_args()
    load(args.csv, truncate=args.truncate)
