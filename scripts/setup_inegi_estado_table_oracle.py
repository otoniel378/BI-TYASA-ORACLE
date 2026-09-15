"""
scripts/setup_inegi_estado_table_oracle.py — Crea la tabla Oracle ADW para
indicadores INEGI desagregados por entidad federativa (mapa de calor por
estado). Correr una sola vez.

Uso:
    python scripts/setup_inegi_estado_table_oracle.py
    python scripts/setup_inegi_estado_table_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "GOLD_INDICADORES_INEGI_ESTADO": """
        CREATE TABLE ADMIN.GOLD_INDICADORES_INEGI_ESTADO (
            CLAVE           VARCHAR2(20)  NOT NULL,
            NOMBRE          VARCHAR2(200) NOT NULL,
            ESTADO_CVE      VARCHAR2(2)   NOT NULL,
            ESTADO_ISO      VARCHAR2(10)  NOT NULL,
            ESTADO_NOMBRE   VARCHAR2(100) NOT NULL,
            FECHA           VARCHAR2(7)   NOT NULL,
            VALOR           NUMBER,
            FECHA_CARGA     TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_INEGI_ESTADO PRIMARY KEY (CLAVE, ESTADO_CVE, FECHA)
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
            "CREATE INDEX IDX_INEGI_ESTADO_CLAVE ON ADMIN.GOLD_INDICADORES_INEGI_ESTADO (CLAVE)"
        )
        conn.commit()
        print("  CREATE INDEX IDX_INEGI_ESTADO_CLAVE")
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
                        help="Elimina y re-crea la tabla de indicadores INEGI por estado")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    create_tables(recreate=args.recreate)
    print("\nSetup de tabla INEGI por estado completado.")
