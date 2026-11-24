"""
scripts/setup_rutas_oracle.py — Crea las tablas de tráfico marítimo de la página
Rutas y puertos (pages/mercado/10_rutas_puertos.py), que llena
scripts/update_trafico_maritimo.py con IMF PortWatch.

  GOLD_TRAFICO_PASOS   — barcos que cruzan al día cada paso marítimo (mercado_rutas/red.PASOS)
  GOLD_TRAFICO_PUERTOS — barcos que llegan al día a cada puerto de llegada (red.PUERTOS)

Uso:
    python scripts/setup_rutas_oracle.py
    python scripts/setup_rutas_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "GOLD_TRAFICO_PASOS": """
        CREATE TABLE ADMIN.GOLD_TRAFICO_PASOS (
            FECHA       DATE          NOT NULL,
            PASO        VARCHAR2(20)  NOT NULL,
            TRANSITOS   NUMBER(8,2),
            GRANEL      NUMBER(8,2),
            CARGADO_EN  TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_TRAFICO_PASOS PRIMARY KEY (FECHA, PASO)
        )
    """,
    "GOLD_TRAFICO_PUERTOS": """
        CREATE TABLE ADMIN.GOLD_TRAFICO_PUERTOS (
            FECHA       DATE          NOT NULL,
            PUERTO      VARCHAR2(20)  NOT NULL,
            LLAMADAS    NUMBER(8,2),
            GRANEL      NUMBER(8,2),
            CARGADO_EN  TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_TRAFICO_PUERTOS PRIMARY KEY (FECHA, PUERTO)
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


def create_tables(recreate: bool = False):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        for name, ddl in TABLES_DDL.items():
            if recreate:
                try:
                    cursor.execute(f"DROP TABLE ADMIN.{name}")
                except oracledb.DatabaseError:
                    pass
            try:
                cursor.execute(ddl.strip())
                conn.commit()
                print(f"  CREATE {name}")
            except oracledb.DatabaseError as e:
                if "ORA-00955" in str(e):
                    print(f"  {name} ya existe, se omite")
                else:
                    raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true", help="Elimina y re-crea las tablas")
    args = parser.parse_args()
    print("Conectando a Oracle ADW...")
    create_tables(recreate=args.recreate)
    print("\nSetup de tráfico marítimo completado.")
