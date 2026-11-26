"""
scripts/setup_tigie_base_oracle.py — Crea ADMIN.GOLD_TIGIE_BASE: el arancel
general (IGI/IGE) por fracción de los capítulos 72/73, capa base del historial
de aranceles (ver scripts/cargar_tigie_base_oracle.py, que la llena, y
ADMIN.GOLD_MEDIDAS_ARANCELARIAS para los cambios posteriores vía DOF).

Uso:
    python scripts/setup_tigie_base_oracle.py
    python scripts/setup_tigie_base_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLE_DDL = """
    CREATE TABLE ADMIN.GOLD_TIGIE_BASE (
        FRACCION          VARCHAR2(10)   NOT NULL,
        NICO              VARCHAR2(5),
        DESCRIPCION       VARCHAR2(500),
        UNIDAD_MEDIDA     VARCHAR2(10),
        IGI               VARCHAR2(20),
        IGE               VARCHAR2(20),
        ES_FRACCION_TYASA NUMBER(1)      DEFAULT 0,
        LINEA_TYASA       VARCHAR2(40),
        FUENTE_FECHA      VARCHAR2(10),
        CARGADO_EN        TIMESTAMP DEFAULT SYSTIMESTAMP,
        CONSTRAINT PK_TIGIE_BASE PRIMARY KEY (FRACCION)
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


def create_table(recreate: bool = False):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if recreate:
            try:
                cursor.execute("DROP TABLE ADMIN.GOLD_TIGIE_BASE")
            except oracledb.DatabaseError:
                pass
        try:
            cursor.execute(TABLE_DDL.strip())
            conn.commit()
            print("  CREATE GOLD_TIGIE_BASE")
        except oracledb.DatabaseError as e:
            if "ORA-00955" in str(e):
                print("  GOLD_TIGIE_BASE ya existe, se omite")
            else:
                raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true", help="Elimina y re-crea la tabla")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    create_table(recreate=args.recreate)
    print("\nSetup de TIGIE base completado.")
