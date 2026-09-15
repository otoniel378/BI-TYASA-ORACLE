"""
03_series_tiempo.py — Series de Tiempo — Aceros Planos Negros.
"""

import os, sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from config import COLORS, COLOR_SEQUENCE

from aceros_planos.negros.loaders import (
    load_gold_demanda_mensual,
    load_gold_demanda_mensual_total,
    load_serie_mensual_proceso,
    load_serie_mensual_cliente,
)

# Quiebres de mercado — carga silenciosa para C2 (event overlay)
_df_quiebres = pd.DataFrame()
try:
    from aceros_planos.negros.loaders_contexto import load_quiebres_relevantes_planos
    _df_quiebres = load_quiebres_relevantes_planos()
except Exception:
    pass
from aceros_planos.negros.analytics.series_tiempo import (
    preparar_serie_mensual,
    calcular_variacion_mensual,
    calcular_volatilidad,
    top_afectados_variacion,
)
from core.components.kpi_cards import render_kpi_row, seccion_titulo
from core.components.filters import sidebar_header
from core.components.charts import linea_temporal
from core.components.tables import tabla_ejecutiva

sidebar_header("Series de Tiempo")

with st.spinner("Cargando datos..."):
    df_mensual_total = load_gold_demanda_mensual_total()
    df_mensual_gran  = load_gold_demanda_mensual()
    df_proceso_ts    = load_serie_mensual_proceso()
    df_cliente_ts    = load_serie_mensual_cliente()

def _anios_de(df):
    if df.empty or "PERIODO" not in df.columns:
        return []
    col = pd.to_datetime(df["PERIODO"], errors="coerce")
    return sorted(col.dropna().dt.year.unique().tolist(), reverse=True)

anios_total = _anios_de(df_mensual_total)

