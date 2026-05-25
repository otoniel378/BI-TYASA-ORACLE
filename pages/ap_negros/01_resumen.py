"""
01_resumen.py — Resumen Ejecutivo — Aceros Planos Negros.
Vision 360: KPIs, tendencia mensual, participacion por producto, top clientes y top productos.
"""

import os, sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config import APP_NAME, COLORS

from aceros_planos.negros.loaders import (
    load_gold_demanda_cliente,
    load_gold_demanda_producto,
    load_gold_demanda_mensual,
    load_gold_demanda_mensual_total,
)
from aceros_planos.negros.analytics.kpis import calcular_kpis_resumen, calcular_top_n, calcular_participacion
from aceros_planos.negros.analytics.series_tiempo import preparar_serie_mensual
from core.components.kpi_cards import render_kpi_row, seccion_titulo
from core.components.filters import sidebar_header, filtro_rango_fechas, aplicar_filtro_fechas
from core.components.charts import linea_temporal, barras_horizontales, barras_verticales, donut
from core.components.tables import tabla_ejecutiva

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
sidebar_header("Filtros", "📊")
fecha_inicio, fecha_fin = filtro_rango_fechas(key_prefix="re")

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------
with st.spinner("Cargando datos..."):
    df_cliente  = load_gold_demanda_cliente()
    df_producto = load_gold_demanda_producto()
    df_mensual  = load_gold_demanda_mensual_total()

df_mensual_f = aplicar_filtro_fechas(df_mensual, fecha_inicio, fecha_fin, col="PERIODO")

# Contexto externo — carga silenciosa para A1 (gauge) y A3 (mini-panel)
_ctx_ok  = False
_df_vars = pd.DataFrame()
_df_ine  = pd.DataFrame()
try:
    from aceros_planos.negros.loaders_contexto import (
        load_vars_mercado_planos,
        load_alertas_inegi_planos,
    )
    _df_vars = load_vars_mercado_planos(dias=90)
    _df_ine  = load_alertas_inegi_planos()
    _ctx_ok  = True
except Exception:
    pass

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <h2 style='color:{COLORS["primary"]};margin-bottom:0;'>📊 Resumen Ejecutivo</h2>
    <p style='color:{COLORS["text_light"]};'>Aceros Planos Negros — Demanda historica</p>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ---------------------------------------------------------------------------
# KPIs principales
# ---------------------------------------------------------------------------
kpis_data = calcular_kpis_resumen(df_cliente, df_producto, df_mensual_f)

render_kpi_row([
    {"label": "Toneladas Totales",     "value": kpis_data.toneladas_totales, "suffix": " ton",  "icon": "⚖️",
     "help_text": "Suma total de toneladas en el periodo seleccionado."},
    {"label": "Clientes Activos",      "value": kpis_data.clientes_activos,  "icon": "👥",
     "help_text": "Numero de clientes con al menos un embarque."},
    {"label": "Productos Activos",     "value": kpis_data.productos_activos, "icon": "🔩",
     "help_text": "Numero de productos unicos vendidos."},
    {"label": "Ticket Prom. / Cliente","value": kpis_data.ticket_promedio,   "suffix": " ton",  "icon": "📦",
     "delta": kpis_data.variacion_mom, "delta_label": "vs mes anterior",
     "help_text": "Toneladas promedio por cliente activo."},
])

st.markdown("")
col1, col2 = st.columns(2)
with col1:
    st.metric("Top cliente",  kpis_data.top_cliente  or "—")
with col2:
    st.metric("Top producto", kpis_data.top_producto or "—")

# Exportar KPIs al contexto acumulativo del sistema
try:
    from core.chat_widget import actualizar_contexto_sistema
    actualizar_contexto_sistema("negros_kpis", {
        "pagina":            "Resumen Ejecutivo — Aceros Planos Negros",
        "toneladas_totales": round(float(kpis_data.toneladas_totales or 0), 1),
        "clientes_activos":  int(kpis_data.clientes_activos or 0),
        "productos_activos": int(kpis_data.productos_activos or 0),
        "ticket_promedio":   round(float(kpis_data.ticket_promedio or 0), 1),
        "variacion_mom_pct": round(float(kpis_data.variacion_mom or 0), 1),
        "top_cliente":       kpis_data.top_cliente or "",
        "top_producto":      kpis_data.top_producto or "",
    })
