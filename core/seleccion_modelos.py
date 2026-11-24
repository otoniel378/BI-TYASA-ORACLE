"""
seleccion_modelos.py — Modelo que usa el modo Automático de los pronósticos.

scripts/update_seleccion_modelos.py corre la validación de origen móvil
(forecasting.seleccionar_modelo) de cada serie y guarda el ganador en
GOLD_SELECCION_MODELO junto con la firma de los datos (forecasting.firma_serie).
Si la tabla no existe todavía o los datos cambiaron desde el cálculo (firma
distinta), forecast_auto lo calcula al momento (~15 s por serie).
"""

import pandas as pd
import streamlit as st

from core.db_connector import run_query, table_ref
from core.forecasting import firma_serie, generar_forecast

T_SELECCION = table_ref("GOLD_SELECCION_MODELO")


@st.cache_data(ttl=3600, show_spinner=False)
def load_selecciones() -> pd.DataFrame:
    try:
        df = run_query(f"SELECT SERIE_ID, FIRMA, MODELO, WAPE FROM {T_SELECCION}")
    except RuntimeError:  # tabla aún no creada (scripts/setup_seleccion_modelos_oracle.py)
        return pd.DataFrame(columns=["serie_id", "firma", "modelo", "wape"])
    df.columns = [c.lower() for c in df.columns]
    return df


def modelo_precalculado(serie_id: str, firma: str) -> tuple[str | None, float | None]:
    """(modelo, WAPE %) guardados para la serie si siguen vigentes."""
    sel = load_selecciones()
    m = sel[(sel["serie_id"] == serie_id) & (sel["firma"] == firma)]
    if m.empty:
        return None, None
    return m["modelo"].iloc[0], (float(m["wape"].iloc[0]) if pd.notna(m["wape"].iloc[0]) else None)


def forecast_auto(df: pd.DataFrame, horizonte: int, serie_id: str, **kw):
    """generar_forecast en modo Automático con la selección precalculada si
    sigue vigente. <kw>: mismos argumentos de generar_forecast."""
    firma = firma_serie(df, kw.get("col_periodo", "PERIODO"), kw.get("col_val", "PESO_TON"),
                        fecha_corte=kw.get("fecha_corte"), rellenar_huecos=kw.get("rellenar_huecos", False))
    modelo, wape = modelo_precalculado(serie_id, firma)
    res = generar_forecast(df, horizonte, modelo="auto", seleccion=modelo, **kw)
    if modelo is not None and res.error_origen_movil is None:
        res.error_origen_movil = wape
    return res


def generar(df: pd.DataFrame, horizonte: int, modelo: str, serie_id: str, **kw):
    """Punto de entrada de las páginas: Automático usa forecast_auto; los demás
    modelos van directo a generar_forecast."""
    if modelo == "auto":
        return forecast_auto(df, horizonte, serie_id, **kw)
    return generar_forecast(df, horizonte, modelo=modelo, **kw)
