"""
scripts/load_snice_to_oracle.py — Carga el Excel SNICE Siderúrgico más reciente
(hoja AVISOS_AUTORIZADOS, avisos automáticos de importación) a Oracle ADW:
detalle en BRONZE_SNICE_SIDERURGICO + recálculo de las 4 tablas GOLD para ese
periodo. Idempotente: si el periodo ya existía, lo reemplaza en vez de duplicar.

Requiere las tablas creadas por setup_snice_tables_oracle.py.

Uso:
    python scripts/load_snice_to_oracle.py
    python scripts/load_snice_to_oracle.py --file data/snice/siderurgico_2026-05.xlsx
    python scripts/load_snice_to_oracle.py --dir data/snice_historico --all   # backfill masivo
"""

import argparse
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import openpyxl
import oracledb
from dotenv import load_dotenv

from tigie_partidas import categoria_de, FRACCIONES_NO_KG
from download_snice_siderurgico import extraer_periodo_reportado

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


def _todos_los_archivos(dir_path: Path) -> list[Path]:
    archivos = sorted(dir_path.glob("*.xlsx"))
    if not archivos:
        raise FileNotFoundError(f"Sin archivos .xlsx en {dir_path}")
    return archivos


def _periodo_de(path: Path) -> str:
    """Detecta el periodo: primero por nombre de archivo (rápido, cubre el
    flujo automático siderurgico_YYYY-MM.xlsx); si no matchea, cae a leer la
    celda 'PERIODO REPORTADO' del propio Excel (cubre archivos descargados a
    mano del portal SNICE, con el nombre que trae de ahí)."""
    m = re.search(r"siderurgico_(\d{4}-\d{2})\.xlsx$", path.name)
    if m:
        return m.group(1)
    return extraer_periodo_reportado(path)


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

            fraccion_str = str(fraccion) if fraccion else None
            categoria, subcategoria = categoria_de(fraccion_str) if fraccion_str else (None, None)
            if fraccion_str and fraccion_str[:6] in FRACCIONES_NO_KG:
                print(f"  ADVERTENCIA: fracción {fraccion_str} (folio {folio}) no está en Kg "
                      f"(es 'Pza') — su VOLUMEN_AVISO no es comparable con el resto, revisar antes de sumar.")

            rows.append((
                str(folio)[:50] if folio else None,
                str(razon_social)[:300] if razon_social else None,
                _parse_fecha(fecha_tramite, con_hora=True),
                float(volumen) if isinstance(volumen, (int, float)) else None,
                fraccion_str[:20] if fraccion_str else None,
                _truncar_bytes(str(descripcion)) if descripcion else None,
                str(pais_origen)[:150] if pais_origen else None,
                str(pais_exportador)[:150] if pais_exportador else None,
                str(numero_aviso)[:50] if numero_aviso else None,
                _parse_fecha(fecha_resolucion, con_hora=True),
                _parse_fecha(inicio_vigencia, con_hora=False),
                _parse_fecha(fin_vigencia, con_hora=False),
                categoria,
                subcategoria,
                periodo,
            ))
        return rows
    finally:
        wb.close()