except Exception:
    pass

# ---------------------------------------------------------------------------
# A1 + A3 — Gauge ICC + Mini-panel contexto externo
# ---------------------------------------------------------------------------
if _ctx_ok:
    from aceros_planos.negros.analytics.contexto_mercado import calcular_indice_condicion_comercial
    icc = calcular_indice_condicion_comercial(_df_vars, _df_ine)

    _OK = "#16A34A"; _WA = "#D97706"; _ER = "#DC2626"; _T2 = "#64748B"; _T3 = "#94A3B8"

    col_g, col_m = st.columns([1, 3])

    with col_g:
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=icc["indice"],
            number={"font": {"size": 28, "color": icc["color"]}, "suffix": "/10"},
            title={"text": f"<b>ICC: {icc['nivel']}</b>",
                   "font": {"size": 11, "color": icc["color"]}},
            gauge={
                "axis": {"range": [0, 10], "tickfont": {"size": 9}},
                "bar":  {"color": icc["color"], "thickness": 0.25},
                "bgcolor": "white", "borderwidth": 0,
                "steps": [
                    {"range": [0,   4],  "color": "#FEE2E2"},
                    {"range": [4,   6.5],"color": "#FEF3C7"},
                    {"range": [6.5, 10], "color": "#DCFCE7"},
                ],
            },
        ))
        fig_g.update_layout(
            height=180, margin=dict(t=24, b=0, l=10, r=10),
            paper_bgcolor="white",
            font=dict(family="Segoe UI, sans-serif"),
        )
        st.plotly_chart(fig_g, use_container_width=True, config={"displayModeBar": False})

    with col_m:
        # A3 — 4 mini-cards de contexto externo
        def _last_mkt(nombre):
            if _df_vars.empty or "nombre" not in _df_vars.columns:
                return None, 0.0
            sub = _df_vars[_df_vars["nombre"] == nombre].sort_values("fecha")
            vals = pd.to_numeric(sub["valor"], errors="coerce").dropna()
            if vals.empty:
                return None, 0.0
            v  = float(vals.iloc[-1])
            d7 = (v - float(vals.iloc[-8])) / abs(float(vals.iloc[-8])) * 100 \
                 if len(vals) >= 8 and float(vals.iloc[-8]) != 0 else 0.0
            return v, d7

        def _last_inegi(clave):
            if _df_ine.empty or "Clave" not in _df_ine.columns:
                return None, "Normal"
            row = _df_ine[_df_ine["Clave"] == clave]
            if row.empty:
                return None, "Normal"
            return row.iloc[0].get("ult_valor"), str(row.iloc[0].get("alerta", "Normal"))

        _COL_A = {"Normal": _OK, "Moderado": _WA, "Alto": _WA, "Critico": _ER}

        cards_info = [
            ("ETF Acero Global", *_last_mkt("ETF_Acero_Global"), "mkt", ".2f"),
            ("USD / MXN",        *_last_mkt("USD_MXN"),           "mkt", ".4f"),
            ("IMAI Manufactura", *_last_inegi("736418"),           "ine", ""),
            ("IGAE Sec. Var%",   *_last_inegi("737149"),           "ine", ""),
        ]

        mc_cols = st.columns(4)
        for i, info in enumerate(cards_info):
            lbl, val, extra, src, fmt = info
            with mc_cols[i]:
                if val is None:
                    st.html(f"""<div style="background:#F8FAFC;border-radius:10px;
                         padding:10px 12px;border:1px solid #E2E8F0;text-align:center;">
                      <div style="font-size:9.5px;font-weight:700;color:{_T3};
                           text-transform:uppercase;margin-bottom:4px;">{lbl}</div>
                      <div style="font-size:16px;font-weight:800;color:{_T3};">N/D</div>
                    </div>""")
                    continue
                if src == "mkt":
                    d7    = extra
                    col_d = _OK if d7 >= 0 else _ER
                    icon  = "▲" if d7 >= 0 else "▼"
                    val_s = f"{float(val):{fmt}}"
                    sub_s = f'<span style="color:{col_d};font-size:10px;">{icon} {abs(d7):.1f}% 7d</span>'
                else:
                    alerta = extra
                    col_d  = _COL_A.get(alerta, _T3)
                    val_s  = f"{float(val):.1f}"
                    sub_s  = f'<span style="color:{col_d};font-size:10px;">{alerta}</span>'

                st.html(f"""<div style="background:#F8FAFC;border-radius:10px;
                     padding:10px 12px;border:1px solid #E2E8F0;border-left:3px solid {col_d};">
                  <div style="font-size:9.5px;font-weight:700;color:{_T3};
                       text-transform:uppercase;margin-bottom:3px;">{lbl}</div>
                  <div style="font-size:17px;font-weight:800;color:#0F172A;">{val_s}</div>
                  {sub_s}
                </div>""")

