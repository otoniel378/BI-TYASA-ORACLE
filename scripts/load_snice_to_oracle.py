"""
scripts/load_snice_to_oracle.py — Carga el Excel SNICE Siderúrgico más reciente
(hoja AVISOS_AUTORIZADOS, avisos automáticos de importación) a Oracle ADW:
detalle en BRONZE_SNICE_SIDERURGICO + recálculo de las 4 tablas GOLD para ese
periodo. Idempotente: si el periodo ya existía, lo reemplaza en vez de duplicar.

Requiere las tablas creadas por setup_snice_tables_oracle.py.

Uso:
    python scripts/load_snice_to_oracle.py
    python scripts/load_snice_to_oracle.py --file data/snice/siderurgico_2026-05.xlsx
"""

import argparse
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openpyxl
import oracledb
from dotenv import load_dotenv

load_dotenv()

HOJA = "AVISOS_AUTORIZADOS"
FILA_ENCABEZADO = 7  # 1-indexed: la fila 8 en adelante ya es data
PERIODOS_A_CONSERVAR = 2
INSERT_BATCH = 2000


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


def _ultimo_archivo(out_dir: Path) -> Path:
    archivos = sorted(out_dir.glob("siderurgico_*.xlsx"), reverse=True)
    if not archivos:
        raise FileNotFoundError(f"Sin archivos siderurgico_*.xlsx en {out_dir}")
    return archivos[0]


def _periodo_de(path: Path) -> str:
    m = re.search(r"siderurgico_(\d{4}-\d{2})\.xlsx$", path.name)
    if not m:
        raise ValueError(f"No se pudo determinar el periodo del nombre de archivo: {path.name}")
    return m.group(1)


def _truncar_bytes(texto: str, max_bytes: int = 3900) -> str:
    """Trunca por bytes UTF-8 (no por caracteres) para no pasarse del límite de la
    columna VARCHAR2(4000 byte) de Oracle con acentos/ñ multibyte."""
    b = texto.encode("utf-8")
    if len(b) <= max_bytes:
        return texto
    return b[:max_bytes].decode("utf-8", errors="ignore")


def _parse_fecha(val, con_hora=False):
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    fmt = "%d/%m/%Y %H:%M:%S" if con_hora else "%d/%m/%Y"
    try:
        return datetime.strptime(str(val).strip(), fmt)
    except ValueError:
        return None


def _leer_avisos(xlsx_path: Path, periodo: str) -> list:
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True)
    try:
        hoja = wb[HOJA]
        rows = []
        for r in hoja.iter_rows(min_row=FILA_ENCABEZADO + 1, values_only=True):
            if not r or not r[0]:
                continue
            (folio, razon_social, fecha_tramite, volumen, fraccion, descripcion,
             pais_origen, pais_exportador, numero_aviso, fecha_resolucion,
             inicio_vigencia, fin_vigencia) = r[:12]

            rows.append((
                str(folio)[:50] if folio else None,
                str(razon_social)[:300] if razon_social else None,
                _parse_fecha(fecha_tramite, con_hora=True),
                float(volumen) if isinstance(volumen, (int, float)) else None,
                str(fraccion)[:20] if fraccion else None,
                _truncar_bytes(str(descripcion)) if descripcion else None,
                str(pais_origen)[:150] if pais_origen else None,
                str(pais_exportador)[:150] if pais_exportador else None,
                str(numero_aviso)[:50] if numero_aviso else None,
                _parse_fecha(fecha_resolucion, con_hora=True),
                _parse_fecha(inicio_vigencia, con_hora=False),
                _parse_fecha(fin_vigencia, con_hora=False),
                periodo,
            ))
        return rows
    finally:
        wb.close()


def cargar_bronze(rows: list, periodo: str):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ADMIN.BRONZE_SNICE_SIDERURGICO WHERE PERIODO = :1", [periodo])
        conn.commit()

        insert_sql = """
            INSERT INTO ADMIN.BRONZE_SNICE_SIDERURGICO (
                FOLIO_TRAMITE, RAZON_SOCIAL, FECHA_TRAMITE, VOLUMEN_AVISO,
                FRACCION_ARANCELARIA, DESCRIPCION_MERCANCIA, PAIS_ORIGEN,
                PAIS_EXPORTADOR, NUMERO_AVISO, FECHA_RESOLUCION,
                INICIO_VIGENCIA, FIN_VIGENCIA, PERIODO
            ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13)
        """
        n_batches = math.ceil(len(rows) / INSERT_BATCH)
        for i in range(n_batches):
            cursor.executemany(insert_sql, rows[i * INSERT_BATCH:(i + 1) * INSERT_BATCH])
            conn.commit()
        print(f"  OK {len(rows):,} avisos en BRONZE_SNICE_SIDERURGICO (periodo {periodo})")

        # Retención: solo conservar los últimos N periodos de detalle
        cursor.execute("SELECT DISTINCT PERIODO FROM ADMIN.BRONZE_SNICE_SIDERURGICO ORDER BY PERIODO DESC")
        periodos = [r[0] for r in cursor.fetchall()]
        for p in periodos[PERIODOS_A_CONSERVAR:]:
            cursor.execute("DELETE FROM ADMIN.BRONZE_SNICE_SIDERURGICO WHERE PERIODO = :1", [p])
            conn.commit()
            print(f"  Retención: borrado periodo {p} de BRONZE (detalle histórico vive en GOLD)")
    finally:
        cursor.close()
        conn.close()


