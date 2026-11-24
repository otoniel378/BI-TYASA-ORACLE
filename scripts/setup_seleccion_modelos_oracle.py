"""
scripts/setup_seleccion_modelos_oracle.py — Crea GOLD_SELECCION_MODELO: el
modelo que usa el modo Automático de los pronósticos para cada serie, elegido
con la validación de origen móvil. La llena scripts/update_seleccion_modelos.py
y la lee core/seleccion_modelos.py.

  SERIE_ID  — p. ej. NEGROS|TOTAL, NEGROS|PROCESO|<proceso>, NEGROS|PRODUCTO|<producto>,
              CANACERO|IMPORTACION|TOTAL, CANACERO|IMPORTACION|FRACCION|<fracción>
  FIRMA     — último mes | meses | total de la serie (forecasting.firma_serie);
              si los datos cambian, la selección deja de aplicar.
  MODELO    — clave del modelo (combo, ets, sarima, xgb, naive)
  WAPE      — error del modelo elegido (todos los horizontes, %)
  DETALLE   — WAPE de cada modelo, p. ej. "combo: 28% | sarima: 34% | ..."

Uso:
    python scripts/setup_seleccion_modelos_oracle.py
    python scripts/setup_seleccion_modelos_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

DDL = """
    CREATE TABLE ADMIN.GOLD_SELECCION_MODELO (
        SERIE_ID      VARCHAR2(200)  NOT NULL,
        FIRMA         VARCHAR2(60)   NOT NULL,
        MODELO        VARCHAR2(20)   NOT NULL,
        WAPE          NUMBER(8,2),
        DETALLE       VARCHAR2(400),
        CALCULADO_EN  TIMESTAMP DEFAULT SYSTIMESTAMP,
        CONSTRAINT PK_SELECCION_MODELO PRIMARY KEY (SERIE_ID)
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
                cursor.execute("DROP TABLE ADMIN.GOLD_SELECCION_MODELO")
            except oracledb.DatabaseError:
                pass
        try:
            cursor.execute(DDL.strip())
            conn.commit()
            print("  CREATE GOLD_SELECCION_MODELO")
        except oracledb.DatabaseError as e:
            if "ORA-00955" in str(e):
                print("  GOLD_SELECCION_MODELO ya existe, se omite")
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
