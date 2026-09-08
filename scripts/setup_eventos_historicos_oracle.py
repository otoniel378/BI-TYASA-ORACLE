"""
scripts/setup_eventos_historicos_oracle.py — Crea la tabla de eventos
históricos curados a mano (COVID, aranceles, etc.) que se cruzan con el
timeline de contexto macro en pages/mercado/08_pronostico_comercio.py.

No hay fuente automática confiable de noticias históricas (la búsqueda del
proyecto es solo en vivo), así que esta tabla se siembra manualmente — ver
scripts/seed_eventos_historicos.py.

Uso:
    python scripts/setup_eventos_historicos_oracle.py
    python scripts/setup_eventos_historicos_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "GOLD_EVENTOS_HISTORICOS": """
        CREATE TABLE ADMIN.GOLD_EVENTOS_HISTORICOS (
            ID                      VARCHAR2(50)   NOT NULL,
            FECHA_INICIO            DATE           NOT NULL,
            FECHA_FIN               DATE,
            NOMBRE                  VARCHAR2(200)  NOT NULL,
            DESCRIPCION             VARCHAR2(2000),
            VARIABLES_RELACIONADAS  VARCHAR2(500),
            FUENTE                  VARCHAR2(500),
            CREADO_EN               TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_EVENTOS_HISTORICOS PRIMARY KEY (ID)
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
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true",
                        help="Elimina y re-crea la tabla de eventos históricos")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    create_tables(recreate=args.recreate)
    print("\nSetup de GOLD_EVENTOS_HISTORICOS completado.")
