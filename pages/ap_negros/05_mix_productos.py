"""
05_mix_productos.py — Mix de Productos — Aceros Planos Negros.
"""

import os, sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from config import COLORS, COLOR_SEQUENCE, HEATMAP_COLORSCALE

from aceros_planos.negros.loaders import (
    load_gold_demanda_mensual,
    load_gold_cliente_producto,
    load_ventas_limpias,
)
from aceros_planos.negros.analytics.mix_productos import (
    n_familias_por_cliente,
    tabla_coocurrencia,
    combinaciones_frecuentes,
    oportunidades_crosssell,
)
from core.components.kpi_cards import render_kpi_row, seccion_titulo
from core.components.filters import sidebar_header, filtro_clientes, aplicar_filtro_lista
from core.components.charts import heatmap
from core.components.tables import tabla_ejecutiva

sidebar_header("Filtros")
clientes_sel = filtro_clientes(key_prefix="mix")
min_clientes_combo = st.sidebar.slider("Min. clientes para combos", min_value=1, max_value=20, value=2, key="mix_min_clientes")

with st.spinner("Cargando datos..."):
    df_mensual_gran = load_gold_demanda_mensual()
    df_cp_base = load_gold_cliente_producto()
    df_vl = load_ventas_limpias()

if "PERIODO" in df_mensual_gran.columns:
    df_mensual_gran["PERIODO"] = pd.to_datetime(df_mensual_gran["PERIODO"], errors="coerce")
if "FECHAEMB" in df_vl.columns:
    df_vl["FECHAEMB"] = pd.to_datetime(df_vl["FECHAEMB"], errors="coerce")

anios_mix = sorted(df_vl["FECHAEMB"].dropna().dt.year.unique().tolist(), reverse=True) if not df_vl.empty and "FECHAEMB" in df_vl.columns else []
meses_nombres = ["Todos", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

st.markdown(
    f"""
    <h2 style='color:{COLORS["primary"]};margin-bottom:0;'>Mix de Productos</h2>
    <p style='color:{COLORS["text_light"]};'>Portafolio, especificaciones tecnicas y oportunidades de cross-sell</p>
    """,
    unsafe_allow_html=True,
)
st.divider()

# KPIs
df_cp_kpi = df_cp_base.copy()
if clientes_sel:
    df_cp_kpi = aplicar_filtro_lista(df_cp_kpi, clientes_sel, "CLIENTE")

total_productos = df_mensual_gran["PRODUCTO_LIMPIO"].nunique() if not df_mensual_gran.empty and "PRODUCTO_LIMPIO" in df_mensual_gran.columns else 0
total_clientes  = df_cp_kpi["CLIENTE"].nunique() if not df_cp_kpi.empty else 0
df_nfam  = n_familias_por_cliente(df_cp_kpi)
prom_fam = round(df_nfam["N_PRODUCTOS"].mean(), 1) if not df_nfam.empty else 0
mono     = int((df_nfam["N_PRODUCTOS"] == 1).sum()) if not df_nfam.empty else 0

render_kpi_row([
    {"label": "Productos activos",       "value": total_productos},
    {"label": "Clientes activos",        "value": total_clientes},
    {"label": "Prom. productos/cliente", "value": prom_fam},
    {"label": "Clientes monoproducto",   "value": mono,
     "help_text": "Maxima oportunidad de cross-sell."},
])
st.divider()

# ── SECCION 1 — Participacion por producto ────────────────────────────────────
seccion_titulo("Participacion por Producto", "Evolucion por periodo con filtros inline")

col_f1, col_f2, col_f3 = st.columns([1, 1, 4])
with col_f1:
    anio_mix_sel = st.selectbox("Anio", options=["Todos"] + [str(a) for a in anios_mix], key="mix_anio_inline")
with col_f2:
    mes_mix_sel = st.selectbox("Mes", options=meses_nombres, key="mix_mes_inline", disabled=(anio_mix_sel == "Todos"))

mes_num = meses_nombres.index(mes_mix_sel) if mes_mix_sel != "Todos" and anio_mix_sel != "Todos" else 0
excluir_mix = {"OTROS", "OTHER", "N/D", "SIN CLASIFICAR", "S/C"}
df_mg = df_mensual_gran.dropna(subset=["PERIODO"]).copy()
if "PRODUCTO_LIMPIO" in df_mg.columns:
    df_mg = df_mg[~df_mg["PRODUCTO_LIMPIO"].str.upper().isin(excluir_mix)]

if anio_mix_sel != "Todos":
    df_mg = df_mg[df_mg["PERIODO"].dt.year == int(anio_mix_sel)]
    if mes_num > 0:
        df_mg = df_mg[df_mg["PERIODO"].dt.month == mes_num]

if not df_mg.empty and "PRODUCTO_LIMPIO" in df_mg.columns:
    if anio_mix_sel != "Todos" and mes_num == 0:
        df_mg["EJE"] = df_mg["PERIODO"].dt.strftime("%b %Y")
        eje_label = "Mes"
    elif anio_mix_sel != "Todos" and mes_num > 0:
        df_mg["EJE"] = df_mg["PERIODO"].dt.strftime("%b %Y")
        eje_label = "Mes"
    else:
        df_mg["EJE"] = df_mg["PERIODO"].dt.year.astype(str)
        eje_label = "Anio"

    orden_eje = (
        df_mg.drop_duplicates("EJE").sort_values("PERIODO")["EJE"].tolist()
        if anio_mix_sel != "Todos" else
        df_mg.drop_duplicates("EJE").sort_values("EJE")["EJE"].tolist()
    )
    df_stk = df_mg.groupby(["EJE", "PRODUCTO_LIMPIO"], as_index=False)["PESO_TON"].sum()

    fig_stk = px.bar(df_stk, x="EJE", y="PESO_TON", color="PRODUCTO_LIMPIO",
                      title=f"Participacion por producto — {eje_label}",
                      labels={"PESO_TON": "Toneladas", "EJE": eje_label, "PRODUCTO_LIMPIO": "Producto"},
                      color_discrete_sequence=COLOR_SEQUENCE, category_orders={"EJE": orden_eje})
    fig_stk.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=11),
        margin=dict(l=40, r=20, t=50, b=80),
        legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center", font=dict(size=10), title_text=""),
        height=430, barmode="stack",
        xaxis=dict(title=eje_label, showgrid=False, tickangle=-30),
        yaxis=dict(title="Toneladas", gridcolor="#E5E7EB"),
        title=dict(font=dict(size=14, color=COLORS["primary"]), x=0),
    )
    st.plotly_chart(fig_stk, width="stretch")

    df_part_res = df_mg.groupby("PRODUCTO_LIMPIO", as_index=False)["PESO_TON"].sum().sort_values("PESO_TON", ascending=False)
    total_t = df_part_res["PESO_TON"].sum()
    df_part_res["PCT"]      = (df_part_res["PESO_TON"] / total_t * 100).round(1) if total_t > 0 else 0
    df_part_res["PCT_ACUM"] = df_part_res["PCT"].cumsum().round(1)
    tabla_ejecutiva(df_part_res, titulo="Participacion por producto en el periodo seleccionado",
                    col_formatos={"PESO_TON": "{:,.1f}", "PCT": "{:.1f}%", "PCT_ACUM": "{:.1f}%"},
                    key="part_prod_tabla", height=260)