def recalcular_gold(periodo: str):
    """Recalcula las 4 tablas GOLD para <periodo> a partir del detalle en BRONZE.
    Las tablas GOLD nunca se purgan por retención: acumulan historial para
    series de tiempo aunque el detalle del periodo ya se haya borrado de BRONZE."""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        for tabla in (
            "GOLD_SNICE_RESUMEN_MENSUAL", "GOLD_SNICE_TOP_EMPRESAS",
            "GOLD_SNICE_TOP_PAISES", "GOLD_SNICE_TOP_FRACCIONES",
        ):
            cursor.execute(f"DELETE FROM ADMIN.{tabla} WHERE PERIODO = :1", [periodo])
        conn.commit()

        cursor.execute("""
            INSERT INTO ADMIN.GOLD_SNICE_RESUMEN_MENSUAL
                (PERIODO, VOLUMEN_TOTAL, AVISOS_TOTAL, EMPRESAS_DISTINTAS, PAISES_DISTINTOS, FRACCIONES_DISTINTAS)
            SELECT PERIODO, SUM(VOLUMEN_AVISO), COUNT(*),
                   COUNT(DISTINCT RAZON_SOCIAL), COUNT(DISTINCT PAIS_ORIGEN), COUNT(DISTINCT FRACCION_ARANCELARIA)
            FROM ADMIN.BRONZE_SNICE_SIDERURGICO
            WHERE PERIODO = :1
            GROUP BY PERIODO
        """, [periodo])

        cursor.execute("""
            INSERT INTO ADMIN.GOLD_SNICE_TOP_EMPRESAS
                (PERIODO, RAZON_SOCIAL, VOLUMEN_TOTAL, AVISOS, FRACCIONES_DISTINTAS, PAISES_DISTINTOS)
            SELECT PERIODO, RAZON_SOCIAL, SUM(VOLUMEN_AVISO), COUNT(*),
                   COUNT(DISTINCT FRACCION_ARANCELARIA), COUNT(DISTINCT PAIS_ORIGEN)
            FROM ADMIN.BRONZE_SNICE_SIDERURGICO
            WHERE PERIODO = :1 AND RAZON_SOCIAL IS NOT NULL
            GROUP BY PERIODO, RAZON_SOCIAL
        """, [periodo])

        cursor.execute("""
            INSERT INTO ADMIN.GOLD_SNICE_TOP_PAISES
                (PERIODO, PAIS_ORIGEN, VOLUMEN_TOTAL, AVISOS, EMPRESAS_DISTINTAS)
            SELECT PERIODO, PAIS_ORIGEN, SUM(VOLUMEN_AVISO), COUNT(*), COUNT(DISTINCT RAZON_SOCIAL)
            FROM ADMIN.BRONZE_SNICE_SIDERURGICO
            WHERE PERIODO = :1 AND PAIS_ORIGEN IS NOT NULL
            GROUP BY PERIODO, PAIS_ORIGEN
        """, [periodo])

        cursor.execute("""
            INSERT INTO ADMIN.GOLD_SNICE_TOP_FRACCIONES
                (PERIODO, FRACCION_ARANCELARIA, VOLUMEN_TOTAL, AVISOS, EMPRESAS_DISTINTAS)
            SELECT PERIODO, FRACCION_ARANCELARIA, SUM(VOLUMEN_AVISO), COUNT(*), COUNT(DISTINCT RAZON_SOCIAL)
            FROM ADMIN.BRONZE_SNICE_SIDERURGICO
            WHERE PERIODO = :1 AND FRACCION_ARANCELARIA IS NOT NULL
            GROUP BY PERIODO, FRACCION_ARANCELARIA
        """, [periodo])

        conn.commit()
        print(f"  OK tablas GOLD recalculadas para periodo {periodo}")
    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Ruta al xlsx a cargar (default: el más reciente en data/snice/)")
    parser.add_argument("--dir", default="data/snice", help="Carpeta con los archivos siderurgico_*.xlsx")
    args = parser.parse_args()

    xlsx_path = Path(args.file) if args.file else _ultimo_archivo(Path(args.dir))
    periodo = _periodo_de(xlsx_path)

    print(f"Cargando {xlsx_path.name} (periodo {periodo}) a Oracle ADW...")

    print("1. Leyendo avisos del Excel...")
    rows = _leer_avisos(xlsx_path, periodo)
    if not rows:
        print("Sin filas para cargar.")
        sys.exit(1)
    print(f"   {len(rows):,} avisos leídos")

    print("2. Cargando BRONZE_SNICE_SIDERURGICO...")
    cargar_bronze(rows, periodo)

    print("3. Recalculando tablas GOLD...")
    recalcular_gold(periodo)

    print("\nCarga SNICE completada.")


if __name__ == "__main__":
    main()
