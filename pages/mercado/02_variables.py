"""
02_variables.py — Variables Globales de Mercado — TYASA BI
Series históricas de las 31 variables siderúrgicas monitoreadas.
"""

import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from config import COLORS, COLOR_SEQUENCE

from mercado_noticias.loaders import load_variables_mercado, load_quiebres_activos
from core.components.filters import sidebar_header
from core.components.kpi_cards import seccion_titulo
from core.components.tables import tabla_ejecutiva

sidebar_header("Variables Globales")

dias_hist = st.sidebar.slider("Días de historia", 90, 500, 400, step=30, key="vg_dias")
cat_vg = st.sidebar.selectbox(
    "Categoría",
    ["Todas", "Energía", "Insumos_Acero", "Sector_Acero",
     "Logistica", "Riesgo_Mercados", "Asia", "Europa", "Mexico"],
    key="vg_cat"
)

st.markdown(
    f"""
    <h2 style='color:{COLORS["primary"]};margin-bottom:0;'>Variables Globales de Mercado</h2>
    <p style='color:{COLORS["text_light"]};'>Series históricas · 31 variables · Actualización diaria</p>
    """,
    unsafe_allow_html=True,
)
st.divider()

with st.spinner("Cargando datos..."):
    df_vars     = load_variables_mercado(dias=dias_hist)
    df_quiebres = load_quiebres_activos()

if df_vars.empty:
    st.warning("Sin datos disponibles. Verifica la tabla gold_variables_mercado en BigQuery.")
    st.stop()

# Filtrar por categoría
if cat_vg != "Todas":
    df_vars = df_vars[df_vars["categoria"] == cat_vg]

FECHA_EVENTO = pd.Timestamp("2026-02-28")
nombres = sorted(df_vars["nombre"].unique().tolist())

# ── Vista general: mini sparklines por categoría ──────────────────────────────
seccion_titulo("Resumen por categoría", "Cambio acumulado desde el inicio del conflicto (28-Feb-2026)")

cat_cols = [c for c in df_vars["categoria"].unique()]
cambios_resumen = []
for nombre in nombres:
    sub = df_vars[df_vars["nombre"] == nombre].sort_values("fecha")
    pre  = sub[sub["fecha"] < FECHA_EVENTO]["valor"]
    post = sub[sub["fecha"] >= FECHA_EVENTO]["valor"]
    if len(pre) < 5 or len(post) < 1:
        continue
    cambio = (post.mean() - pre.mean()) / abs(pre.mean()) * 100
    cat    = sub["categoria"].iloc[0]
    cambios_resumen.append({"Variable": nombre.replace("_", " "), "Categoría": cat,
                             "Media pre": round(pre.mean(), 2), "Media post": round(post.mean(), 2),
                             "Cambio %": round(cambio, 1)})

if cambios_resumen:
    df_resumen = pd.DataFrame(cambios_resumen).sort_values("Cambio %", key=abs, ascending=False)
    fig_bar = px.bar(
        df_resumen, x="Cambio %", y="Variable", orientation="h",
        color="Cambio %",
        color_continuous_scale=["#1E8449", "#F4F4F4", "#C0392B"],
        color_continuous_midpoint=0,
        title=f"Cambio % en media diaria post vs pre evento ({len(df_resumen)} variables)",
        labels={"Cambio %": "Cambio %", "Variable": ""},
    )
    fig_bar.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=10),
        margin=dict(l=10, r=60, t=50, b=40),
        height=max(400, len(df_resumen) * 22 + 80),
        coloraxis_showscale=False,
        xaxis=dict(title="Cambio %", gridcolor="#E5E7EB", zeroline=True, zerolinecolor="#888"),
        yaxis=dict(tickfont=dict(size=9)),
        title=dict(font=dict(size=13, color=COLORS["primary"]), x=0),
    )
    st.plotly_chart(fig_bar, width="stretch")

st.divider()

