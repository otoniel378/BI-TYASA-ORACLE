"""
scripts/backfill_canacero_historico.py — Carga puntual (uso único, no se
integra a la app) de los archivos históricos de CANACERO SICEP descargados
manualmente por el usuario: importación 2021-2025 + exportación 2026.

Reutiliza mercado.canacero.loaders.cargar_csv_canacero(), el mismo camino
que usa el uploader de la pestaña "Participación TYASA" — reemplaza por
(año, movimiento), así que correr esto dos veces no duplica filas.

Uso:
    python scripts/backfill_canacero_historico.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mercado.canacero.loaders import cargar_csv_canacero

DOWNLOADS = r"C:\Users\OTONIEL\Downloads"

ARCHIVOS = [
    ("2021_ImpTot_20260825110658_98.csv", "IMPORTACION"),
    ("2022_ImpTot_20260825110523_98.csv", "IMPORTACION"),
    ("2023_ImpTot_20260825110445_98.csv", "IMPORTACION"),
    ("2024_ImpTot_20260825110415_98.csv", "IMPORTACION"),
    ("2025_ImpTot_20260825110341_98.csv", "IMPORTACION"),
    ("general_ExpTot_20260824121515_98.csv", "EXPORTACION"),
]


def main():
    for nombre, movimiento in ARCHIVOS:
        ruta = os.path.join(DOWNLOADS, nombre)
        print(f"Cargando {nombre} ({movimiento})...")
        resultado = cargar_csv_canacero(ruta, movimiento, nombre)
        print(f"  -> {resultado}")


if __name__ == "__main__":
    main()