st.divider()

# ---------------------------------------------------------------------------
# Fila 1: Tendencia mensual + Participacion por Producto
# ---------------------------------------------------------------------------
df_part = calcular_participacion(df_producto, "PRODUCTO_LIMPIO")

col_trend, col_part = st.columns([2, 1])

with col_trend:
    seccion_titulo("Tendencia Mensual de Demanda", "Serie de toneladas por mes")
    if df_mensual_f.empty:
        st.warning("Sin datos para el periodo seleccionado.")
    else:
        serie = preparar_serie_mensual(df_mensual_f)

        # A2 — toggle Absoluta / YoY % / Índice
        vista = st.radio("Vista:", ["Absoluta", "YoY %", "Índice base=100"],
                         horizontal=True, key="re_vista_trend", label_visibility="collapsed")

        if vista == "Absoluta":
            fig_linea = linea_temporal(serie, x="PERIODO", y="PESO_TON",
                                       titulo="Toneladas mensuales", show_area=True)
            fig_linea.update_layout(height=260)
            st.plotly_chart(fig_linea, use_container_width=True)

        elif vista == "YoY %":
            s = serie.copy()
            s["PERIODO"] = pd.to_datetime(s["PERIODO"], errors="coerce")
            s = s.sort_values("PERIODO").set_index("PERIODO")
            s["YoY"] = s["PESO_TON"].pct_change(12) * 100
            s = s.dropna(subset=["YoY"]).reset_index()
            if s.empty:
                st.info("Insuficientes datos para calcular YoY (mínimo 13 meses).")
            else:
                colors_bar = [("#16A34A" if v >= 0 else "#DC2626") for v in s["YoY"]]
                fig_yoy = go.Figure(go.Bar(
                    x=s["PERIODO"], y=s["YoY"],
                    marker_color=colors_bar, name="Var. YoY %",
                ))
                fig_yoy.update_layout(
                    height=260, margin=dict(t=10, b=10, l=10, r=10),
                    yaxis_title="Variación YoY (%)", paper_bgcolor="white",
                    plot_bgcolor="#F8FAFC", font=dict(family="Segoe UI, sans-serif", size=11),
                    xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#EEF2FF"),
                )
                fig_yoy.add_hline(y=0, line_dash="dot", line_color="#94A3B8", line_width=1)
                st.plotly_chart(fig_yoy, use_container_width=True,
                                config={"displayModeBar": False})

        else:  # Índice base=100
            s = serie.copy()
            s["PERIODO"] = pd.to_datetime(s["PERIODO"], errors="coerce")
            s = s.sort_values("PERIODO")
            base = float(s["PESO_TON"].iloc[0]) if not s.empty and float(s["PESO_TON"].iloc[0]) != 0 else 1
            s["Indice"] = s["PESO_TON"] / base * 100
            fig_idx = linea_temporal(s, x="PERIODO", y="Indice",
                                     titulo="Índice (primer mes = 100)", show_area=False)
            fig_idx.update_layout(height=260)
            fig_idx.add_hline(y=100, line_dash="dot", line_color="#94A3B8", line_width=1)
            st.plotly_chart(fig_idx, use_container_width=True)