# ── Panel de series individuales ──────────────────────────────────────────────
seccion_titulo("Series históricas individuales", "Selecciona una o varias variables")

vars_sel = st.multiselect(
    "Variables a mostrar",
    options=nombres,
    default=nombres[:4] if len(nombres) >= 4 else nombres,
    key="vg_vars_sel"
)

if vars_sel:
    COLS = min(3, len(vars_sel))
    ROWS = (len(vars_sel) + COLS - 1) // COLS
    cols_grid = st.columns(COLS)

    for i, var in enumerate(vars_sel):
        col = cols_grid[i % COLS]
        with col:
            sub = df_vars[df_vars["nombre"] == var].sort_values("fecha")
            if sub.empty:
                st.caption(f"{var}: sin datos")
                continue

            pre_s = sub[sub["fecha"] <  FECHA_EVENTO]
            pos_s = sub[sub["fecha"] >= FECHA_EVENTO]

            # Cambio
            if len(pre_s) >= 5 and len(pos_s) >= 1:
                cambio = (pos_s["valor"].mean() - pre_s["valor"].mean()) / abs(pre_s["valor"].mean()) * 100
                cambio_str = f"{cambio:+.1f}%"
                c_color = COLORS["danger"] if cambio > 0 else COLORS["success"]
            else:
                cambio_str = "—"
                c_color = COLORS["neutral"]

            fig2 = go.Figure()
            if not pre_s.empty:
                fig2.add_trace(go.Scatter(
                    x=pre_s["fecha"], y=pre_s["valor"],
                    line=dict(color=COLORS["primary"], width=1.4), opacity=0.6,
                    name="Pre", hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f}<extra></extra>"
                ))
            if not pos_s.empty:
                fig2.add_trace(go.Scatter(
                    x=pos_s["fecha"], y=pos_s["valor"],
                    line=dict(color=COLORS["danger"], width=2.2),
                    name="Post", hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f}<extra></extra>"
                ))
                fig2.add_vrect(
                    x0=str(FECHA_EVENTO.date()), x1=str(pos_s["fecha"].max().date()),
                    fillcolor="rgba(192,57,43,0.06)", line_width=0,
                )
            fig2.add_vline(
                x=FECHA_EVENTO.timestamp() * 1000,
                line_width=1.5, line_dash="dash",
                line_color=COLORS["danger"], opacity=0.8,
            )
            fig2.add_annotation(
                x=FECHA_EVENTO.timestamp() * 1000,
                y=1, yref="paper",
                text="Inicio evento",
                showarrow=False,
                yanchor="bottom",
                font=dict(size=9, color=COLORS["danger"]),
                bgcolor="rgba(255,255,255,0.7)",
            )
            fig2.add_annotation(
                x=0.97, y=0.97, xref="paper", yref="paper",
                text=cambio_str,
                showarrow=False, font=dict(size=14, color=c_color, family="Inter"),
                bgcolor="rgba(255,255,255,0.8)",
            )
            fig2.update_layout(
                paper_bgcolor=COLORS["surface"],
                plot_bgcolor=COLORS["background"],
                font=dict(family="Inter", size=9, color=COLORS["text"]),
                margin=dict(l=30, r=10, t=35, b=30),
                height=200, showlegend=False,
                title=dict(text=var.replace("_", " "), font=dict(size=10, color=COLORS["primary"]), x=0),
                xaxis=dict(showgrid=False, tickfont=dict(size=7)),
                yaxis=dict(gridcolor="#F0F0F0", tickfont=dict(size=7)),
            )
            st.plotly_chart(fig2, width="stretch")

st.divider()

# ── Tabla resumen exportable ──────────────────────────────────────────────────
seccion_titulo("Tabla resumen — exportable a Excel", "")

if cambios_resumen:
    tabla_ejecutiva(
        df_resumen,
        col_formatos={"Media pre": "{:,.2f}", "Media post": "{:,.2f}", "Cambio %": "{:+.1f}%"},
        key="tabla_vars_globales",
        height=400,
    )
