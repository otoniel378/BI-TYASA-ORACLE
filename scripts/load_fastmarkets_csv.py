"""
scripts/load_fastmarkets_csv.py — Carga exports CSV del dashboard de Fastmarkets
a Oracle ADW (GOLD_PRECIOS_FASTMARKETS). Idempotente: si el símbolo ya existía,
reemplaza su historial completo en vez de duplicar (cada export trae la serie
completa desde el widget).

Formato esperado (export "Valores separados por comas (.csv)" de un widget con
un solo símbolo):
    Title,<nombre widget>
    ,
    Symbol,<SIMBOLO>
    Description,"<descripción, incluye moneda/unidad al final: ...,peso/tonne>"
    Assessment Date,Mid
    <D/M/YYYY>,<valor>
    ...
    ,
    IMPORTANT NOTICE,
    ...

No se versiona en git (los .csv de data/fastmarkets/ están excluidos por
.gitignore): los datos de Fastmarkets son de licencia comercial y el repo es
público, así que solo viven en Oracle, nunca en el repo.

Uso:
    python scripts/load_fastmarkets_csv.py                     # carga todo data/fastmarkets/*.csv
    python scripts/load_fastmarkets_csv.py --file ruta.csv      # carga un archivo específico
    python scripts/load_fastmarkets_csv.py --dir otra/carpeta   # otra carpeta de exports
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

_MONEDAS = {
    "peso": "MXN", "pesos": "MXN", "mxn": "MXN",
    "usd": "USD", "us$": "USD", "$": "USD", "dollar": "USD", "dollars": "USD",
    "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "gbp": "GBP", "libra": "GBP", "pound": "GBP",
}
_UNIDADES = {
    "tonne": "tonelada", "tonnes": "tonelada", "tonelada": "tonelada", "ton": "tonelada",
    "kg": "kg", "kilogram": "kg",
    "lb": "lb", "lbs": "lb", "pound": "lb",
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


def _inferir_moneda_unidad(descripcion: str):
    """Intenta leer moneda/unidad del sufijo típico de Fastmarkets, ej.
    '...delivered Monterrey, Mexico, peso/tonne' -> ('MXN', 'tonelada')."""
    if not descripcion:
        return None, None
    ultimo = descripcion.split(",")[-1].strip().lower()
    if "/" not in ultimo:
        return None, None
    moneda_raw, _, unidad_raw = ultimo.partition("/")
    return _MONEDAS.get(moneda_raw.strip()), _UNIDADES.get(unidad_raw.strip())


def _parse_fastmarkets_csv(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.reader(f))

    simbolo = None
    descripcion = None
    data_rows = []
    in_data = False

    for fila in filas:
        if not fila or all(not c.strip() for c in fila):
            in_data = False
            continue
        clave = fila[0].strip()
        if clave == "Symbol":
            simbolo = fila[1].strip() if len(fila) > 1 else None
            continue
        if clave == "Description":
            descripcion = fila[1].strip() if len(fila) > 1 else None
            continue
        if clave == "Assessment Date":
            in_data = True
            continue
        if clave in ("IMPORTANT NOTICE", "Title"):
            in_data = False
            continue
        if in_data:
            data_rows.append(fila)

    if not simbolo:
        raise ValueError("no se encontró la fila 'Symbol' — ¿es un export de Fastmarkets?")
    if not data_rows:
        raise ValueError("no se encontraron filas de datos tras 'Assessment Date'")
    if any(len(r) != 2 for r in data_rows):
        raise ValueError(
            "el export tiene más de una columna de valores — por ahora este loader "
            "solo soporta un símbolo por archivo (exporta un widget con un solo símbolo)"
        )

    puntos = []
    for fecha_str, valor_str in data_rows:
        fecha_str, valor_str = fecha_str.strip(), valor_str.strip()
        if not fecha_str or not valor_str:
            continue
        fecha = datetime.strptime(fecha_str, "%d/%m/%Y").date()
        puntos.append((fecha, float(valor_str)))

    if not puntos:
        raise ValueError("no se pudo leer ningún punto de datos válido")

    puntos.sort(key=lambda p: p[0])
    return simbolo, descripcion or "", puntos


def cargar_serie(conn, simbolo: str, descripcion: str, puntos: list):
    moneda, unidad = _inferir_moneda_unidad(descripcion)
    ahora = datetime.utcnow()

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ADMIN.GOLD_PRECIOS_FASTMARKETS WHERE SIMBOLO = :1", [simbolo])
        conn.commit()

        rows = [
            (fecha, simbolo, descripcion[:500], valor, moneda, unidad, ahora)
            for fecha, valor in puntos
        ]
        cursor.executemany("""
            INSERT INTO ADMIN.GOLD_PRECIOS_FASTMARKETS
                (FECHA, SIMBOLO, DESCRIPCION, VALOR, MONEDA, UNIDAD, CARGADO_EN)
            VALUES (:1,:2,:3,:4,:5,:6,:7)
        """, rows)
        conn.commit()

        unidad_txt = f"{moneda or '?'}/{unidad or '?'}"
        print(f"  OK {simbolo}: {len(rows)} observaciones "
              f"({puntos[0][0]} -> {puntos[-1][0]}) · {unidad_txt}")
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="CSV específico a cargar")
    parser.add_argument("--dir", default="data/fastmarkets", help="Carpeta con exports *.csv")
    args = parser.parse_args()

    if args.file:
        archivos = [Path(args.file)]
    else:
        archivos = sorted(Path(args.dir).glob("*.csv"))
        if not archivos:
            print(f"Sin archivos CSV en {args.dir}")
            sys.exit(1)

    conn = get_conn()
    try:
        for path in archivos:
            print(f"\nProcesando {path.name}...")
            try:
                simbolo, descripcion, puntos = _parse_fastmarkets_csv(path)
            except ValueError as e:
                print(f"  SALTADO: {e}")
                continue
            cargar_serie(conn, simbolo, descripcion, puntos)
    finally:
        conn.close()

    print("\nCarga Fastmarkets completada.")


if __name__ == "__main__":
    main()
