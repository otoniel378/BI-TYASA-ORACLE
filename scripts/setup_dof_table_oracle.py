"""
scripts/setup_dof_table_oracle.py — Crea ADMIN.GOLD_ALERTAS_DOF, donde
scripts/monitor_dof.py registra cada publicación del DOF ya analizada (sea o
no relevante) para no reprocesarla/reenviar la alerta en una corrida futura
(9am vs. 3pm del mismo día, o días siguientes).

Uso:
    python scripts/setup_dof_table_oracle.py
    python scripts/setup_dof_table_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLE_DDL = """
    CREATE TABLE ADMIN.GOLD_ALERTAS_DOF (
        CODIGO           VARCHAR2(20)   NOT NULL,
        FECHA_DOF        VARCHAR2(10),
        DEPENDENCIA      VARCHAR2(300),
        DESCRIPCION      VARCHAR2(1000),
        URL              VARCHAR2(500),
        RELEVANTE        NUMBER(1)      DEFAULT 0,
        IMPACTO          VARCHAR2(10),
        DIRECCION        VARCHAR2(15),
        RESUMEN          VARCHAR2(1000),
        FRACCIONES_TYASA VARCHAR2(500),
        CORREO_ENVIADO   NUMBER(1)      DEFAULT 0,
        ANALIZADO_EN     TIMESTAMP DEFAULT SYSTIMESTAMP,
        CONSTRAINT PK_ALERTAS_DOF PRIMARY KEY (CODIGO)
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
                cursor.execute("DROP TABLE ADMIN.GOLD_ALERTAS_DOF")
            except oracledb.DatabaseError:
                pass
        try:
            cursor.execute(TABLE_DDL.strip())
            conn.commit()
            print("  CREATE GOLD_ALERTAS_DOF")
        except oracledb.DatabaseError as e:
            if "ORA-00955" in str(e):
                print("  GOLD_ALERTAS_DOF ya existe, se omite")
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
    print("\nSetup de alertas DOF completado.")
