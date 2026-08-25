"""
scripts/setup_canacero_tables_oracle.py — Crea la tabla Oracle ADW del
pipeline CANACERO SICEP (comercio exterior nacional por fracción arancelaria,
"Base de datos tradicional"). Correr una sola vez.

Tabla creada:
  BRONZE_CANACERO_COMEX — 1 fila por (periodo_mes, movimiento, fracción).
  A diferencia de SNICE (miles de avisos/mes), CANACERO da ~900 fracciones
  por archivo: no hay retención ni tablas GOLD separadas, se agrega en vivo
  desde esta única tabla (ver mercado/canacero/loaders.py).

Uso:
    python scripts/setup_canacero_tables_oracle.py
    python scripts/setup_canacero_tables_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "BRONZE_CANACERO_COMEX": """
        CREATE TABLE ADMIN.BRONZE_CANACERO_COMEX (
            ANIO                   NUMBER(4)     NOT NULL,
            MES                    NUMBER(2)     NOT NULL,
            PERIODO_MES            VARCHAR2(7)   NOT NULL,
            MOVIMIENTO             VARCHAR2(20)  NOT NULL,
            FRACCION_ARANCELARIA   VARCHAR2(20)  NOT NULL,
            DESCRIPCION            VARCHAR2(500),
            CATEGORIA              VARCHAR2(200),
            VOLUMEN_TON            NUMBER,
            VALOR_USD              NUMBER,
            ARCHIVO_ORIGEN         VARCHAR2(200),
            FECHA_CARGA            TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_CANACERO_COMEX PRIMARY KEY (PERIODO_MES, MOVIMIENTO, FRACCION_ARANCELARIA)
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
                if "ORA-00955" in str(e):  # nombre ya existe
                    print(f"  {name} ya existe, se omite")
                else:
                    raise
        cursor.execute(
            "CREATE INDEX IDX_CANACERO_FRACCION ON ADMIN.BRONZE_CANACERO_COMEX (FRACCION_ARANCELARIA)"
        )
        conn.commit()
        print("  CREATE INDEX IDX_CANACERO_FRACCION")
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
                        help="Elimina y re-crea la tabla CANACERO")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    create_tables(recreate=args.recreate)
    print("\nSetup de tabla CANACERO completado.")