else:
    st.info("Sin datos para el periodo seleccionado.")

st.divider()

# ── SECCION 2 — Especificaciones tecnicas ─────────────────────────────────────
seccion_titulo("Analisis de Especificaciones Tecnicas",
               "Distribucion de calibres y anchos — filtra por proceso y rango de calibre")

if not df_vl.empty and "CALIBRE" in df_vl.columns and "PROCESO" in df_vl.columns:
    col_e1, col_e2, col_e3 = st.columns([1, 1, 2])
    with col_e1:
        anio_esp = st.selectbox("Anio", options=["Todos"] + [str(a) for a in anios_mix], key="esp_anio")
    with col_e2:
        mes_esp_nombre = st.selectbox("Mes", options=meses_nombres, key="esp_mes", disabled=(anio_esp == "Todos"))

    df_vl_esp = df_vl.copy()
    df_vl_esp["CALIBRE"] = pd.to_numeric(df_vl_esp["CALIBRE"], errors="coerce")
    df_vl_esp["ANCHO"]   = pd.to_numeric(df_vl_esp.get("ANCHO", np.nan), errors="coerce")
    df_vl_esp = df_vl_esp.dropna(subset=["CALIBRE"])

    if anio_esp != "Todos":
        df_vl_esp = df_vl_esp[df_vl_esp["FECHAEMB"].dt.year == int(anio_esp)]
        mes_esp_num = meses_nombres.index(mes_esp_nombre)
        if mes_esp_num > 0:
            df_vl_esp = df_vl_esp[df_vl_esp["FECHAEMB"].dt.month == mes_esp_num]

    if df_vl_esp.empty:
        st.info("Sin datos para el periodo seleccionado.")
    else:
        col_e4, col_e5 = st.columns([1, 2])
        with col_e4:
            procesos_esp = sorted(df_vl_esp["PROCESO"].dropna().unique().tolist())
            proc_esp_sel = st.multiselect("Proceso(s):", options=procesos_esp, default=[], key="esp_proceso")
        with col_e5:
            cal_min = float(df_vl_esp["CALIBRE"].min())
            cal_max = float(df_vl_esp["CALIBRE"].max())
            if cal_min < cal_max:
                cal_rango = st.slider("Rango calibre (mm):", min_value=cal_min, max_value=cal_max,
                                       value=(cal_min, cal_max), step=0.1, key="esp_calibre")
            else:
                cal_rango = (cal_min, cal_max)

        df_esp = df_vl_esp.copy()
        if proc_esp_sel:
            df_esp = df_esp[df_esp["PROCESO"].isin(proc_esp_sel)]
        df_esp = df_esp[(df_esp["CALIBRE"] >= cal_rango[0]) & (df_esp["CALIBRE"] <= cal_rango[1])]

        if df_esp.empty:
            st.info("Sin datos con los filtros actuales.")
        else:
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            col_k1.metric("Registros",    f"{len(df_esp):,}")
            col_k2.metric("Calibre prom.", f"{df_esp['CALIBRE'].mean():.2f} mm")
            col_k3.metric("Toneladas",    f"{df_esp['PESO_TON'].sum():,.1f}")
            col_k4.metric("Procesos",     df_esp["PROCESO"].nunique())
            st.divider()

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                seccion_titulo("Distribucion de Calibres por Proceso", "")
                fig_box = px.box(df_esp, x="PROCESO", y="CALIBRE", color="PROCESO",
                                  color_discrete_sequence=COLOR_SEQUENCE,
                                  labels={"CALIBRE": "Calibre (mm)", "PROCESO": ""}, points=False)
                fig_box.update_layout(
                    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=10),
                    margin=dict(l=40, r=20, t=30, b=80), showlegend=False,
                    xaxis=dict(showgrid=False, tickangle=-25),
                    yaxis=dict(gridcolor="#E5E7EB", title="Calibre (mm)"), height=360,
                )
                st.plotly_chart(fig_box, width="stretch")

            with col_g2:
                seccion_titulo("Toneladas por Rango de Calibre", "")
                df_esp["RANGO_CAL"] = pd.cut(df_esp["CALIBRE"],
                                              bins=[0, 1.5, 3.0, 5.0, 8.0, 12.0, 20.0, 999],
                                              labels=["<1.5", "1.5-3", "3-5", "5-8", "8-12", "12-20", ">20"],
                                              right=False).astype(str)
                df_calp = df_esp.groupby(["PROCESO", "RANGO_CAL"], as_index=False)["PESO_TON"].sum()
                fig_cal = px.bar(df_calp, x="RANGO_CAL", y="PESO_TON", color="PROCESO", barmode="group",
                                  labels={"PESO_TON": "Toneladas", "RANGO_CAL": "Rango calibre (mm)", "PROCESO": "Proceso"},
                                  color_discrete_sequence=COLOR_SEQUENCE,
                                  category_orders={"RANGO_CAL": ["<1.5", "1.5-3", "3-5", "5-8", "8-12", "12-20", ">20"]})
                fig_cal.update_layout(
                    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=10),
                    margin=dict(l=40, r=20, t=30, b=60),
                    legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center", font=dict(size=9)),
                    xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB"), height=360,
                )
                st.plotly_chart(fig_cal, width="stretch")

            st.divider()
            seccion_titulo("Top Combinaciones Proceso + Calibre", "Por toneladas demandadas")
            df_combo_c = (
                df_esp.groupby(["PROCESO", "CALIBRE"], as_index=False)["PESO_TON"]
                .sum().sort_values("PESO_TON", ascending=False).head(15)
            )
            df_combo_c["COMBO"] = (df_combo_c["PROCESO"].astype(str) + "  |  " +
                                   df_combo_c["CALIBRE"].apply(lambda x: f"{x:.2f} mm"))
            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                fig_tc = go.Figure(go.Bar(
                    x=df_combo_c["PESO_TON"].iloc[::-1], y=df_combo_c["COMBO"].iloc[::-1],
                    orientation="h",
                    marker=dict(color=df_combo_c["PESO_TON"].iloc[::-1], colorscale=HEATMAP_COLORSCALE,
                                showscale=True, colorbar=dict(title="ton", thickness=12)),
                    text=df_combo_c["PESO_TON"].iloc[::-1].round(0), textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Toneladas: %{x:,.1f}<extra></extra>",
                ))
                fig_tc.update_layout(
                    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=9),
                    margin=dict(l=10, r=80, t=30, b=40),
                    xaxis=dict(title="Toneladas", gridcolor="#E5E7EB"),
                    yaxis=dict(tickfont=dict(size=9)), showlegend=False,
                    height=max(340, len(df_combo_c) * 28 + 60),
                    title=dict(text="Top 15: Proceso + Calibre",
                               font=dict(size=13, color=COLORS["primary"]), x=0),
                )
                st.plotly_chart(fig_tc, width="stretch")
            with col_c2:
                tabla_ejecutiva(df_combo_c[["PROCESO", "CALIBRE", "PESO_TON"]],
                                col_formatos={"CALIBRE": "{:.2f}", "PESO_TON": "{:,.1f}"},
                                key="top_combo_c", height=400)

            st.divider()
            seccion_titulo("Combinacion Especifica — Proceso + Calibre + Ancho", "")
            df_ancho = df_esp.dropna(subset=["ANCHO"]).copy() if "ANCHO" in df_esp.columns else pd.DataFrame()
            if not df_ancho.empty:
                df_c3 = (
                    df_ancho.groupby(["PROCESO", "CALIBRE", "ANCHO"], as_index=False)["PESO_TON"]
                    .sum().sort_values("PESO_TON", ascending=False).head(20).reset_index(drop=True)
                )
                df_c3["RANK"] = range(1, len(df_c3) + 1)
                df_c3["ESPECIFICACION"] = (df_c3["PROCESO"] + "  |  " +
                                           df_c3["CALIBRE"].apply(lambda x: f"{x:.2f}") + "mm x " +
                                           df_c3["ANCHO"].apply(lambda x: f"{x:.0f}mm"))
                col_d1, col_d2 = st.columns([2, 1])
                with col_d1:
                    fig_c3 = px.bar(df_c3, x="PESO_TON", y="ESPECIFICACION", orientation="h", color="PROCESO",
                                     color_discrete_sequence=COLOR_SEQUENCE,
                                     text=df_c3["PESO_TON"].round(0),
                                     labels={"PESO_TON": "Toneladas", "ESPECIFICACION": "", "PROCESO": "Proceso"},
                                     title="Top 20 combinaciones Proceso + Calibre + Ancho",
                                     category_orders={"ESPECIFICACION": df_c3["ESPECIFICACION"].iloc[::-1].tolist()})
                    fig_c3.update_traces(textposition="outside", textfont_size=8)
                    fig_c3.update_layout(
                        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=8),
                        margin=dict(l=10, r=80, t=50, b=40),
                        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center", font=dict(size=9)),
                        xaxis=dict(title="Toneladas", gridcolor="#E5E7EB"), yaxis=dict(tickfont=dict(size=7)),
                        height=max(420, len(df_c3) * 26 + 80),
                        title=dict(font=dict(size=13, color=COLORS["primary"]), x=0),
                    )
                    st.plotly_chart(fig_c3, width="stretch")
                with col_d2:
                    tabla_ejecutiva(df_c3[["RANK", "PROCESO", "CALIBRE", "ANCHO", "PESO_TON"]],
                                    col_formatos={"CALIBRE": "{:.2f}", "ANCHO": "{:.0f}", "PESO_TON": "{:,.1f}"},
                                    key="top_c3", height=480)
            else:
                st.info("Sin datos de ancho disponibles.")