def cargar_bronze(rows: list, periodo: str, aplicar_retencion: bool = True):
    """Reemplaza el detalle de <periodo> en BRONZE. Si <aplicar_retencion> es
    False, no purga periodos viejos todavía (para no insertar-y-borrar en
    cada iteración de un backfill masivo) — llamar aplicar_retencion_bronze()
    una sola vez al final en ese caso."""
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
                INICIO_VIGENCIA, FIN_VIGENCIA, CATEGORIA_PRODUCTO, SUBCATEGORIA, PERIODO
            ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,:14,:15)
        """
        n_batches = math.ceil(len(rows) / INSERT_BATCH)
        for i in range(n_batches):
            cursor.executemany(insert_sql, rows[i * INSERT_BATCH:(i + 1) * INSERT_BATCH])
            conn.commit()
        print(f"  OK {len(rows):,} avisos en BRONZE_SNICE_SIDERURGICO (periodo {periodo})")
    finally:
        cursor.close()
        conn.close()

    if aplicar_retencion:
        aplicar_retencion_bronze()


def aplicar_retencion_bronze():
    """Conserva solo los PERIODOS_A_CONSERVAR periodos más recientes en
    BRONZE (el histórico agregado vive en las tablas GOLD, que nunca se
    purgan — ver recalcular_gold())."""
    conn = get_conn()
    cursor = conn.cursor()
    try:
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
            "GOLD_SNICE_TOP_PAISES", "GOLD_SNICE_TOP_FRACCIONES", "GOLD_SNICE_TOP_CATEGORIAS",
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

        cursor.execute("""
            INSERT INTO ADMIN.GOLD_SNICE_TOP_CATEGORIAS
                (PERIODO, PARTIDA, CATEGORIA_PRODUCTO, SUBCATEGORIA, VOLUMEN_TOTAL, AVISOS, EMPRESAS_DISTINTAS)
            SELECT PERIODO, SUBSTR(FRACCION_ARANCELARIA, 1, 4),
                   MIN(CATEGORIA_PRODUCTO), MIN(SUBCATEGORIA),
                   SUM(VOLUMEN_AVISO), COUNT(*), COUNT(DISTINCT RAZON_SOCIAL)
            FROM ADMIN.BRONZE_SNICE_SIDERURGICO
            WHERE PERIODO = :1 AND FRACCION_ARANCELARIA IS NOT NULL
            GROUP BY PERIODO, SUBSTR(FRACCION_ARANCELARIA, 1, 4)
        """, [periodo])

        conn.commit()
        print(f"  OK tablas GOLD recalculadas para periodo {periodo}")
    finally:
        cursor.close()
        conn.close()


def _cargar_un_archivo(xlsx_path: Path, aplicar_retencion: bool) -> str:
    periodo = _periodo_de(xlsx_path)
    print(f"Cargando {xlsx_path.name} (periodo {periodo}) a Oracle ADW...")
    rows = _leer_avisos(xlsx_path, periodo)
    if not rows:
        print("  Sin filas para cargar, se omite.")
        return periodo
    print(f"  {len(rows):,} avisos leídos")
    cargar_bronze(rows, periodo, aplicar_retencion=aplicar_retencion)
    recalcular_gold(periodo)
    return periodo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Ruta al xlsx a cargar (default: el más reciente en data/snice/)")
    parser.add_argument("--dir", default="data/snice", help="Carpeta con los archivos xlsx")
    parser.add_argument(
        "--all", action="store_true",
        help="Backfill: procesa TODOS los .xlsx de --dir (no solo el más reciente), "
             "detectando el periodo por el nombre o, si no matchea, por el contenido "
             "del Excel — para archivos descargados a mano del portal SNICE. La "
             "retención de BRONZE se aplica una sola vez al final, no por archivo.",
    )
    args = parser.parse_args()

    if args.all:
        archivos = _todos_los_archivos(Path(args.dir))
        print(f"Backfill: {len(archivos)} archivos encontrados en {args.dir}\n")
        cargados, fallidos = [], []
        for xlsx_path in archivos:
            try:
                periodo = _cargar_un_archivo(xlsx_path, aplicar_retencion=False)
                cargados.append(periodo)
            except Exception as e:
                print(f"  ERROR con {xlsx_path.name}: {e}")
                fallidos.append(xlsx_path.name)
            print()

        print("Aplicando retención de BRONZE (una sola vez, al final del backfill)...")
        aplicar_retencion_bronze()

        print(f"\nBackfill completado: {len(cargados)} periodos cargados, {len(fallidos)} fallidos.")
        if fallidos:
            print("Archivos con error:", ", ".join(fallidos))
            sys.exit(1)
        return

    xlsx_path = Path(args.file) if args.file else _ultimo_archivo(Path(args.dir))
    _cargar_un_archivo(xlsx_path, aplicar_retencion=True)
    print("\nCarga SNICE completada.")


if __name__ == "__main__":
    main()
