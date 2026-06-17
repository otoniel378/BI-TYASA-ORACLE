"""
transform_to_gold.py — Genera todas las tablas gold desde SILVER_VENTAS_LIMPIAS.

Tablas generadas:
  - GOLD_DEMANDA_CLIENTE    -> resumen por cliente
  - GOLD_DEMANDA_PRODUCTO   -> resumen por producto
  - GOLD_DEMANDA_MENSUAL    -> serie temporal mensual por producto
  - GOLD_CLIENTE_PRODUCTO   -> matriz cliente × producto
  - GOLD_DEMANDA_PROCESO    -> resumen por proceso productivo

Uso:
    python scripts/transform_to_gold.py
    python scripts/transform_to_gold.py --truncate
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import oracledb
from dotenv import load_dotenv

load_dotenv()

GOLD_TRANSFORMS = {
    "GOLD_DEMANDA_CLIENTE": """
        INSERT INTO ADMIN.GOLD_DEMANDA_CLIENTE
            (CLIENTE, AREA, DIVISION, PESO_TON, N_EMBARQUES, PRIMERA_COMPRA, ULTIMA_COMPRA)
        SELECT
            CLIENTE, AREA, DIVISION,
            SUM(PESO_TON)    AS PESO_TON,
            COUNT(*)         AS N_EMBARQUES,
            MIN(FECHAEMB)    AS PRIMERA_COMPRA,
            MAX(FECHAEMB)    AS ULTIMA_COMPRA
        FROM ADMIN.SILVER_VENTAS_LIMPIAS
        GROUP BY CLIENTE, AREA, DIVISION
    """,

    "GOLD_DEMANDA_PRODUCTO": """
        INSERT INTO ADMIN.GOLD_DEMANDA_PRODUCTO
            (PRODUCTO_LIMPIO, AREA, DIVISION, PESO_TON, N_CLIENTES)
        SELECT
            PRODUCTO_LIMPIO, AREA, DIVISION,
            SUM(PESO_TON)           AS PESO_TON,
            COUNT(DISTINCT CLIENTE) AS N_CLIENTES
        FROM ADMIN.SILVER_VENTAS_LIMPIAS
        GROUP BY PRODUCTO_LIMPIO, AREA, DIVISION
    """,

    "GOLD_DEMANDA_MENSUAL": """
        INSERT INTO ADMIN.GOLD_DEMANDA_MENSUAL
            (PERIODO, ANIO, MES, PRODUCTO_LIMPIO, AREA, DIVISION,
             PESO_TON, N_CLIENTES, N_EMBARQUES)
        SELECT
            PERIODO, ANIO, MES, PRODUCTO_LIMPIO, AREA, DIVISION,
            SUM(PESO_TON)           AS PESO_TON,
            COUNT(DISTINCT CLIENTE) AS N_CLIENTES,
            COUNT(*)                AS N_EMBARQUES
        FROM ADMIN.SILVER_VENTAS_LIMPIAS
        GROUP BY PERIODO, ANIO, MES, PRODUCTO_LIMPIO, AREA, DIVISION
    """,

    "GOLD_CLIENTE_PRODUCTO": """
        INSERT INTO ADMIN.GOLD_CLIENTE_PRODUCTO
            (CLIENTE, PRODUCTO_LIMPIO, AREA, DIVISION, PESO_TON, N_EMBARQUES)
        SELECT
            CLIENTE, PRODUCTO_LIMPIO, AREA, DIVISION,
            SUM(PESO_TON)  AS PESO_TON,
            COUNT(*)       AS N_EMBARQUES
        FROM ADMIN.SILVER_VENTAS_LIMPIAS
        GROUP BY CLIENTE, PRODUCTO_LIMPIO, AREA, DIVISION
    """,

    "GOLD_DEMANDA_PROCESO": """
        INSERT INTO ADMIN.GOLD_DEMANDA_PROCESO
            (PROCESO, AREA, DIVISION, PESO_TON, N_CLIENTES, N_EMBARQUES)
        SELECT
            PROCESO, AREA, DIVISION,
            SUM(PESO_TON)           AS PESO_TON,
            COUNT(DISTINCT CLIENTE) AS N_CLIENTES,
            COUNT(*)                AS N_EMBARQUES
        FROM ADMIN.SILVER_VENTAS_LIMPIAS
        GROUP BY PROCESO, AREA, DIVISION
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


def build_gold(truncate: bool = False):
    print("Conectando a Oracle ADW...")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        for table, sql in GOLD_TRANSFORMS.items():
            if truncate:
                cursor.execute(f"TRUNCATE TABLE ADMIN.{table}")
                conn.commit()
            cursor.execute(sql.strip())
            rows = cursor.rowcount
            conn.commit()
            print(f"  OK {table}: {rows:,} filas")
        print("\nOK Todas las tablas gold generadas correctamente.")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR Error en {table}: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera tablas gold desde silver")
    parser.add_argument("--truncate", action="store_true",
                        help="Vacía las tablas gold antes de regenerar")
    args = parser.parse_args()
    build_gold(truncate=args.truncate)
