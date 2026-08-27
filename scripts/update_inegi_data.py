"""
update_inegi_data.py — Descarga indicadores INEGI y los carga en Oracle ADW.

Tablas destino: ADMIN.GOLD_INDICADORES_INEGI

Uso:
    python scripts/update_inegi_data.py
    python scripts/update_inegi_data.py --truncate   # limpia antes de insertar
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import math
import requests
import oracledb
from dotenv import load_dotenv

load_dotenv()

try:
    import pandas as pd
except ImportError:
    print("Instala pandas: pip install pandas")
    sys.exit(1)

INEGI_TOKEN = os.environ.get("INEGI_TOKEN", "")

INDICADORES = {
    "736407": "IMAI_ActividadIndustrial_Indice",
    "736418": "IMAI_Manufactureras_Indice",
    "736414": "IMAI_Construccion_Indice",
    "736475": "IMAI_MetalicasBasicas_331_Indice",
    "736476": "IMAI_HierroAcero_3311_Indice",
    "736481": "IMAI_ProductosMetalicos_332_Indice",
    "736491": "IMAI_MaquinariaEquipo_333_Indice",
    "736526": "IMAI_ActividadIndustrial_VarAnual",
    "736533": "IMAI_Construccion_VarAnual",
    "736594": "IMAI_MetalicasBasicas_331_VarAnual",
    "910468": "EMIM_VolFisico_Desest_Indice",
    "910470": "EMIM_VolFisico_Desest_VarAnual",
    "720332": "ENEC_ValorProd_ObraTotal",
    "720334": "ENEC_ValorProd_Edificacion",
    "720336": "ENEC_ValorProd_AguaRiegoSaneamiento",
    "720338": "ENEC_ValorProd_ElectricidadTelecom",
    "720340": "ENEC_ValorProd_Transporte_Urb",
    "720342": "ENEC_ValorProd_PetroleoPetroquimica",
    "720344": "ENEC_ValorProd_OtrasConstrucciones",
    # ── ENEC mensual EN PESOS — "Valores absolutos corrientes > Por tipo de obra
    #    específico > [categoría] > Total [categoría]" (miles de pesos corrientes,
    #    UNIT 9997) — contraparte en pesos de los índices 720332-344 de arriba,
    #    validada por correlación >0.94 (0.76 en Otras Construcciones) contra ellos ─
    "722078": "ENEC_ValorProdPesos_Edificacion",
    "722084": "ENEC_ValorProdPesos_AguaRiegoSaneamiento",
    "722088": "ENEC_ValorProdPesos_ElectricidadTelecom",
    "722092": "ENEC_ValorProdPesos_Transporte_Urb",
    "722099": "ENEC_ValorProdPesos_PetroleoPetroquimica",
    "722103": "ENEC_ValorProdPesos_OtrasConstrucciones",
    "718504": "EMEC_Ingresos_ComercioMayor_43",
    "718506": "EMEC_Ingresos_ComercioMenor_46",
    "737173": "IGAE_Secundario_Indice",
    "737149": "IGAE_Secundario_VarAnual",
    "133094": "BC_Siderurgia_Importaciones",
    "133031": "BC_Siderurgia_Exportaciones",
    "910503": "INPP_Manufactura_3133",
    "910502": "INPP_Construccion_23",
    "910501": "INPP_Energia_22",
    "910500": "INPP_Mineria_SinPetroleo",
    "910499": "INPP_Mineria_ConPetroleo",
    "910491": "INPP_SinPetroleo_ConServicios",
    "910396": "INPC_Total_Mensual",
    "909294": "INPC_Energeticos_NoSubyacente",
    "910398": "INPC_Energeticos_Gobierno",
    "910393": "INPC_Subyacente_Total",
    "741034": "IFB_Construccion",
    "741030": "IFB_Maquinaria_Importada",
    "741025": "IFB_Maquinaria_Nacional",
    "701407": "ICE_Construccion",
    "701401": "ICE_Global",
    "334497": "ICC_Confianza_Consumidor",
    # ── ENEC ANUAL — Sector 23 Construcción (valor de producción por subsector) ─
    "796426": "ENEC_Anual_ValorProd_Sector23",
    "796427": "ENEC_Anual_ValorProd_Subsector236_Edificacion",
    "796428": "ENEC_Anual_ValorProd_Subsector237_ObrasIngCivil",
    "796429": "ENEC_Anual_ValorProd_Subsector238_TrabEspecializados",
    "5300000027": "ENEC_Anual_Remuneraciones_Sector23",
}

BIE_BASE   = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml"
BATCH_SIZE = 20

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
        # Series anuales (FREQ Anual): TIME_PERIOD viene como "2024", sin sufijo.
        # Se guarda como cierre de año (YYYY-12) para respetar el formato YYYY-MM
        # que usan el resto de los indicadores en GOLD_INDICADORES_INEGI.
        if periodo.isdigit() and len(periodo) == 4:
            return f"{periodo}-12"
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


# Indicadores descontinuados/legado que solo existen en el banco "BISE"
# (el resto del catálogo vive en "BIE-BISE"; mezclarlos en un mismo batch
# devuelve 401 en vez del 400 individual, por eso se separan aquí).
BANCO_ESPECIAL: dict[str, str] = {
    "5300000027": "BISE",
}


def fetch_batch(ids: list[str], token: str, banco: str = "BIE-BISE") -> list[tuple]:
    """Descarga un batch de indicadores INEGI (área=00, banco configurable)."""
    ids_str = ",".join(ids)
    url = f"{BIE_BASE}/INDICATOR/{ids_str}/es/00/false/{banco}/2.0/{token}?type=json"
    try:
        resp = requests.get(url, timeout=30, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ERROR batch {ids[:2]}...: {e}")
        return []

    rows = []
    for serie in data.get("Series", []):
        clave  = str(serie.get("INDICADOR", ""))
        nombre = INDICADORES.get(clave, clave)
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
            rows.append((clave, nombre, fecha, valor))
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


def cargar_indicadores(truncate: bool = False, insert_batch: int = 2000):
    token = os.environ.get("INEGI_TOKEN", "")
    if not token:
        print("ERROR: INEGI_TOKEN no configurado.")
        print("Agrega INEGI_TOKEN=<tu-token> en .env")
        sys.exit(1)

    import time
    ids     = [c for c in INDICADORES.keys() if c not in BANCO_ESPECIAL]
    batches = [ids[i:i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]
    print(f"Descargando {len(ids)} indicadores en {len(batches)} batch(es)...")

    all_rows = []
    for i, batch in enumerate(batches, 1):
        rows = fetch_batch(batch, token)
        if rows:
            all_rows.extend(rows)
            print(f"  Batch {i}/{len(batches)}: {len(rows)} obs OK")
        else:
            print(f"  Batch {i}/{len(batches)}: sin datos")
        if i < len(batches):
            time.sleep(0.5)

    for clave, banco in BANCO_ESPECIAL.items():
        rows = fetch_batch([clave], token, banco=banco)
        if rows:
            all_rows.extend(rows)
            print(f"  {clave} (banco {banco}): {len(rows)} obs OK")
        else:
            print(f"  {clave} (banco {banco}): sin datos")

    if not all_rows:
        print("Sin datos para cargar.")
        return

    INSERT = """
        INSERT INTO ADMIN.GOLD_INDICADORES_INEGI (CLAVE, NOMBRE, FECHA, VALOR)
        VALUES (:1,:2,:3,:4)
    """

    conn = get_conn()
    cursor = conn.cursor()
    try:
        if truncate:
            cursor.execute("TRUNCATE TABLE ADMIN.GOLD_INDICADORES_INEGI")
            conn.commit()
            print(f"  Tabla truncada.")
        else:
            cursor.execute("DELETE FROM ADMIN.GOLD_INDICADORES_INEGI")
            conn.commit()
            print(f"  Datos anteriores eliminados.")

        n_batches = math.ceil(len(all_rows) / insert_batch)
        for i in range(n_batches):
            cursor.executemany(INSERT, all_rows[i*insert_batch:(i+1)*insert_batch])
            conn.commit()

        print(f"  OK {len(all_rows):,} filas en GOLD_INDICADORES_INEGI")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--truncate", action="store_true",
                        help="Truncar tabla antes de insertar")
    args = parser.parse_args()

    cargar_indicadores(truncate=args.truncate)
    print("\nActualizacion INEGI completada.")
