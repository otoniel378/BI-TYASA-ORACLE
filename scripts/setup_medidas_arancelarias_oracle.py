"""
scripts/setup_medidas_arancelarias_oracle.py — Crea ADMIN.GOLD_MEDIDAS_ARANCELARIAS,
donde scripts/monitor_dof.py registra cada medida arancelaria concreta que Gemini
extrae de un decreto del DOF (arancel general, cuota compensatoria/antidumping,
exención/régimen especial tipo Regla 8a, o preferencia de TLC), una fila por
fracción afectada. A diferencia de GOLD_ALERTAS_DOF (1 fila por publicación del
DOF, solo lo relevante para TYASA), esta tabla es 1 fila por fracción+medida,
de CUALQUIER fracción de los capítulos 72/73 (no solo las de TYASA) — para poder
armar el historial completo "qué le pasó al arancel de la fracción X y cuándo".

Uso:
    python scripts/setup_medidas_arancelarias_oracle.py
    python scripts/setup_medidas_arancelarias_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLE_DDL = """
    CREATE TABLE ADMIN.GOLD_MEDIDAS_ARANCELARIAS (
        CODIGO_DOF       VARCHAR2(20)   NOT NULL,
        FRACCION         VARCHAR2(10)   NOT NULL,
        ES_FRACCION_TYASA NUMBER(1)     DEFAULT 0,
        TIPO_MEDIDA      VARCHAR2(60),
        VALOR            VARCHAR2(500),
        PAIS_ORIGEN      VARCHAR2(100),
        VIGENCIA_DESDE   VARCHAR2(20),
        VIGENCIA_HASTA   VARCHAR2(20),
        FECHA_DOF        VARCHAR2(10),
        URL              VARCHAR2(500),
        REGISTRADO_EN    TIMESTAMP DEFAULT SYSTIMESTAMP,
        CONSTRAINT PK_MEDIDAS_ARANCELARIAS PRIMARY KEY (CODIGO_DOF, FRACCION)
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
                cursor.execute("DROP TABLE ADMIN.GOLD_MEDIDAS_ARANCELARIAS")
            except oracledb.DatabaseError:
                pass
        try:
            cursor.execute(TABLE_DDL.strip())
            conn.commit()
            print("  CREATE GOLD_MEDIDAS_ARANCELARIAS")
        except oracledb.DatabaseError as e:
            if "ORA-00955" in str(e):
                print("  GOLD_MEDIDAS_ARANCELARIAS ya existe, se omite")
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
    print("\nSetup de medidas arancelarias completado.")
