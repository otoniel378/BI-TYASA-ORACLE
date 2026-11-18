"""
scripts/setup_memoria_ia_oracle.py — Crea la tabla de memoria del asistente IA
(core/memoria_ia.py): insights clave de las conversaciones del chat, que se
inyectan como contexto al iniciar cada sesión.

Uso (una sola vez):
    python scripts/setup_memoria_ia_oracle.py
    python scripts/setup_memoria_ia_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

DDL = """
    CREATE TABLE ADMIN.GOLD_MEMORIA_IA (
        ID_MEMORIA     VARCHAR2(20)   NOT NULL,
        FECHA          DATE,
        USUARIO        VARCHAR2(50),
        TIPO           VARCHAR2(30),
        TEMA           VARCHAR2(100),
        CONTENIDO      VARCHAR2(1000),
        RELEVANCIA     VARCHAR2(10),
        FUENTE_SESION  VARCHAR2(50),
        CARGADO_EN     TIMESTAMP DEFAULT SYSTIMESTAMP,
        CONSTRAINT PK_MEMORIA_IA PRIMARY KEY (ID_MEMORIA)
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


def main(recreate: bool = False):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if recreate:
            try:
                cursor.execute("DROP TABLE ADMIN.GOLD_MEMORIA_IA")
            except oracledb.DatabaseError:
                pass
        try:
            cursor.execute(DDL.strip())
            conn.commit()
            print("  CREATE GOLD_MEMORIA_IA")
        except oracledb.DatabaseError as e:
            if "ORA-00955" in str(e):
                print("  GOLD_MEMORIA_IA ya existe, se omite")
            else:
                raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true", help="Elimina y re-crea la tabla")
    args = ap.parse_args()
    print("Conectando a Oracle ADW...")
    main(recreate=args.recreate)
