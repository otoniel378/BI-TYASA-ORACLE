"""
transform_to_silver.py — Transforma BRONZE_VENTAS_RAW -> SILVER_VENTAS_LIMPIAS.

Limpieza aplicada:
  - CLIENTE y PROCESO: TRIM + UPPER
  - PRODUCTO_LIMPIO: TRIM + UPPER del producto original
  - PESO_TON: PESO / 1000
  - PERIODO: primer día del mes de FECHAEMB
  - AREA = 'NEGROS', DIVISION = 'PLANOS' (todos los datos actuales)
  - Se excluyen filas sin FECHAEMB

Uso:
    python scripts/transform_to_silver.py
    python scripts/transform_to_silver.py --truncate
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import oracledb
from dotenv import load_dotenv

load_dotenv()

SQL_TRANSFORM = """
    INSERT INTO ADMIN.SILVER_VENTAS_LIMPIAS (
        FECHAEMB, CLIENTE, PRODUCTO_ORIGINAL, PRODUCTO_LIMPIO,
        PROCESO, CALIBRE, ANCHO, PESO_KG, PESO_TON,
        COLADA, PIEZAS, ANIO, MES, PERIODO, AREA, DIVISION
    )
    SELECT
        FECHAEMB,
        TRIM(UPPER(CLIENTE))          AS CLIENTE,
        PRODUCTO                      AS PRODUCTO_ORIGINAL,
        TRIM(UPPER(PRODUCTO))         AS PRODUCTO_LIMPIO,
        TRIM(UPPER(PROCESO))          AS PROCESO,
        CALIBRE,
        ANCHO,
        PESO                          AS PESO_KG,
        ROUND(PESO / 1000, 6)         AS PESO_TON,
        COLADA,
        PIEZAS,
        EXTRACT(YEAR  FROM FECHAEMB)  AS ANIO,
        EXTRACT(MONTH FROM FECHAEMB)  AS MES,
        TRUNC(FECHAEMB, 'MM')         AS PERIODO,
        'NEGROS'                      AS AREA,
        'PLANOS'                      AS DIVISION
    FROM ADMIN.BRONZE_VENTAS_RAW
    WHERE FECHAEMB IS NOT NULL
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


def transform(truncate: bool = False):
    print("Conectando a Oracle ADW...")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if truncate:
            cursor.execute("TRUNCATE TABLE ADMIN.SILVER_VENTAS_LIMPIAS")
            conn.commit()
            print("  TRUNCATE SILVER_VENTAS_LIMPIAS")

        print("  Ejecutando transformación bronze -> silver...")
        cursor.execute(SQL_TRANSFORM)
        rows = cursor.rowcount
        conn.commit()
        print(f"\nOK {rows:,} filas insertadas en SILVER_VENTAS_LIMPIAS")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transforma bronze -> silver")
    parser.add_argument("--truncate", action="store_true",
                        help="Vacía silver antes de transformar (evita duplicados)")
    args = parser.parse_args()
    transform(truncate=args.truncate)
