"""
aciertos.py — Pestaña "¿Qué tan bien acierta?" de los pronósticos.
Corre la validación de origen móvil (forecasting.backtest_origen_movil) con un
botón y muestra el error por meses de anticipación contra la meta.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import COLORS, COLOR_SEQUENCE
from core.forecasting import (
    CANDIDATOS_AUTO as MODELOS, backtest_origen_movil, error_global, resumen_origen_movil,
)

META_MAPE = 30
NOMBRE_CORTO = {"ets": "ETS", "sarima": "SARIMA", "xgb": "XGBoost", "naive": "Naive", "combo": "ETS + SARIMA"}
_COLORES = {"combo": COLORS["primary"], "ets": COLORS["success"], "sarima": COLORS["secondary"],
            "xgb": COLOR_SEQUENCE[1], "naive": COLORS["neutral"]}


LIMITE_POCO_CONFIABLE = 50


def aviso_confiabilidad(res) -> None:
    """Aviso corto bajo el pronóstico según qué tanto se equivoca el modelo en
    esta serie (validación de origen móvil; solo modo Automático)."""
    err = getattr(res, "error_origen_movil", None)
    if err is None:
        return
    if err > LIMITE_POCO_CONFIABLE:
        st.warning(f"Pronóstico poco confiable: en esta serie se equivoca en promedio {err:.0f} %. "
                   "Úsalo solo como referencia.")
    elif err > META_MAPE:
        st.caption(f"En esta serie el pronóstico se equivoca en promedio {err:.0f} % (meta ≤ {META_MAPE} %).")
    else:
        st.caption(f"En esta serie el pronóstico se equivoca en promedio {err:.0f} % (dentro de la meta).")


def render_aciertos(df: pd.DataFrame, key: str, referencia: str = "lo real", **kw_backtest) -> None:
    """<key>: único por página y serie (incluir la fecha de corte para recalcular
    al cargar datos nuevos). <kw_backtest>: col_periodo, col_val, fecha_corte,
    rellenar_huecos, df_exog — igual que generar_forecast."""
    st.caption(f"Se pronostica como si estuviéramos en meses anteriores y se compara con {referencia}. "
               f"Meta: error ≤ {META_MAPE} %.")
    if df.empty:
        st.warning("Sin datos.")
        return
    if st.button("Calcular aciertos (≈ 1 min)", key=f"btn_{key}") and key not in st.session_state:
        st.session_state[key] = backtest_origen_movil(df, horizonte=6, n_origenes=6, modelos=MODELOS, **kw_backtest)
    bt = st.session_state.get(key)
    if bt is None:
        st.info("Haz clic en el botón para calcular.")
        return
    if bt.empty:
        st.warning("Serie insuficiente para la validación.")
        return

    res = resumen_origen_movil(bt)
    res["Modelo"] = res["modelo"].map(NOMBRE_CORTO)
    glob = error_global(bt)
    mejor = glob.idxmin()
    mejora = (1 - glob[mejor] / glob["naive"]) * 100 if "naive" in glob else float("nan")

    c1, c2, c3 = st.columns(3)
    c1.metric("Mejor modelo", NOMBRE_CORTO[mejor])
    c2.metric("Error promedio (6 meses)", f"{glob[mejor]:.1f} %",
              delta="dentro de la meta" if glob[mejor] <= META_MAPE else "arriba de la meta",
              delta_color="normal" if glob[mejor] <= META_MAPE else "inverse")
    c3.metric("Mejor que repetir el año pasado", f"{mejora:.0f} %")

    tabla = res.pivot(index="Modelo", columns="h", values="MAPE (%)")
    tabla.columns = [f"{h} {'mes' if h == 1 else 'meses'}" for h in tabla.columns]
    tabla = tabla.loc[tabla.mean(axis=1).sort_values().index]
    st.markdown("**Error por meses de anticipación (MAPE %)**")
    st.dataframe(
        tabla.style.format("{:.1f}").map(
            lambda v: f"color:{COLORS['success'] if v <= META_MAPE else COLORS['danger']};font-weight:600"),
        width="stretch",
    )

    fig = go.Figure()
    for mk, g in res.groupby("modelo"):
        fig.add_trace(go.Scatter(x=g["h"], y=g["MAPE (%)"], name=NOMBRE_CORTO[mk], mode="lines+markers",
                                 line=dict(color=_COLORES.get(mk), width=3 if mk == mejor else 1.8)))
    fig.add_hline(y=META_MAPE, line=dict(color=COLORS["danger"], dash="dot"),
                  annotation_text=f"meta {META_MAPE} %", annotation_position="top left")
    fig.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=20, b=40), height=340,
        xaxis=dict(title="Meses de anticipación", dtick=1, showgrid=False),
        yaxis=dict(title="Error (MAPE %)", gridcolor="#E5E7EB"),
        legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
    )
    st.plotly_chart(fig, width="stretch", key=f"chart_{key}")
    st.caption(f"{bt['origen'].nunique()} cortes, de {bt['origen'].min():%b %Y} a {bt['origen'].max():%b %Y}. "
               "Error promedio = error total ÷ volumen total.")
