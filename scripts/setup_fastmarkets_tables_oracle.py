"""
scripts/setup_fastmarkets_tables_oracle.py — Crea la tabla Oracle ADW para
los precios/pronósticos históricos de Fastmarkets (exportados a mano desde
su dashboard, sin API en este plan de acceso). Correr una sola vez.

Uso:
    python scripts/setup_fastmarkets_tables_oracle.py
    python scripts/setup_fastmarkets_tables_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "BRONZE_FASTMARKETS_PRECIOS": """
        CREATE TABLE ADMIN.BRONZE_FASTMARKETS_PRECIOS (
            SYMBOL          VARCHAR2(50)   NOT NULL,
            DESCRIPCION     VARCHAR2(500),
            TITULO_WIDGET   VARCHAR2(200),
            FECHA           DATE           NOT NULL,
            MEDIDA          VARCHAR2(20)   NOT NULL,
            VALOR           NUMBER,
            TIPO            VARCHAR2(20)   NOT NULL,
            ARCHIVO_ORIGEN  VARCHAR2(200),
            FECHA_CARGA     TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_FASTMARKETS_PRECIOS PRIMARY KEY (SYMBOL, FECHA, MEDIDA)
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


def _drop_table(cursor, name: str):
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
                _drop_table(cursor, name)
            try:
                cursor.execute(ddl.strip())
                conn.commit()
                print(f"  CREATE {name}")
            except oracledb.DatabaseError as e:
                if "ORA-00955" in str(e):
                    print(f"  {name} ya existe, se omite")
                else:
                    raise
        cursor.execute(
            "CREATE INDEX IDX_FASTMARKETS_SYMBOL ON ADMIN.BRONZE_FASTMARKETS_PRECIOS (SYMBOL)"
        )
        conn.commit()
        print("  CREATE INDEX IDX_FASTMARKETS_SYMBOL")
    except oracledb.DatabaseError as e:
        if "ORA-01408" in str(e) or "ORA-00955" in str(e):
            print("  Índice ya existe, se omite")
        else:
            raise
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
