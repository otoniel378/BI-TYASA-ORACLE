"""
migrate_categoria_column.py — Agrega la columna CATEGORIA a la tabla
ADMIN.GOLD_SENTIMIENTO_NOTICIAS ya existente en producción.

Migración idempotente: si la columna ya existe (ORA-01430), no falla.
NO usa setup_market_tables_oracle.py directamente porque su __main__ hace
TRUNCATE + reload de otras tablas (GOLD_QUIEBRES_DETECTADOS, GOLD_VARIABLES_MERCADO)
— este script solo toca la columna nueva, nada más.

Uso:
  python scripts/migrate_categoria_column.py
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

from scripts.setup_market_tables_oracle import get_conn


def run():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        try:
            cursor.execute(
                "ALTER TABLE ADMIN.GOLD_SENTIMIENTO_NOTICIAS ADD (CATEGORIA VARCHAR2(50))"
            )
            conn.commit()
            print("OK: columna CATEGORIA agregada a GOLD_SENTIMIENTO_NOTICIAS")
        except Exception as e:
            if "ORA-01430" in str(e):
                print("OK: la columna CATEGORIA ya existía, nada que hacer")
            else:
                raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
