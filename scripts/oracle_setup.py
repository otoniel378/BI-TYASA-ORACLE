"""
oracle_setup.py — Crea todas las tablas en Oracle ADW (una sola vez).

Uso:
    python scripts/oracle_setup.py              # crea las tablas que no existen
    python scripts/oracle_setup.py --recreate   # elimina y re-crea todo
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import oracledb
from dotenv import load_dotenv

load_dotenv()

# ── Tablas en orden de creación (respeta dependencias) ───────────────────────

TABLES = {
    "BRONZE_VENTAS_RAW": """
        CREATE TABLE ADMIN.BRONZE_VENTAS_RAW (
            FECHAEMB        DATE,
            FHEMBARQUE      DATE,
            CVECLIENTE      VARCHAR2(50),
            CLIENTE         VARCHAR2(200),
            PEDIDO          VARCHAR2(50),
            POSICION        VARCHAR2(20),
            CVESAP          VARCHAR2(100),
            EMBARQUE        VARCHAR2(50),
            REMISION        VARCHAR2(50),
            PLACAS          VARCHAR2(50),
            CVEMAT_PROD     VARCHAR2(50),
            PRODUCTO        VARCHAR2(500),
            SECUENCIA       NUMBER,
            CALIBRE         NUMBER,
            ANCHO           NUMBER,
            PESO            NUMBER,
            COLADA          VARCHAR2(50),
            PIEZAS          NUMBER,
            LARGO           NUMBER,
            PARTE_CLIENTE   VARCHAR2(200),
            ESPESOR_REAL    NUMBER,
            ESPESOR         NUMBER,
            PESOBRUTO       NUMBER,
            NIV_CALIDAD     VARCHAR2(50),
            TARIMA          VARCHAR2(50),
            PROCESO         VARCHAR2(100)
        )
    """,

    "SILVER_VENTAS_LIMPIAS": """
        CREATE TABLE ADMIN.SILVER_VENTAS_LIMPIAS (
            FECHAEMB            DATE,
            CLIENTE             VARCHAR2(200),
            PRODUCTO_ORIGINAL   VARCHAR2(500),
            PRODUCTO_LIMPIO     VARCHAR2(500),
            PROCESO             VARCHAR2(100),
            CALIBRE             NUMBER,
            ANCHO               NUMBER,
            PESO_KG             NUMBER,
            PESO_TON            NUMBER,
            COLADA              VARCHAR2(50),
            PIEZAS              NUMBER,
            ANIO                NUMBER(4),
            MES                 NUMBER(2),
            PERIODO             DATE,
            AREA                VARCHAR2(50),
            DIVISION            VARCHAR2(50)
        )
    """,

    "GOLD_DEMANDA_CLIENTE": """
        CREATE TABLE ADMIN.GOLD_DEMANDA_CLIENTE (
            CLIENTE         VARCHAR2(200),
            AREA            VARCHAR2(50),
            DIVISION        VARCHAR2(50),
            PESO_TON        NUMBER,
            N_EMBARQUES     NUMBER,
            PRIMERA_COMPRA  DATE,
            ULTIMA_COMPRA   DATE
        )
    """,

    "GOLD_DEMANDA_PRODUCTO": """
        CREATE TABLE ADMIN.GOLD_DEMANDA_PRODUCTO (
            PRODUCTO_LIMPIO VARCHAR2(500),
            AREA            VARCHAR2(50),
            DIVISION        VARCHAR2(50),
            PESO_TON        NUMBER,
            N_CLIENTES      NUMBER
        )
    """,

    "GOLD_DEMANDA_MENSUAL": """
        CREATE TABLE ADMIN.GOLD_DEMANDA_MENSUAL (
            PERIODO         DATE,
            ANIO            NUMBER(4),
            MES             NUMBER(2),
            PRODUCTO_LIMPIO VARCHAR2(500),
            AREA            VARCHAR2(50),
            DIVISION        VARCHAR2(50),
            PESO_TON        NUMBER,
            N_CLIENTES      NUMBER,
            N_EMBARQUES     NUMBER
        )
    """,

    "GOLD_CLIENTE_PRODUCTO": """
        CREATE TABLE ADMIN.GOLD_CLIENTE_PRODUCTO (
            CLIENTE         VARCHAR2(200),
            PRODUCTO_LIMPIO VARCHAR2(500),
            AREA            VARCHAR2(50),
            DIVISION        VARCHAR2(50),
            PESO_TON        NUMBER,
            N_EMBARQUES     NUMBER
        )
    """,

    "GOLD_DEMANDA_PROCESO": """
        CREATE TABLE ADMIN.GOLD_DEMANDA_PROCESO (
            PROCESO         VARCHAR2(100),
            AREA            VARCHAR2(50),
            DIVISION        VARCHAR2(50),
            PESO_TON        NUMBER,
            N_CLIENTES      NUMBER,
            N_EMBARQUES     NUMBER
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


def drop_table(cursor, name: str):
    try:
        cursor.execute(f"DROP TABLE ADMIN.{name}")
        print(f"  DROP   {name}")
    except oracledb.DatabaseError:
        pass  # tabla no existía, no es error


def create_all(recreate: bool = False):
    print("Conectando a Oracle ADW...")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        for name, ddl in TABLES.items():
            if recreate:
                drop_table(cursor, name)
            cursor.execute(ddl.strip())
            conn.commit()
            print(f"  CREATE {name}")
        print("\nOK Todas las tablas creadas correctamente.")
    except oracledb.DatabaseError as e:
        conn.rollback()
        print(f"\nERROR Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crea las tablas de TYASA BI en Oracle ADW")
    parser.add_argument("--recreate", action="store_true",
                        help="Elimina y re-crea todas las tablas (borra datos)")
    args = parser.parse_args()

    if args.recreate:
        confirm = input("¿Confirmas eliminar y re-crear todas las tablas? (s/N): ")
        if confirm.lower() != "s":
            print("Cancelado.")
            sys.exit(0)

    create_all(recreate=args.recreate)