else:
    st.info("Sin datos de especificaciones. Verifica que ventas_limpias contenga CALIBRE y PROCESO.")

st.divider()

# ── SECCION 3 — Co-ocurrencia ─────────────────────────────────────────────────
df_cp_cooc = df_cp_base.copy()
if clientes_sel:
    df_cp_cooc = aplicar_filtro_lista(df_cp_cooc, clientes_sel, "CLIENTE")

seccion_titulo("Co-ocurrencia de Productos", "Clientes que compran ambos productos")
df_cooc = tabla_coocurrencia(df_cp_cooc)
if not df_cooc.empty:
    fig_cooc = heatmap(df_cooc, titulo="Co-ocurrencia de productos (n clientes)",
                        x_label="Producto", y_label="Producto", fmt=".0f")
    st.plotly_chart(fig_cooc, width="stretch")

seccion_titulo("Pares Frecuentes", f"Productos comprados juntos por >= {min_clientes_combo} clientes")
df_combos = combinaciones_frecuentes(df_cp_cooc, min_clientes=min_clientes_combo)
if not df_combos.empty:
    tabla_ejecutiva(df_combos, col_formatos={"N_CLIENTES": "{:,}"}, key="combos_frecuentes", height=300)
else:
    st.info("Sin pares con el umbral actual.")

st.divider()

# ── SECCION 4 — Cross-sell ────────────────────────────────────────────────────
seccion_titulo("Oportunidades de Cross-sell", "Productos populares que el cliente aun no compra")
df_cs = oportunidades_crosssell(df_cp_cooc, min_soporte=0.10)
if not df_cs.empty:
    tabla_ejecutiva(df_cs, col_formatos={"N_CLIENTES_LO_COMPRAN": "{:,}"},
                    key="crosssell_oport", height=400)
    st.caption("Productos que >= 10% de clientes activos compran y el cliente aun no ha adquirido.")
else:
    st.info("Sin oportunidades de cross-sell con los parametros actuales.")
