"""
scripts/cargar_tigie_base_oracle.py — Carga/actualiza ADMIN.GOLD_TIGIE_BASE: el
arancel general (IGI = Impuesto General de Importación, IGE = de Exportación)
por fracción arancelaria de los capítulos 72 y 73 (fundición/hierro/acero y sus
manufacturas), tal como lo publica SNICE en su edición completa más reciente
de la TIGIE.

Es la "foto base" (capa 1) del historial de aranceles que arma TYASA BI — las
capas 2+ (cuotas compensatorias, exenciones tipo Regla 8a, TLC) se registran
aparte en ADMIN.GOLD_MEDIDAS_ARANCELARIAS a partir de lo que detecta
scripts/monitor_dof.py en el Diario Oficial (ver dof_monitor.py).

Fuente: directorio público de SNICE (snice.gob.mx/~oracle/SNICE_DOCS/), el
archivo "TIGIE completa" con fecha más reciente en el nombre. Confirmado
2026-11-25 que la edición vigente en ese directorio es TIGIE-MAYO24
(29-may-2024) — anterior a hoy, así que es un PISO de referencia, no
necesariamente el arancel exacto vigente; usar junto con GOLD_MEDIDAS_ARANCELARIAS
para lo que haya cambiado desde esa fecha.

Este script NO corre automático (no es parte del workflow de GH Actions) — se
re-ejecuta a mano cuando SNICE publique una edición más nueva (ocurre 1-2 veces
al año). Para refrescar: cambiar TIGIE_URL abajo por el archivo más reciente
listado en https://www.snice.gob.mx/~oracle/SNICE_DOCS/ (buscar "TIGIE" +
"completa"/"vigente", ordenar por fecha de modificación).

Uso:
  python scripts/cargar_tigie_base_oracle.py
"""

import io
import os
import re
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import oracledb
import requests
from dotenv import load_dotenv

load_dotenv()

from scripts.fracciones_tyasa import es_fraccion_tyasa, linea_tyasa

TIGIE_URL = "https://www.snice.gob.mx/~oracle/SNICE_DOCS/TIGIE-MAYO24-TIGIE_20240529-20240529.XLSX"
FUENTE_FECHA = "29/05/2024"
CAPITULOS = ("72", "73")

_FRACCION_PARTIDA_RE = re.compile(r"^(\d{2})\.\d{2}$")
_FRACCION_HOJA_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$")


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


def _descargar_xlsx() -> bytes:
    resp = requests.get(TIGIE_URL, timeout=60)
    resp.raise_for_status()
    return resp.content


def _extraer_fracciones(contenido: bytes) -> list[dict]:
    """Extrae las fracciones de 8 dígitos (hoja del catálogo, con IGI/IGE) de
    los capítulos 72/73. Una fracción puede tener varias filas (una por NICO) —
    se queda con la primera (la tasa IGI/IGE es la misma fracción a fracción,
    el NICO solo distingue variantes para fines estadísticos)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True)
    ws = wb["TIGIE + NICO"]

    en_capitulo = False
    unidad_actual = None
    vistos: dict[str, dict] = {}

    for row in ws.iter_rows(values_only=True):
        frac = row[1]
        if frac is None:
            continue
        fs = str(frac).strip()

        m_partida = _FRACCION_PARTIDA_RE.fullmatch(fs)
        if m_partida:
            en_capitulo = m_partida.group(1) in CAPITULOS
            continue
        if not en_capitulo:
            continue

        m_hoja = _FRACCION_HOJA_RE.fullmatch(fs)
        if not m_hoja:
            continue

        fraccion = "".join(m_hoja.groups())
        unidad = row[6] or unidad_actual
        unidad_actual = unidad  # algunas filas de NICO repiten fracción sin unidad propia
        if fraccion in vistos:
            continue
        vistos[fraccion] = {
            "fraccion": fraccion,
            "nico": row[2],
            "descripcion": (row[3] or "").strip(),
            "unidad_medida": unidad,
            "igi": str(row[7]).strip() if row[7] is not None else "",
            "ige": str(row[8]).strip() if row[8] is not None else "",
        }
    return list(vistos.values())


def _guardar(conn: oracledb.Connection, fracciones: list[dict]) -> int:
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
        rows = [
            {
                "fraccion": f["fraccion"],
                "nico": f["nico"],
                "descripcion": f["descripcion"][:500],
                "unidad_medida": (f["unidad_medida"] or "")[:10],
                "igi": f["igi"][:20],
                "ige": f["ige"][:20],
                "es_tyasa": 1 if es_fraccion_tyasa(f["fraccion"]) else 0,
                "linea": linea_tyasa(f["fraccion"])[:40],
                "fuente_fecha": FUENTE_FECHA,
            }
            for f in fracciones
        ]
        cursor.executemany(
            """
            MERGE INTO ADMIN.GOLD_TIGIE_BASE T
            USING (SELECT :fraccion AS FRACCION FROM dual) S
            ON (T.FRACCION = S.FRACCION)
            WHEN MATCHED THEN UPDATE SET
                NICO = :nico, DESCRIPCION = :descripcion, UNIDAD_MEDIDA = :unidad_medida,
                IGI = :igi, IGE = :ige, ES_FRACCION_TYASA = :es_tyasa,
                LINEA_TYASA = :linea, FUENTE_FECHA = :fuente_fecha
            WHEN NOT MATCHED THEN INSERT
                (FRACCION, NICO, DESCRIPCION, UNIDAD_MEDIDA, IGI, IGE,
                 ES_FRACCION_TYASA, LINEA_TYASA, FUENTE_FECHA)
            VALUES
                (:fraccion, :nico, :descripcion, :unidad_medida, :igi, :ige,
                 :es_tyasa, :linea, :fuente_fecha)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        cursor.close()


def run():
    print(f"Descargando TIGIE completa ({FUENTE_FECHA}) de SNICE...")
    contenido = _descargar_xlsx()
    print(f"  {len(contenido):,} bytes")

    print("Extrayendo fracciones de capítulos 72/73...")
    fracciones = _extraer_fracciones(contenido)
    n_tyasa = sum(1 for f in fracciones if es_fraccion_tyasa(f["fraccion"]))
    print(f"  {len(fracciones)} fracciones ({n_tyasa} son de TYASA)")

    print("Guardando en Oracle ADW...")
    conn = get_conn()
    try:
        n = _guardar(conn, fracciones)
        print(f"  {n} filas guardadas/actualizadas en GOLD_TIGIE_BASE")
    finally:
        conn.close()

    print("\nLISTO")


if __name__ == "__main__":
    run()