with col_part:
    if not df_part.empty:
        seccion_titulo("Participacion por Producto", "")
        fig_barras = barras_verticales(df_part.head(10), x="PRODUCTO_LIMPIO", y="PESO_TON",
                                       titulo="", x_label="", y_label="Toneladas")
        fig_barras.update_layout(height=290, xaxis_tickangle=-45)
        st.plotly_chart(fig_barras, use_container_width=True)

# ---------------------------------------------------------------------------
# Fila 2: Donut Mixto + Comparación Mes x Año (lado a lado)
# ---------------------------------------------------------------------------
col_donut, col_yoy = st.columns([1, 2])

with col_donut:
    if not df_part.empty:
        seccion_titulo("Mix por Producto", "")
        fig_donut = donut(df_part.head(8), names="PRODUCTO_LIMPIO", values="PESO_TON", titulo="")
        fig_donut.update_layout(height=260, legend_orientation="h", legend_y=-0.25)
        st.plotly_chart(fig_donut, use_container_width=True)

with col_yoy:
    if not df_mensual_f.empty:
        serie_yoy = preparar_serie_mensual(df_mensual_f)
        if "ANIO" in serie_yoy.columns and "MES" in serie_yoy.columns:
            df_yoy = serie_yoy.copy()
            df_yoy["AÑO"] = df_yoy["ANIO"].astype(str)
            df_yoy = df_yoy.sort_values(["ANIO", "MES"])
            seccion_titulo("Comparación Mes a Mes por Año", "Estacionalidad y patrones anuales")
            fig_yoy = linea_temporal(df_yoy, x="MES", y="PESO_TON", color="AÑO", titulo="", y_label="Ton")
            fig_yoy.update_layout(
                height=260,
                xaxis=dict(
                    tickmode="array",
                    tickvals=list(range(1, 13)),
                    ticktext=["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                              "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
                ),
            )
            st.plotly_chart(fig_yoy, use_container_width=True)

# ---------------------------------------------------------------------------
# Top 10 Clientes y Top 10 Productos
# ---------------------------------------------------------------------------
col_c, col_d = st.columns(2)

with col_c:
    seccion_titulo("Top 10 Clientes", "Por volumen de toneladas")
    top_clientes = calcular_top_n(df_cliente, "CLIENTE", n=10)
    if not top_clientes.empty:
        fig_cli = barras_horizontales(top_clientes, x="PESO_TON", y="CLIENTE", x_label="Toneladas")
        st.plotly_chart(fig_cli, use_container_width=True)

with col_d:
    seccion_titulo("Top 10 Productos", "Por volumen de toneladas")
    top_prod = calcular_top_n(df_producto, "PRODUCTO_LIMPIO", n=10)
    if not top_prod.empty:
        fig_prod = barras_horizontales(top_prod, x="PESO_TON", y="PRODUCTO_LIMPIO", x_label="Toneladas")
        st.plotly_chart(fig_prod, use_container_width=True)

# ---------------------------------------------------------------------------
# Tabla resumen
# ---------------------------------------------------------------------------
st.divider()
seccion_titulo("Tabla Resumen por Cliente", "Descargable en Excel")

df_resumen = df_cliente.copy() if not df_cliente.empty else pd.DataFrame()
if not df_resumen.empty:
    tabla_ejecutiva(df_resumen.sort_values("PESO_TON", ascending=False),
                    col_formatos={"PESO_TON": "{:,.1f}"}, key="resumen_clientes")
