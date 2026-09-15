"""
update_inegi_estado_data.py — Descarga indicadores INEGI desagregados por
entidad federativa y los carga en Oracle ADW.

A diferencia de update_inegi_data.py (indicadores nacionales), aquí la CLAVE
del indicador no cambia por estado: lo que cambia es el parámetro de área
geográfica en la URL de la API (00=nacional, 01-32=estados). Confirmado con
la API real que esta desagregación NO existe para IMAI/EMIM/IGAE/INPP/etc.
(national-only) pero SÍ existe para el valor de producción de ENEC.

Catálogo de indicadores por estado — se va ampliando conforme se detectan
más claves con desagregación estatal en el Banco de Indicadores de INEGI
(inegi.org.mx/app/indicadores/ → filtrar por Área geográfica = un estado y
ver si el indicador aparece con valores distintos al nacional).

Tabla destino: ADMIN.GOLD_INDICADORES_INEGI_ESTADO

Uso:
    python scripts/update_inegi_estado_data.py
    python scripts/update_inegi_estado_data.py --truncate   # limpia antes de insertar
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import math
import time
import requests
import oracledb
from dotenv import load_dotenv

load_dotenv()

INEGI_TOKEN = os.environ.get("INEGI_TOKEN", "")

# ── Indicadores con desagregación por entidad federativa ─────────────────────
INDICADORES_ESTADO = {
    "723135": "ENEC_ValorProdPesos_Sector23_Total",
}

# ── Catálogo de 32 estados: cve INEGI (01-32) -> (ISO 3166-2, nombre oficial) ─
# El ISO ("MX-AGU", etc.) es la clave con la que se hace match contra
# assets/mx_estados.geojson (properties.id) para dibujar el mapa.
ESTADOS = {
    "00": ("MX",     "Nacional"),
    "01": ("MX-AGU", "Aguascalientes"),
    "02": ("MX-BCN", "Baja California"),
    "03": ("MX-BCS", "Baja California Sur"),
    "04": ("MX-CAM", "Campeche"),
    "05": ("MX-COA", "Coahuila de Zaragoza"),
    "06": ("MX-COL", "Colima"),
    "07": ("MX-CHP", "Chiapas"),
    "08": ("MX-CHH", "Chihuahua"),
    "09": ("MX-CMX", "Ciudad de México"),
    "10": ("MX-DUR", "Durango"),
    "11": ("MX-GUA", "Guanajuato"),
    "12": ("MX-GRO", "Guerrero"),
    "13": ("MX-HID", "Hidalgo"),
    "14": ("MX-JAL", "Jalisco"),
    "15": ("MX-MEX", "México"),
    "16": ("MX-MIC", "Michoacán de Ocampo"),
    "17": ("MX-MOR", "Morelos"),
    "18": ("MX-NAY", "Nayarit"),
    "19": ("MX-NLE", "Nuevo León"),
    "20": ("MX-OAX", "Oaxaca"),
    "21": ("MX-PUE", "Puebla"),
    "22": ("MX-QUE", "Querétaro"),
    "23": ("MX-ROO", "Quintana Roo"),
    "24": ("MX-SLP", "San Luis Potosí"),
    "25": ("MX-SIN", "Sinaloa"),
    "26": ("MX-SON", "Sonora"),
    "27": ("MX-TAB", "Tabasco"),
    "28": ("MX-TAM", "Tamaulipas"),
    "29": ("MX-TLA", "Tlaxcala"),
    "30": ("MX-VER", "Veracruz de Ignacio de la Llave"),
    "31": ("MX-YUC", "Yucatán"),
    "32": ("MX-ZAC", "Zacatecas"),
}

BIE_BASE = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _parse_periodo(periodo: str) -> str | None:
    if "/" not in periodo:
        return None
    year, sub = periodo.split("/", 1)
    if sub.startswith("T"):
        try:
            return f"{year}-{(int(sub[1]) - 1) * 3 + 1:02d}"
        except (ValueError, IndexError):
            return None
    try:
        return f"{year}-{int(sub):02d}"
    except ValueError:
        return None


def fetch_area(clave: str, area_cve: str, token: str) -> list[tuple]:
    """Descarga la serie completa de <clave> para un área geográfica (00 o 01-32)."""
    url = f"{BIE_BASE}/INDICATOR/{clave}/es/{area_cve}/false/BIE-BISE/2.0/{token}?type=json"
    try:
        resp = requests.get(url, timeout=30, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    ERROR {clave} area={area_cve}: {e}")
        return []

    nombre = INDICADORES_ESTADO.get(clave, clave)
    iso, estado_nombre = ESTADOS.get(area_cve, (area_cve, area_cve))
    rows = []
    for serie in data.get("Series", []):
        for obs in serie.get("OBSERVATIONS", []):
            periodo = obs.get("TIME_PERIOD", "")
            val_str = str(obs.get("OBS_VALUE", "") or "")
            if not val_str or val_str in ("N/E", "N/A", "null", "None"):
                continue
            fecha = _parse_periodo(periodo)
            if not fecha:
                continue
            try:
                valor = float(val_str)
            except (ValueError, TypeError):
                continue
            rows.append((clave, nombre, area_cve, iso, estado_nombre, fecha, valor))
    return rows


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


def cargar_indicadores_estado(truncate: bool = False, insert_batch: int = 2000):
    token = os.environ.get("INEGI_TOKEN", "")
    if not token:
        print("ERROR: INEGI_TOKEN no configurado.")
        print("Agrega INEGI_TOKEN=<tu-token> en .env")
        sys.exit(1)

    areas = list(ESTADOS.keys())  # "00" nacional + "01".."32"
    all_rows = []
    for clave in INDICADORES_ESTADO:
        print(f"Descargando {clave} ({INDICADORES_ESTADO[clave]}) en {len(areas)} áreas...")
        for i, area_cve in enumerate(areas, 1):
            rows = fetch_area(clave, area_cve, token)
            estado_nombre = ESTADOS[area_cve][1]
            if rows:
                all_rows.extend(rows)
                print(f"  [{i}/{len(areas)}] {estado_nombre}: {len(rows)} obs OK")
            else:
                print(f"  [{i}/{len(areas)}] {estado_nombre}: sin datos")
            time.sleep(0.3)

    if not all_rows:
        print("Sin datos para cargar.")
        return

    INSERT = """
        INSERT INTO ADMIN.GOLD_INDICADORES_INEGI_ESTADO
            (CLAVE, NOMBRE, ESTADO_CVE, ESTADO_ISO, ESTADO_NOMBRE, FECHA, VALOR)
        VALUES (:1,:2,:3,:4,:5,:6,:7)
    """

    conn = get_conn()
    cursor = conn.cursor()
    try:
        if truncate:
            cursor.execute("TRUNCATE TABLE ADMIN.GOLD_INDICADORES_INEGI_ESTADO")
            conn.commit()
            print("  Tabla truncada.")
        else:
            claves = list(INDICADORES_ESTADO.keys())
            claves_sql = ",".join("'" + c + "'" for c in claves)
            cursor.execute(
                f"DELETE FROM ADMIN.GOLD_INDICADORES_INEGI_ESTADO "
                f"WHERE CLAVE IN ({claves_sql})"
            )
            conn.commit()
            print("  Datos anteriores de estos indicadores eliminados.")

        n_batches = math.ceil(len(all_rows) / insert_batch)
        for i in range(n_batches):
            cursor.executemany(INSERT, all_rows[i*insert_batch:(i+1)*insert_batch])
            conn.commit()

        print(f"  OK {len(all_rows):,} filas en GOLD_INDICADORES_INEGI_ESTADO")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--truncate", action="store_true",
                        help="Truncar tabla antes de insertar")
    args = parser.parse_args()

    cargar_indicadores_estado(truncate=args.truncate)
    print("\nActualizacion INEGI por estado completada.")
