"""
scripts/update_trafico_maritimo.py — Baja de IMF PortWatch (CSV en HDX) el
tráfico diario de los pasos marítimos y puertos de llegada que monitorea la
página Rutas y puertos, y reemplaza GOLD_TRAFICO_PASOS y GOLD_TRAFICO_PUERTOS
(últimos 2 años). PortWatch publica cada semana con ~10 días de retraso; correrlo
a diario solo asegura tomar la publicación en cuanto sale.

Antes, una sola vez: python scripts/setup_rutas_oracle.py
Uso:               python scripts/update_trafico_maritimo.py
Workflow:          .github/workflows/update_trafico_maritimo.yml (L–V)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from dotenv import load_dotenv

from mercado_rutas.fuentes import descargar_pasos, descargar_puertos
from scripts.setup_rutas_oracle import get_conn

load_dotenv()


def _reemplazar(conn, tabla: str, columnas: list[str], df: pd.DataFrame) -> int:
    filas = [tuple(None if pd.isna(v) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in r)
             for r in df[columnas].itertuples(index=False)]
    cursor = conn.cursor()
    # Oracle ADW hace el DELETE en paralelo y entonces no deja insertar en la misma
    # transacción (ORA-12838); igual que en update_semaforo_ferros.py
    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
    cursor.execute(f"DELETE FROM ADMIN.{tabla}")
    marcas = ", ".join(f":{i + 1}" for i in range(len(columnas)))
    cursor.executemany(f"INSERT INTO ADMIN.{tabla} ({', '.join(c.upper() for c in columnas)}) VALUES ({marcas})", filas)
    conn.commit()
    cursor.close()
    return len(filas)


def main():
    print("Descargando IMF PortWatch...")
    pasos, puertos = descargar_pasos(), descargar_puertos()
    if pasos.empty or puertos.empty:
        raise SystemExit("PortWatch devolvió datos vacíos; no se tocan las tablas")
    print(f"  Pasos: {pasos['paso'].nunique()} · {pasos['fecha'].min():%Y-%m-%d} a {pasos['fecha'].max():%Y-%m-%d}")
    print(f"  Puertos: {puertos['puerto'].nunique()} · hasta {puertos['fecha'].max():%Y-%m-%d}")
    conn = get_conn()
    try:
        n1 = _reemplazar(conn, "GOLD_TRAFICO_PASOS", ["fecha", "paso", "transitos", "granel"], pasos)
        n2 = _reemplazar(conn, "GOLD_TRAFICO_PUERTOS", ["fecha", "puerto", "llamadas", "granel"], puertos)
    finally:
        conn.close()
    print(f"  Guardadas {n1} filas de pasos y {n2} de puertos")


if __name__ == "__main__":
    main()
