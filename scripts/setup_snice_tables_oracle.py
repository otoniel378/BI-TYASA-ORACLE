"""
scripts/setup_snice_tables_oracle.py — Crea las tablas Oracle ADW del pipeline
SNICE Siderúrgico (avisos automáticos de importación). Correr una sola vez.

Tablas creadas:
  BRONZE_SNICE_SIDERURGICO   — 1 fila por aviso (detalle). Solo se conservan
                                los últimos 2 periodos (ver load_snice_to_oracle.py);
                                el histórico agregado vive en las tablas GOLD.
  GOLD_SNICE_RESUMEN_MENSUAL — 1 fila por periodo: totales generales
  GOLD_SNICE_TOP_EMPRESAS    — 1 fila por periodo + empresa (razón social)
  GOLD_SNICE_TOP_PAISES      — 1 fila por periodo + país de origen
  GOLD_SNICE_TOP_FRACCIONES  — 1 fila por periodo + fracción arancelaria

Las 4 tablas GOLD nunca se purgan (crecen ~poco cada mes) — son la base para
series de tiempo/tendencias en la plataforma aunque el detalle en BRONZE ya
se haya borrado.

Uso:
    python scripts/setup_snice_tables_oracle.py
    python scripts/setup_snice_tables_oracle.py --recreate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

TABLES_DDL = {
    "BRONZE_SNICE_SIDERURGICO": """
        CREATE TABLE ADMIN.BRONZE_SNICE_SIDERURGICO (
            FOLIO_TRAMITE          VARCHAR2(50),
            RAZON_SOCIAL           VARCHAR2(300),
            FECHA_TRAMITE          DATE,
            VOLUMEN_AVISO          NUMBER,
            FRACCION_ARANCELARIA   VARCHAR2(20),
            DESCRIPCION_MERCANCIA  VARCHAR2(4000),
            PAIS_ORIGEN            VARCHAR2(150),
            PAIS_EXPORTADOR        VARCHAR2(150),
            NUMERO_AVISO           VARCHAR2(50),
            FECHA_RESOLUCION       DATE,
            INICIO_VIGENCIA        DATE,
            FIN_VIGENCIA           DATE,
            PERIODO                VARCHAR2(7)   NOT NULL,
            FECHA_CARGA            TIMESTAMP     DEFAULT SYSTIMESTAMP
        )
    """,
    "GOLD_SNICE_RESUMEN_MENSUAL": """
        CREATE TABLE ADMIN.GOLD_SNICE_RESUMEN_MENSUAL (
            PERIODO               VARCHAR2(7)  NOT NULL,
            VOLUMEN_TOTAL          NUMBER,
            AVISOS_TOTAL            NUMBER,
            EMPRESAS_DISTINTAS      NUMBER,
            PAISES_DISTINTOS        NUMBER,
            FRACCIONES_DISTINTAS    NUMBER,
            FECHA_CARGA             TIMESTAMP DEFAULT SYSTIMESTAMP,
            CONSTRAINT PK_SNICE_RESUMEN PRIMARY KEY (PERIODO)
        )
    """,
    "GOLD_SNICE_TOP_EMPRESAS": """
        CREATE TABLE ADMIN.GOLD_SNICE_TOP_EMPRESAS (
            PERIODO              VARCHAR2(7)   NOT NULL,
            RAZON_SOCIAL          VARCHAR2(300) NOT NULL,
            VOLUMEN_TOTAL         NUMBER,
            AVISOS                NUMBER,
            FRACCIONES_DISTINTAS  NUMBER,
            PAISES_DISTINTOS      NUMBER,
            CONSTRAINT PK_SNICE_EMPRESAS PRIMARY KEY (PERIODO, RAZON_SOCIAL)
        )
    """,
    "GOLD_SNICE_TOP_PAISES": """
        CREATE TABLE ADMIN.GOLD_SNICE_TOP_PAISES (
            PERIODO             VARCHAR2(7)   NOT NULL,
            PAIS_ORIGEN          VARCHAR2(150) NOT NULL,
            VOLUMEN_TOTAL        NUMBER,
            AVISOS               NUMBER,
            EMPRESAS_DISTINTAS   NUMBER,
            CONSTRAINT PK_SNICE_PAISES PRIMARY KEY (PERIODO, PAIS_ORIGEN)
        )
    """,
    "GOLD_SNICE_TOP_FRACCIONES": """
        CREATE TABLE ADMIN.GOLD_SNICE_TOP_FRACCIONES (
            PERIODO              VARCHAR2(7)  NOT NULL,
            FRACCION_ARANCELARIA  VARCHAR2(20) NOT NULL,
            VOLUMEN_TOTAL         NUMBER,
            AVISOS                NUMBER,
            EMPRESAS_DISTINTAS    NUMBER,
            CONSTRAINT PK_SNICE_FRACCIONES PRIMARY KEY (PERIODO, FRACCION_ARANCELARIA)
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
            "CREATE INDEX IDX_SNICE_BRONZE_PERIODO ON ADMIN.BRONZE_SNICE_SIDERURGICO (PERIODO)"
        )
        conn.commit()
        print("  CREATE INDEX IDX_SNICE_BRONZE_PERIODO")
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
                        help="Elimina y re-crea las tablas SNICE")
    args = parser.parse_args()

    print("Conectando a Oracle ADW...")
    create_tables(recreate=args.recreate)
    print("\nSetup de tablas SNICE completado.")
    print("Siguiente: python scripts/load_snice_to_oracle.py")
