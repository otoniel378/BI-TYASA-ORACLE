"""
scripts/setup_fastmarkets_table_oracle.py — Crea la tabla Oracle ADW del
pipeline Fastmarkets (precios de acero exportados manualmente del dashboard).

Tabla creada:
  GOLD_PRECIOS_FASTMARKETS — 1 fila por símbolo + fecha de evaluación.
  Se recarga por símbolo completo en cada corrida de load_fastmarkets_csv.py
  (no crece sin control: cada export trae el histórico completo del símbolo).

Uso:
    python scripts/setup_fastmarkets_table_oracle.py
    python scripts/setup_fastmarkets_table_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "GOLD_PRECIOS_FASTMARKETS": """
        CREATE TABLE ADMIN.GOLD_PRECIOS_FASTMARKETS (
            SIMBOLO      VARCHAR2(20)  NOT NULL,
            DESCRIPCION  VARCHAR2(500),
            FECHA        DATE          NOT NULL,
            VALOR        NUMBER,
            MONEDA       VARCHAR2(10),
            UNIDAD       VARCHAR2(30),
            CARGADO_EN   TIMESTAMP
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true",
                        help="Elimina y re-crea la tabla Fastmarkets")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    create_tables(recreate=args.recreate)
    print("\nSetup de tabla Fastmarkets completado.")
    print("Siguiente: python scripts/load_fastmarkets_csv.py")
