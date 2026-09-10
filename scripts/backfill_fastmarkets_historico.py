"""
scripts/backfill_fastmarkets_historico.py — Carga puntual (uso único, no se
integra a la app) de los históricos/pronósticos de Fastmarkets descargados a
mano por el usuario en C:\\Users\\OTONIEL\\Fastmarket (38 archivos .xlsx, ver
mercado_fastmarkets/parser.py para el detalle de los layouts reales).

Idempotente por MERGE en (SYMBOL, FECHA, MEDIDA) — así los duplicados reales
(ej. "SCRAP SBQ", exportado dos veces con casi el mismo rango de fechas) no
duplican filas, y correr esto de nuevo tampoco.

Uso:
    python scripts/backfill_fastmarkets_historico.py
    python scripts/backfill_fastmarkets_historico.py --carpeta "C:\\otra\\ruta"
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

from mercado_fastmarkets.parser import parsear_archivo

load_dotenv()

CARPETA_DEFAULT = r"C:\Users\OTONIEL\Fastmarket"
TAMANO_LOTE = 1000

MERGE_SQL = """
    MERGE INTO ADMIN.BRONZE_FASTMARKETS_PRECIOS t
    USING (SELECT :symbol AS SYMBOL, :fecha AS FECHA, :medida AS MEDIDA FROM dual) s
    ON (t.SYMBOL = s.SYMBOL AND t.FECHA = s.FECHA AND t.MEDIDA = s.MEDIDA)
    WHEN MATCHED THEN UPDATE SET
        DESCRIPCION = :descripcion, TITULO_WIDGET = :titulo_widget,
        VALOR = :valor, TIPO = :tipo, ARCHIVO_ORIGEN = :archivo_origen
    WHEN NOT MATCHED THEN INSERT
        (SYMBOL, DESCRIPCION, TITULO_WIDGET, FECHA, MEDIDA, VALOR, TIPO, ARCHIVO_ORIGEN)
        VALUES (:symbol, :descripcion, :titulo_widget, :fecha, :medida, :valor, :tipo, :archivo_origen)
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


def _cargar_lote(cursor, filas: list) -> None:
    binds = [
        {
            "symbol": f["symbol"], "descripcion": f["descripcion"],
            "titulo_widget": f["titulo_widget"], "fecha": f["fecha"],
            "medida": f["medida"], "valor": f["valor"], "tipo": f["tipo"],
            "archivo_origen": f["archivo_origen"],
        }
        for f in filas
    ]
    cursor.executemany(MERGE_SQL, binds)


def main(carpeta: str) -> None:
    rutas = sorted(glob.glob(os.path.join(carpeta, "*.xlsx")))
    if not rutas:
        print(f"No se encontraron archivos .xlsx en {carpeta}")
        return

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")

    total_filas = 0
    omitidos = []

    try:
        for ruta in rutas:
            nombre = os.path.basename(ruta)
            try:
                filas, motivo = parsear_archivo(ruta)
            except Exception as e:
                omitidos.append((nombre, f"Error al leer: {e}"))
                print(f"  ERROR {nombre}: {e}")
                continue

            if motivo:
                omitidos.append((nombre, motivo))
                print(f"  OMITIDO {nombre}: {motivo}")
                continue

            for i in range(0, len(filas), TAMANO_LOTE):
                lote = filas[i:i + TAMANO_LOTE]
                _cargar_lote(cursor, lote)
                conn.commit()

            total_filas += len(filas)
            print(f"  OK {nombre}: {len(filas)} filas")

        print(f"\n{len(rutas)} archivos procesados, {total_filas} filas cargadas.")
        if omitidos:
            print(f"\n{len(omitidos)} archivos omitidos:")
            for nombre, motivo in omitidos:
                print(f"  - {nombre}: {motivo}")
        else:
            print("Ningún archivo omitido.")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--carpeta", default=CARPETA_DEFAULT,
                        help="Carpeta con los .xlsx de Fastmarkets")
    args = parser.parse_args()
    main(args.carpeta)