st.markdown(
    f"""
    <h2 style='color:{COLORS["primary"]};margin-bottom:0;'>Series de Tiempo</h2>
    <p style='color:{COLORS["text_light"]};'>Comportamiento temporal de la demanda de Aceros Planos Negros</p>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ── SECCION 1 — Serie mensual total ──────────────────────────────────────────
seccion_titulo("Serie Mensual Total", "Toneladas acumuladas por mes")

col_s1, col_s2, _ = st.columns([1, 1, 4])
with col_s1:
    anio_ini_sel = st.selectbox("Desde anio", options=["Todos"] + [str(a) for a in anios_total], key="st_anio_ini")
with col_s2:
    anio_fin_sel = st.selectbox("Hasta anio", options=["Todos"] + [str(a) for a in anios_total], index=0, key="st_anio_fin")

df_tot_f = df_mensual_total.copy()
if "PERIODO" in df_tot_f.columns:
    df_tot_f["PERIODO"] = pd.to_datetime(df_tot_f["PERIODO"], errors="coerce")
    if anio_ini_sel != "Todos":
        df_tot_f = df_tot_f[df_tot_f["PERIODO"].dt.year >= int(anio_ini_sel)]
    if anio_fin_sel != "Todos":
        df_tot_f = df_tot_f[df_tot_f["PERIODO"].dt.year <= int(anio_fin_sel)]

serie = preparar_serie_mensual(df_tot_f)
serie_var = calcular_variacion_mensual(serie)

if not serie_var.empty:
    ult = serie_var.iloc[-1]
    render_kpi_row([
        {"label": "Ultimo mes",       "value": ult["PESO_TON"], "suffix": " ton",
         "delta": ult.get("VAR_MOM_PCT"), "delta_label": "MoM"},
        {"label": "Promedio mensual", "value": round(serie_var["PESO_TON"].mean(), 1), "suffix": " ton"},
        {"label": "Maximo",           "value": round(serie_var["PESO_TON"].max(), 1),  "suffix": " ton"},
        {"label": "Minimo",           "value": round(serie_var["PESO_TON"].min(), 1),  "suffix": " ton"},
    ])

    # C1 — Vista toggle + C2 — overlay de quiebres
    c_vis, c_ovr = st.columns([3, 1])
    with c_vis:
        vista_st = st.radio("Vista:", ["Absoluta", "YoY %", "Índice base=100"],
                            horizontal=True, key="st_vista_serie", label_visibility="collapsed")
    with c_ovr:
        overlay_q = st.checkbox("Mostrar quiebres de mercado", value=True, key="st_overlay_q") \
                    if not _df_quiebres.empty else False

    sv = serie_var.copy()
    sv["PERIODO"] = pd.to_datetime(sv["PERIODO"], errors="coerce")
    sv = sv.sort_values("PERIODO")

    if vista_st == "Absoluta":
        fig_serie = linea_temporal(sv, x="PERIODO", y="PESO_TON",
                                   titulo="Demanda mensual total", show_area=True)
    elif vista_st == "YoY %":
        sv2 = sv.set_index("PERIODO")
        sv2["YoY"] = sv2["PESO_TON"].pct_change(12) * 100
        sv2 = sv2.dropna(subset=["YoY"]).reset_index()
        if sv2.empty:
            st.info("Insuficientes datos para YoY (mínimo 13 meses).")
            sv2 = sv.copy()
            sv2["YoY"] = 0.0
        colors_b = [COLORS["success"] if v >= 0 else COLORS["danger"] for v in sv2.get("YoY", [])]
        fig_serie = go.Figure(go.Bar(
            x=sv2.get("PERIODO", pd.Series()), y=sv2.get("YoY", pd.Series()),
            marker_color=colors_b, name="YoY %",
            hovertemplate="%{x|%b %Y}<br>YoY: %{y:.1f}%<extra></extra>",
        ))
        fig_serie.add_hline(y=0, line_dash="dot", line_color=COLORS["neutral"], line_width=1)
        fig_serie.update_layout(
            paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
            font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
            margin=dict(l=40, r=20, t=30, b=40), showlegend=False, height=320,
            xaxis=dict(showgrid=False), yaxis=dict(title="YoY (%)", gridcolor="#E5E7EB"),
        )
    else:  # Índice base=100
        base = float(sv["PESO_TON"].iloc[0]) if not sv.empty and float(sv["PESO_TON"].iloc[0]) != 0 else 1
        sv["Indice"] = sv["PESO_TON"] / base * 100
        fig_serie = linea_temporal(sv, x="PERIODO", y="Indice",
                                   titulo="Índice base=100 (primer mes del período)", show_area=False)
        fig_serie.add_hline(y=100, line_dash="dot", line_color=COLORS["neutral"], line_width=1)

    # C2 — Añadir líneas verticales de quiebres activos
    if overlay_q and not _df_quiebres.empty and "fecha_inicio" in _df_quiebres.columns:
        q_dates = pd.to_datetime(_df_quiebres["fecha_inicio"], errors="coerce").dropna().unique()
        for qd in q_dates[:5]:
            var_q = ""
            row_q = _df_quiebres[pd.to_datetime(_df_quiebres["fecha_inicio"], errors="coerce") == qd]
            if not row_q.empty and "variable" in row_q.columns:
                var_q = row_q.iloc[0]["variable"]
            fig_serie.add_vline(
                x=qd, line_dash="dash", line_color="#F59E0B", line_width=1.5,
                annotation_text=var_q[:15], annotation_position="top right",
                annotation_font_size=9, annotation_font_color="#92400E",
            )

    fig_serie.update_layout(height=320)
    st.plotly_chart(fig_serie, width="stretch")
else:
    st.warning("Sin datos para el periodo seleccionado.")

# ── SECCION 2 — Variacion mensual ────────────────────────────────────────────
st.divider()
seccion_titulo("Variacion Mensual (%)", "Cambio porcentual respecto al mes anterior")

if not serie_var.empty and "VAR_MOM_PCT" in serie_var.columns:
    df_var = serie_var.dropna(subset=["VAR_MOM_PCT"]).copy()
    df_var["COLOR"] = df_var["VAR_MOM_PCT"].apply(lambda v: COLORS["success"] if v >= 0 else COLORS["danger"])
    fig_var = go.Figure()
    fig_var.add_trace(go.Bar(x=df_var["PERIODO"], y=df_var["VAR_MOM_PCT"], marker_color=df_var["COLOR"],
                              hovertemplate="%{x|%b %Y}<br>Variacion: %{y:.1f}%<extra></extra>"))
    fig_var.add_hline(y=0, line_color=COLORS["neutral"], line_width=1)
    fig_var.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis=dict(showgrid=False), yaxis=dict(title="Variacion (%)", gridcolor="#E5E7EB"),
        showlegend=False, height=280,
    )
    st.plotly_chart(fig_var, width="stretch")

# ── C3 — Índice Estacional ───────────────────────────────────────────────────
st.divider()
seccion_titulo("Índice Estacional por Mes", "Cuánto vende cada mes respecto al promedio anual (base=100)")

if not serie_var.empty and "PESO_TON" in serie_var.columns:
    _sv_est = serie_var.copy()
    _sv_est["PERIODO"] = pd.to_datetime(_sv_est["PERIODO"], errors="coerce")
    _sv_est = _sv_est.dropna(subset=["PERIODO"])
    if "ANIO" not in _sv_est.columns:
        _sv_est["ANIO"] = _sv_est["PERIODO"].dt.year
    if "MES" not in _sv_est.columns:
        _sv_est["MES"] = _sv_est["PERIODO"].dt.month

    avg_anual = _sv_est.groupby("ANIO")["PESO_TON"].mean()
    _sv_est["avg_anio"] = _sv_est["ANIO"].map(avg_anual)
    _sv_est["idx_est"]  = _sv_est["PESO_TON"] / _sv_est["avg_anio"].replace(0, float("nan")) * 100
    idx_mes = _sv_est.groupby("MES")["idx_est"].mean().reset_index()
    idx_mes.columns = ["MES", "Índice"]

    MESES_LABEL = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
                   "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    idx_mes["Mes_lbl"] = idx_mes["MES"].apply(lambda m: MESES_LABEL[int(m)] if 1 <= int(m) <= 12 else str(m))
    idx_mes["Color"] = idx_mes["Índice"].apply(
        lambda v: COLORS["success"] if v >= 105 else (COLORS["danger"] if v <= 95 else COLORS["neutral"])
    )

    fig_est = go.Figure(go.Bar(
        x=idx_mes["Mes_lbl"], y=idx_mes["Índice"],
        marker_color=idx_mes["Color"].tolist(),
        text=idx_mes["Índice"].apply(lambda v: f"{v:.0f}"),
        textposition="outside", textfont=dict(size=9),
        hovertemplate="%{x}<br>Índice: %{y:.1f}<extra></extra>",
    ))
    fig_est.add_hline(y=100, line_dash="dot", line_color="#64748B", line_width=1.5,
                      annotation_text="Promedio=100", annotation_font_size=9)
    fig_est.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=11),
        margin=dict(l=40, r=20, t=30, b=30), showlegend=False, height=270,
        xaxis=dict(showgrid=False), yaxis=dict(title="Índice (100 = promedio)", gridcolor="#E5E7EB"),
    )
    st.plotly_chart(fig_est, width="stretch")
    _idx_max = idx_mes.loc[idx_mes["Índice"].idxmax(), "Mes_lbl"]
    _idx_min = idx_mes.loc[idx_mes["Índice"].idxmin(), "Mes_lbl"]
    st.caption(f"Mes más alto: **{_idx_max}** · Mes más bajo: **{_idx_min}** · "
               f"Estacionalidad calculada sobre {_sv_est['ANIO'].nunique()} años de datos.")

def _filtrar_anios(df, col="PERIODO"):
    if df.empty or col not in df.columns:
        return df
    d = df.copy()
    d[col] = pd.to_datetime(d[col], errors="coerce")
    if anio_ini_sel != "Todos":
        d = d[d[col].dt.year >= int(anio_ini_sel)]
    if anio_fin_sel != "Todos":
        d = d[d[col].dt.year <= int(anio_fin_sel)]
    return d

df_gran_f = _filtrar_anios(df_mensual_gran)
df_proc_f = _filtrar_anios(df_proceso_ts)
df_cli_f  = _filtrar_anios(df_cliente_ts)

col_p, col_proc, col_cli = st.columns(3)

def _render_top(df, col_dim, titulo, key_suffix):
    if df.empty or col_dim not in df.columns:
        st.info("Sin datos.")
        return
    top = top_afectados_variacion(df, col_dim)
    if top.empty:
        st.info("Sin datos suficientes.")
        return
    top["DIMENSION"] = top["DIMENSION"].astype(str).str[:30]
    top["VAR_ABS"] = top["VAR_ABS"].round(1)
    top["VAR_PCT_STR"] = top["VAR_PCT"].apply(
        lambda v: f"+{v:.1f}%" if pd.notna(v) and v > 0 else (f"{v:.1f}%" if pd.notna(v) else "—")
    )
    st.dataframe(
        top[["DIMENSION", "VAR_ABS", "VAR_PCT_STR"]].rename(
            columns={"DIMENSION": titulo, "VAR_ABS": "Var (ton)", "VAR_PCT_STR": "Var %"}
        ),
        hide_index=True, width="stretch", height=310,
    )

with col_p:
    st.markdown("**Productos**")
    _render_top(df_gran_f, "PRODUCTO_LIMPIO", "Producto", "prod")
with col_proc:
    st.markdown("**Procesos**")
    _render_top(df_proc_f, "PROCESO", "Proceso", "proc")
with col_cli:
    st.markdown("**Clientes**")
    _render_top(df_cli_f, "CLIENTE", "Cliente", "cli")

# ── SECCION 3 — Tendencia por producto ───────────────────────────────────────
st.divider()
seccion_titulo("Tendencia Mensual por Producto", "Evolucion historica por tipo de producto")

excluir_prods = {"OTROS", "OTHER", "N/D", "SIN CLASIFICAR", "S/C"}
df_gran_clean = df_gran_f.copy()
if "PRODUCTO_LIMPIO" in df_gran_clean.columns:
    df_gran_clean = df_gran_clean[~df_gran_clean["PRODUCTO_LIMPIO"].str.upper().isin(excluir_prods)]

prods_disponibles = sorted(df_gran_clean["PRODUCTO_LIMPIO"].dropna().unique().tolist()) if not df_gran_clean.empty else []

col_t1, col_t2, _ = st.columns([2, 1, 3])
with col_t1:
    prods_sel = st.multiselect("Productos a mostrar", options=prods_disponibles,
                                default=prods_disponibles[:min(8, len(prods_disponibles))], key="tend_prods")
with col_t2:
    tipo_linea = st.selectbox("Tipo", ["Lineas", "Area apilada"], key="tend_tipo")

if not df_gran_clean.empty and prods_sel:
    df_tend = df_gran_clean[df_gran_clean["PRODUCTO_LIMPIO"].isin(prods_sel)].copy()
    if tipo_linea == "Area apilada":
        fig_tend = px.area(df_tend, x="PERIODO", y="PESO_TON", color="PRODUCTO_LIMPIO",
                            color_discrete_sequence=COLOR_SEQUENCE,
                            labels={"PESO_TON": "Toneladas", "PERIODO": "", "PRODUCTO_LIMPIO": "Producto"},
                            title="Tendencia mensual por producto (area apilada)")
    else:
        fig_tend = px.line(df_tend, x="PERIODO", y="PESO_TON", color="PRODUCTO_LIMPIO",
                            color_discrete_sequence=COLOR_SEQUENCE,
                            labels={"PESO_TON": "Toneladas", "PERIODO": "", "PRODUCTO_LIMPIO": "Producto"},
                            title="Tendencia mensual por producto")
        fig_tend.update_traces(line_width=2)

    fig_tend.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=11),
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center", font=dict(size=10), title_text=""),
        height=420, xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB", title="Toneladas"),
        title=dict(font=dict(size=14, color=COLORS["primary"]), x=0),
    )
    st.plotly_chart(fig_tend, width="stretch")
elif not prods_sel:
    st.info("Selecciona al menos un producto.")

# ── SECCION 4 — Volatilidad ───────────────────────────────────────────────────
st.divider()
seccion_titulo("Variabilidad por Producto", "Coeficiente de variacion mensual (CV menor = mas estable)")

if not df_gran_clean.empty and "PRODUCTO_LIMPIO" in df_gran_clean.columns:
    col_v1, _ = st.columns([2, 4])
    with col_v1:
        prods_vol_sel = st.multiselect("Incluir productos", options=prods_disponibles,
                                        default=prods_disponibles, key="vol_prods")

    df_vol_input = df_gran_clean.copy()
    if prods_vol_sel:
        df_vol_input = df_vol_input[df_vol_input["PRODUCTO_LIMPIO"].isin(prods_vol_sel)]

    df_vol = calcular_volatilidad(df_vol_input, col_dim="PRODUCTO_LIMPIO", col_val="PESO_TON")

    if not df_vol.empty:
        color_map = {"Alta": COLORS["success"], "Media": COLORS["warning"], "Baja": COLORS["danger"]}
        df_vp = df_vol.sort_values("CV", ascending=True).copy()

        fig_vol = go.Figure()
        for est, color in color_map.items():
            sub = df_vp[df_vp["ESTABILIDAD"] == est]
            if sub.empty:
                continue
            fig_vol.add_trace(go.Bar(
                x=sub["CV"], y=sub["DIMENSION"], orientation="h", name=f"Estabilidad {est}",
                marker_color=color, text=sub["CV"].apply(lambda v: f"{v:.1f}%"),
                textposition="outside", textfont=dict(size=9),
                hovertemplate="<b>%{y}</b><br>CV: %{x:.1f}%<extra></extra>",
            ))

        fig_vol.update_layout(
            paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
            font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=10),
            margin=dict(l=10, r=90, t=50, b=40),
            legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
            height=max(320, len(df_vp) * 34 + 80), barmode="overlay",
            xaxis=dict(title="CV (%)", gridcolor="#E5E7EB"), yaxis=dict(tickfont=dict(size=9)),
            title=dict(text="Ranking de estabilidad — menor CV es mas estable",
                       font=dict(size=13, color=COLORS["primary"]), x=0),
        )
        st.plotly_chart(fig_vol, width="stretch")
        tabla_ejecutiva(
            df_vol[["DIMENSION", "MEDIA", "STD", "CV", "ESTABILIDAD"]].rename(
                columns={"DIMENSION": "PRODUCTO", "MEDIA": "PROM_TON", "STD": "DESV_STD"}
            ),
            col_formatos={"PROM_TON": "{:,.1f}", "DESV_STD": "{:,.1f}", "CV": "{:.1f}%"},
            key="estabilidad_prod", height=300,
        )

# ── Tabla exportable ──────────────────────────────────────────────────────────
st.divider()
seccion_titulo("Serie Historica Completa", "Exportable en Excel")
if not serie_var.empty:
    cols_exp = [c for c in ["PERIODO", "ANIO", "MES", "PESO_TON", "VAR_MOM", "VAR_MOM_PCT"] if c in serie_var.columns]
    tabla_ejecutiva(serie_var[cols_exp],
                    col_formatos={"PESO_TON": "{:,.1f}", "VAR_MOM": "{:,.1f}", "VAR_MOM_PCT": "{:.1f}%"},
                    key="serie_historica", height=380)
