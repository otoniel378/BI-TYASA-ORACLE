"""
transform_to_silver.py — Transforma BRONZE_VENTAS_RAW -> SILVER_VENTAS_LIMPIAS.

Limpieza aplicada:
  - CLIENTE, PROCESO y PRODUCTO_LIMPIO: TRIM + UPPER + espacios repetidos a uno
  - PESO_TON: PESO / 1000
  - PERIODO: primer día del mes de FECHAEMB
  - AREA = 'NEGROS', DIVISION = 'PLANOS' (todos los datos actuales)
  - Se excluyen filas sin FECHAEMB, sin CLIENTE o con PESO nulo o <= 0
  - Deduplicación por clave física del embarque (fecha, embarque, remisión,
    secuencia, colada, producto y peso): si el mismo archivo de SAP se carga
    dos veces en Bronce, cada bobina/paquete entra una sola vez a Plata
  - Al final imprime las métricas de calidad de la corrida (registros en
    Bronce, excluidos por regla, duplicados y productos antes/después)

Uso:
    python scripts/transform_to_silver.py
    python scripts/transform_to_silver.py --truncate
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import oracledb
from dotenv import load_dotenv

load_dotenv()

SQL_TRANSFORM = """
    INSERT INTO ADMIN.SILVER_VENTAS_LIMPIAS (
        FECHAEMB, CLIENTE, PRODUCTO_ORIGINAL, PRODUCTO_LIMPIO,
        PROCESO, CALIBRE, ANCHO, PESO_KG, PESO_TON,
        COLADA, PIEZAS, ANIO, MES, PERIODO, AREA, DIVISION
    )
    SELECT
        FECHAEMB,
        REGEXP_REPLACE(TRIM(UPPER(CLIENTE)),  ' {2,}', ' ') AS CLIENTE,
        PRODUCTO                                            AS PRODUCTO_ORIGINAL,
        REGEXP_REPLACE(TRIM(UPPER(PRODUCTO)), ' {2,}', ' ') AS PRODUCTO_LIMPIO,
        REGEXP_REPLACE(TRIM(UPPER(PROCESO)),  ' {2,}', ' ') AS PROCESO,
        CALIBRE,
        ANCHO,
        PESO                          AS PESO_KG,
        ROUND(PESO / 1000, 6)         AS PESO_TON,
        COLADA,
        PIEZAS,
        EXTRACT(YEAR  FROM FECHAEMB)  AS ANIO,
        EXTRACT(MONTH FROM FECHAEMB)  AS MES,
        TRUNC(FECHAEMB, 'MM')         AS PERIODO,
        'NEGROS'                      AS AREA,
        'PLANOS'                      AS DIVISION
    FROM (
        SELECT b.*,
               ROW_NUMBER() OVER (
                   PARTITION BY FECHAEMB, EMBARQUE, REMISION, SECUENCIA, COLADA, PRODUCTO, PESO
                   ORDER BY FHEMBARQUE
               ) AS RN
        FROM ADMIN.BRONZE_VENTAS_RAW b
        WHERE FECHAEMB IS NOT NULL
          AND CLIENTE  IS NOT NULL
          AND PESO     > 0
    )
    WHERE RN = 1
"""

# Métricas de calidad de la corrida (DAMA-DMBOK: completitud, validez, unicidad)
SQL_METRICAS = """
    SELECT
        COUNT(*)                                                    AS BRONCE,
        SUM(CASE WHEN FECHAEMB IS NULL THEN 1 ELSE 0 END)           AS SIN_FECHA,
        SUM(CASE WHEN CLIENTE  IS NULL THEN 1 ELSE 0 END)           AS SIN_CLIENTE,
        SUM(CASE WHEN PESO IS NULL OR PESO <= 0 THEN 1 ELSE 0 END)  AS PESO_INVALIDO,
        COUNT(DISTINCT PRODUCTO)                                    AS PRODUCTOS_ORIGINALES,
        (SELECT COUNT(DISTINCT PRODUCTO_LIMPIO) FROM ADMIN.SILVER_VENTAS_LIMPIAS) AS PRODUCTOS_LIMPIOS,
        (SELECT COUNT(*) FROM ADMIN.SILVER_VENTAS_LIMPIAS)          AS PLATA
    FROM ADMIN.BRONZE_VENTAS_RAW
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


def transform(truncate: bool = False):
    print("Conectando a Oracle ADW...")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if truncate:
            cursor.execute("TRUNCATE TABLE ADMIN.SILVER_VENTAS_LIMPIAS")
            conn.commit()
            print("  TRUNCATE SILVER_VENTAS_LIMPIAS")

        print("  Ejecutando transformación bronze -> silver...")
        cursor.execute(SQL_TRANSFORM)
        rows = cursor.rowcount
        conn.commit()
        print(f"\nOK {rows:,} filas insertadas en SILVER_VENTAS_LIMPIAS")

        cursor.execute(SQL_METRICAS)
        cols = [d[0] for d in cursor.description]
        m = dict(zip(cols, cursor.fetchone()))
        excluidos = m["SIN_FECHA"] + m["SIN_CLIENTE"] + m["PESO_INVALIDO"]
        duplicados = m["BRONCE"] - excluidos - m["PLATA"] if truncate else None
        print("\nMétricas de calidad de la corrida")
        print(f"  Registros en Bronce:          {m['BRONCE']:,}")
        print(f"  Sin fecha de embarque:        {m['SIN_FECHA']:,}")
        print(f"  Sin cliente:                  {m['SIN_CLIENTE']:,}")
        print(f"  Peso nulo o <= 0:             {m['PESO_INVALIDO']:,}")
        if duplicados is not None:
            print(f"  Duplicados eliminados:        {duplicados:,}")
        print(f"  Registros en Plata:           {m['PLATA']:,}")
        print(f"  Productos (original -> limpio): {m['PRODUCTOS_ORIGINALES']:,} -> {m['PRODUCTOS_LIMPIOS']:,}")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transforma bronze -> silver")
    parser.add_argument("--truncate", action="store_true",
                        help="Vacía silver antes de transformar (evita duplicados)")
    args = parser.parse_args()
    transform(truncate=args.truncate)
