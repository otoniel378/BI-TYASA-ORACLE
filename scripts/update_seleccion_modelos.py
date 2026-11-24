"""
scripts/update_seleccion_modelos.py — Precalcula el modelo del modo Automático
de los pronósticos (forecasting.seleccionar_modelo, validación de origen móvil)
y lo guarda en GOLD_SELECCION_MODELO (ver setup_seleccion_modelos_oracle.py).

Series: demanda de Aceros Planos Negros (total, por proceso y productos con al
menos MESES_MIN_PRODUCTO meses) y comercio exterior CANACERO (total y por
fracción TYASA, importación y exportación). Usa los mismos loaders y opciones
que las páginas 04_forecasting y 08_pronostico_comercio, para que la firma de
los datos coincida. Solo recalcula las series cuya firma cambió.

Correr después de cargar ventas nuevas (transform_to_gold.py) o un archivo de
CANACERO. También corre mensual en .github/workflows/update_seleccion_modelos.yml.

Uso:
    python scripts/update_seleccion_modelos.py
    python scripts/update_seleccion_modelos.py --solo negros      # o canacero
    python scripts/update_seleccion_modelos.py --forzar           # recalcula todo
"""

import argparse
import logging
import sys
import time
import warnings
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "scripts"))

import pandas as pd
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)
load_dotenv()

from aceros_planos.negros.analytics.forecasting import filtrar_por_dimension, firma_serie, seleccionar_modelo
from setup_seleccion_modelos_oracle import get_conn

MESES_MIN_PRODUCTO = 24   # productos con menos historia se calculan al abrirlos en la app
MESES_MIN_FRACCION = 24


def _series_negros():
    from aceros_planos.negros.loaders import (
        get_fecha_corte, load_gold_demanda_mensual, load_gold_demanda_mensual_total, load_serie_mensual_proceso,
    )
    opc = dict(fecha_corte=get_fecha_corte(), rellenar_huecos=True)   # = _FC_OPC de 04_forecasting
    yield "NEGROS|TOTAL", load_gold_demanda_mensual_total(), opc
    df_proc = load_serie_mensual_proceso()
    for p in sorted(df_proc["PROCESO"].dropna().unique()):
        yield f"NEGROS|PROCESO|{p}", filtrar_por_dimension(df_proc, "PROCESO", p), opc
    df_m = load_gold_demanda_mensual()
    meses = df_m.groupby("PRODUCTO_LIMPIO")["PERIODO"].nunique()
    for p in sorted(meses[meses >= MESES_MIN_PRODUCTO].index):
        yield f"NEGROS|PRODUCTO|{p}", filtrar_por_dimension(df_m, "PRODUCTO_LIMPIO", p), opc


def _series_canacero():
    from mercado.canacero.loaders import (
        load_descripciones_tyasa, load_exog_pronostico, load_serie_tiempo_tyasa, load_series_fracciones_tyasa,
    )
    descripciones = load_descripciones_tyasa()
    cols = dict(col_periodo="periodo_mes", col_val="volumen_total")
    for mov in ("IMPORTACION", "EXPORTACION"):
        yield f"CANACERO|{mov}|TOTAL", load_serie_tiempo_tyasa(mov), dict(cols, df_exog=load_exog_pronostico(None))
        df_f = load_series_fracciones_tyasa(mov)
        for f in sorted(df_f["fraccion"].dropna().unique()):
            serie = filtrar_por_dimension(df_f, "fraccion", f, **cols)
            if len(serie) >= MESES_MIN_FRACCION:
                yield (f"CANACERO|{mov}|FRACCION|{f}", serie,
                       dict(cols, df_exog=load_exog_pronostico(descripciones.get(f))))


def main(solo: str | None, forzar: bool):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT SERIE_ID, FIRMA FROM ADMIN.GOLD_SELECCION_MODELO")
    previas = dict(cursor.fetchall())

    fuentes = {"negros": _series_negros, "canacero": _series_canacero}
    calculadas = omitidas = sin_validacion = 0
    t0 = time.time()
    for nombre, gen in fuentes.items():
        if solo and nombre != solo:
            continue
        for serie_id, df, opc in gen():
            firma = firma_serie(df, opc.get("col_periodo", "PERIODO"), opc.get("col_val", "PESO_TON"),
                                fecha_corte=opc.get("fecha_corte"), rellenar_huecos=opc.get("rellenar_huecos", False))
            if not firma or (not forzar and previas.get(serie_id) == firma):
                omitidas += 1
                continue
            modelo, wape = seleccionar_modelo(df, **opc)
            if modelo is None:
                sin_validacion += 1
                continue
            detalle = " | ".join(f"{k}: {v:.0f}%" for k, v in wape.items())[:400]
            cursor.execute("""
                MERGE INTO ADMIN.GOLD_SELECCION_MODELO t
                USING (SELECT :sid SERIE_ID FROM dual) s ON (t.SERIE_ID = s.SERIE_ID)
                WHEN MATCHED THEN UPDATE SET FIRMA = :firma, MODELO = :modelo, WAPE = :wape,
                                             DETALLE = :detalle, CALCULADO_EN = SYSTIMESTAMP
                WHEN NOT MATCHED THEN INSERT (SERIE_ID, FIRMA, MODELO, WAPE, DETALLE)
                                      VALUES (:sid, :firma, :modelo, :wape, :detalle)
            """, sid=serie_id, firma=firma, modelo=modelo, wape=round(float(wape.iloc[0]), 2), detalle=detalle)
            conn.commit()
            calculadas += 1
            print(f"  {serie_id}: {modelo} ({wape.iloc[0]:.1f}%)", flush=True)
    cursor.close()
    conn.close()
    print(f"\nListo en {(time.time() - t0) / 60:.1f} min · calculadas {calculadas} · sin cambios {omitidas} · "
          f"muy cortas para validar {sin_validacion}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--solo", choices=["negros", "canacero"])
    parser.add_argument("--forzar", action="store_true", help="Recalcula aunque los datos no hayan cambiado")
    args = parser.parse_args()
    main(args.solo, args.forzar)
