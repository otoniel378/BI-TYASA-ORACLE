"""
scripts/setup_semaforo_ferros_oracle.py — Crea las tablas del semáforo de
alerta de alzas en ferroaleaciones (mercado_fastmarkets/alerta_alzas.py), que
llena scripts/update_semaforo_ferros.py y lee
pages/mercado/09_quiebres_ferroaleaciones.py.

  GOLD_SEMAFORO_FERROS   — probabilidad de alza por (serie, mes): TIPO
                           'backtest' = validación hacia adelante (histórico),
                           'actual'   = último mes con el modelo entrenado con todo.
  GOLD_SEMAFORO_METRICAS — qué tan bien acertó el modelo en la validación, por serie.

Uso:
    python scripts/setup_semaforo_ferros_oracle.py
    python scripts/setup_semaforo_ferros_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "GOLD_SEMAFORO_FERROS": """
        CREATE TABLE ADMIN.GOLD_SEMAFORO_FERROS (
            SERIE        VARCHAR2(50)  NOT NULL,
            FECHA        DATE          NOT NULL,
            TIPO         VARCHAR2(10)  NOT NULL,
            PROB         NUMBER(6,4),
            SEMAFORO     VARCHAR2(10),
            ALZA_FUT     NUMBER(10,4),
            Y            NUMBER(1),
            CARGADO_EN   TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_SEMAFORO_FERROS PRIMARY KEY (SERIE, FECHA, TIPO)
        )
    """,
    "GOLD_SEMAFORO_METRICAS": """
        CREATE TABLE ADMIN.GOLD_SEMAFORO_METRICAS (
            SERIE            VARCHAR2(50)  NOT NULL,
            EPISODIOS        NUMBER(5),
            DETECTADOS       NUMBER(5),
            PCT_DETECTADOS   NUMBER(6,4),
            FALSAS_POR_ANIO  NUMBER(8,4),
            ACIERTAN         NUMBER(6,4),
            AUC              NUMBER(6,4),
            PROB_BASE        NUMBER(6,4),
            CONFIABLE        NUMBER(1),
            ACTUALIZADO      TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_SEMAFORO_METRICAS PRIMARY KEY (SERIE)
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
    parser.add_argument("--recreate", action="store_true", help="Elimina y re-crea las tablas del semáforo")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    create_tables(recreate=args.recreate)
    print("\nSetup del semáforo de ferroaleaciones completado.")
