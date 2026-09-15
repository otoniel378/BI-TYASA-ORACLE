"""
02_segmentacion.py — Segmentacion de Clientes — Aceros Planos Negros.
Clasificacion ABC, Pareto y diversificacion de portafolio.
"""

import os, sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.express as px
from config import APP_NAME, COLORS, COLOR_SEQUENCE

from aceros_planos.negros.loaders import (
    load_gold_demanda_cliente,
    load_gold_cliente_producto,
    load_ventas_limpias,
)
from aceros_planos.negros.analytics.segmentacion import (
    clasificar_abc,
    resumen_abc,
    calcular_diversificacion,
    clientes_monoproducto,
)
from core.components.kpi_cards import render_kpi_row, seccion_titulo
from core.components.filters import sidebar_header, filtro_clientes, aplicar_filtro_lista
from core.components.charts import pareto, barras_horizontales, donut
from core.components.tables import tabla_ejecutiva, tabla_clasificacion_abc

sidebar_header("Filtros")
clientes_sel = filtro_clientes(key_prefix="seg")

st.markdown(
    f"""
    <h2 style='color:{COLORS["primary"]};margin-bottom:0;'>Segmentacion de Clientes</h2>
    <p style='color:{COLORS["text_light"]};'>Analisis Pareto, clasificacion ABC y diversificacion de portafolio</p>
    """,
    unsafe_allow_html=True,
)
st.divider()

with st.spinner("Cargando datos base..."):
    df_vl_all = load_ventas_limpias()

anios_disp = []
if not df_vl_all.empty and "FECHAEMB" in df_vl_all.columns:
    anios_disp = sorted(df_vl_all["FECHAEMB"].dropna().dt.year.unique().tolist(), reverse=True)

col_flt1, col_flt2, col_flt3 = st.columns([1, 1, 4])
with col_flt1:
    anio_sel = st.selectbox("Filtrar por anio", options=["Todos"] + [str(a) for a in anios_disp], key="seg_anio")

with st.spinner("Procesando datos..."):
    if anio_sel != "Todos" and not df_vl_all.empty:
        df_yr = df_vl_all[df_vl_all["FECHAEMB"].dt.year == int(anio_sel)].copy()
        df_cliente = (
            df_yr.groupby("CLIENTE", as_index=False)["PESO_TON"].sum()
            if "CLIENTE" in df_yr.columns else load_gold_demanda_cliente()
        )
        if "PRODUCTO_LIMPIO" in df_yr.columns and "CLIENTE" in df_yr.columns:
            df_cp = df_yr.groupby(["CLIENTE", "PRODUCTO_LIMPIO"], as_index=False)["PESO_TON"].sum()
        else:
            df_cp = load_gold_cliente_producto()
    else:
        df_cliente = load_gold_demanda_cliente()
        df_cp = load_gold_cliente_producto()

if clientes_sel:
    df_cliente = aplicar_filtro_lista(df_cliente, clientes_sel, "CLIENTE")
    df_cp = aplicar_filtro_lista(df_cp, clientes_sel, "CLIENTE")

label_yr = f" — Anio {anio_sel}" if anio_sel != "Todos" else " — Historico total"
st.caption(f"Mostrando datos: **{label_yr.strip(' — ')}**  ·  {len(df_cliente):,} clientes")
st.divider()

# KPIs
df_abc = clasificar_abc(df_cliente)
df_resumen_abc = resumen_abc(df_abc)

total_clientes = len(df_abc)
n_a = len(df_abc[df_abc["CLASE"] == "A"]) if not df_abc.empty else 0
n_b = len(df_abc[df_abc["CLASE"] == "B"]) if not df_abc.empty else 0
n_c = len(df_abc[df_abc["CLASE"] == "C"]) if not df_abc.empty else 0
pct_a = round(n_a / total_clientes * 100, 1) if total_clientes > 0 else 0

render_kpi_row([
    {"label": "Total Clientes",      "value": total_clientes},
    {"label": "Clase A (80% vol.)",  "value": n_a, "suffix": f" ({pct_a}%)"},
    {"label": "Clase B",             "value": n_b},
    {"label": "Clase C",             "value": n_c},
])
st.divider()

# Pareto
seccion_titulo("Analisis Pareto de Clientes", "Volumen acumulado — top clientes")
col_p1, col_p2, _ = st.columns([1, 1, 4])
with col_p1:
    top_n_pareto = st.selectbox("Top clientes", options=[10, 15, 20, 30], index=2, key="pareto_top")

if not df_abc.empty:
    df_par = df_abc.head(top_n_pareto).copy()
    df_par["CLIENTE_CORTO"] = df_par["CLIENTE"].str[:26]
    fig_pareto = pareto(df_par, x="CLIENTE_CORTO", y="PESO_TON",
                        titulo=f"Pareto — Top {top_n_pareto} Clientes por Toneladas", max_items=top_n_pareto)
    fig_pareto.update_layout(height=440, margin=dict(b=140, l=40, r=80, t=50),
                              xaxis=dict(tickfont=dict(size=8), tickangle=-50))
    st.plotly_chart(fig_pareto, width="stretch")

st.divider()

# ABC detalle
seccion_titulo("Clasificacion ABC", "Selecciona clase para filtrar la tabla")
col_a, col_b = st.columns([1, 2])

with col_a:
    if not df_resumen_abc.empty:
        fig_donut = donut(df_resumen_abc, names="CLASE", values="PESO_TON", titulo="Volumen por clase")
        st.plotly_chart(fig_donut, width="stretch")
        tabla_ejecutiva(df_resumen_abc, col_formatos={"PESO_TON": "{:,.1f}", "PCT_VOLUMEN": "{:.1f}%"},
                        key="resumen_abc", height=140)

with col_b:
    clase_sel = st.radio("Mostrar clientes de clase:", options=["Todas", "A", "B", "C"],
                          horizontal=True, key="abc_clase_radio")
    if not df_abc.empty:
        df_det = df_abc if clase_sel == "Todas" else df_abc[df_abc["CLASE"] == clase_sel]
        st.caption(f"{len(df_det):,} clientes en clase **{clase_sel}**")
        cols_ok = [c for c in ["RANK", "CLIENTE", "PESO_TON", "PCT", "PCT_ACUM", "CLASE"] if c in df_det.columns]
        tabla_clasificacion_abc(df_det[cols_ok], key="abc_detalle")

st.divider()

# Diversificacion
seccion_titulo("Diversificacion por Cliente", "Numero de productos distintos comprados")
df_div = calcular_diversificacion(df_cp)

if not df_div.empty:
    col_c, col_d = st.columns(2)

    with col_c:
        top_div = st.selectbox("Top clientes", [10, 15, 20], index=2, key="div_top")
        fig_div = barras_horizontales(df_div.head(top_div), x="N_PRODUCTOS", y="CLIENTE",
                                       titulo=f"Top {top_div} clientes mas diversificados", x_label="N de productos")
        st.plotly_chart(fig_div, width="stretch")

    with col_d:
        seccion_titulo("Clientes Monoproducto", "Solo compran un tipo")
        df_mono = clientes_monoproducto(df_cp)
        tabla_ejecutiva(df_mono, col_formatos={"PESO_TON": "{:,.1f}"}, key="mono_producto", height=360)

# Barras apiladas cliente x producto
st.divider()
seccion_titulo("Mix de Productos por Cliente", "Distribucion de toneladas — barras apiladas")

if not df_cp.empty and "PRODUCTO_LIMPIO" in df_cp.columns:
    col_m1, col_m2, _ = st.columns([1, 1, 4])
    with col_m1:
        top_cli_mat = st.selectbox("Top clientes", [10, 15, 20, 30], index=2, key="mat_top")

    top_ids = df_cp.groupby("CLIENTE")["PESO_TON"].sum().nlargest(top_cli_mat).index.tolist()
    df_bar = df_cp[df_cp["CLIENTE"].isin(top_ids)].copy()
    df_bar["CLIENTE_CORTO"] = df_bar["CLIENTE"].str[:28]
    orden_cli = df_bar.groupby("CLIENTE_CORTO")["PESO_TON"].sum().sort_values(ascending=True).index.tolist()

    fig_stack = px.bar(
        df_bar, x="PESO_TON", y="CLIENTE_CORTO", color="PRODUCTO_LIMPIO", orientation="h",
        title=f"Toneladas por cliente y producto (top {top_cli_mat})",
        labels={"PESO_TON": "Toneladas", "CLIENTE_CORTO": "", "PRODUCTO_LIMPIO": "Producto"},
        color_discrete_sequence=COLOR_SEQUENCE,
        category_orders={"CLIENTE_CORTO": orden_cli},
    )
    fig_stack.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=10),
        margin=dict(l=10, r=20, t=50, b=40),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center", font=dict(size=9), title_text=""),
        height=max(380, top_cli_mat * 28 + 100), barmode="stack",
        xaxis=dict(title="Toneladas", gridcolor="#E5E7EB"),
        yaxis=dict(title="", tickfont=dict(size=9)),
        title=dict(font=dict(size=14, color=COLORS["primary"]), x=0),
    )
    st.plotly_chart(fig_stack, width="stretch")

# ---------------------------------------------------------------------------
# B1 — CLIENTES EN RIESGO
# ---------------------------------------------------------------------------
st.divider()
seccion_titulo("Clientes en Riesgo", "Detección automática de señales de alerta por cliente")

_ER  = "#DC2626"; _WA = "#D97706"; _OK = "#16A34A"
_T1  = "#0F172A"; _T2 = "#64748B"; _T3 = "#94A3B8"

from datetime import date as _date
_hoy = pd.Timestamp.today()

tab_fuga, tab_enfr, tab_mix = st.tabs(["En Fuga (>60d)", "Enfriándose (vol -30%)", "Cambiando Mix"])

# ── En Fuga ──────────────────────────────────────────────────────────────────
with tab_fuga:
    fuga_rows = []
    dc = load_gold_demanda_cliente()
    if not dc.empty and "ULTIMA_COMPRA" in dc.columns:
        dc = dc.copy()
        dc["ULTIMA_COMPRA"] = pd.to_datetime(dc["ULTIMA_COMPRA"], errors="coerce")
        dc["dias"] = (_hoy - dc["ULTIMA_COMPRA"]).dt.days
        en_fuga = dc[dc["dias"] > 60].sort_values("PESO_TON", ascending=False)
        for _, row in en_fuga.iterrows():
            dias   = int(row["dias"])
            nivel  = "Crítico (>120d)" if dias > 120 else "En seguimiento (61-120d)"
            fuga_rows.append({
                "Cliente":       row.get("CLIENTE", "?"),
                "Días sin comprar": dias,
                "Vol. histórico (ton)": row.get("PESO_TON", 0),
                "Severidad":     nivel,
            })

    if not fuga_rows:
        st.success("Todos los clientes compraron en los últimos 60 días.")
    else:
        df_fuga = pd.DataFrame(fuga_rows)
        n_crit = sum(1 for r in fuga_rows if r["Días sin comprar"] > 120)
        st.html(f"""<div style="display:flex;gap:10px;margin-bottom:10px;">
          <span style="display:inline-block;padding:3px 10px;border-radius:20px;
               background:#FEE2E2;color:#991B1B;font-size:10.5px;font-weight:700;">
            {n_crit} crítico(s)
          </span>
          <span style="display:inline-block;padding:3px 10px;border-radius:20px;
               background:#FEF3C7;color:#92400E;font-size:10.5px;font-weight:700;">
            {len(fuga_rows) - n_crit} en seguimiento
          </span>
        </div>""")
        for r in fuga_rows[:15]:
            col_bord = _ER if r["Días sin comprar"] > 120 else _WA
            st.html(f"""<div style="background:#fff;border-radius:10px;padding:10px 14px;
                 border-left:4px solid {col_bord};border:1px solid #E2E8F0;
                 margin-bottom:5px;display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="font-size:12.5px;font-weight:700;color:{_T1};">
                  {r['Cliente']}
                </div>
                <div style="font-size:11px;color:{_T2};margin-top:2px;">
                  {r['Severidad']} — Vol. histórico: {r['Vol. histórico (ton)']:,.1f} ton
                </div>
              </div>
              <div style="font-size:22px;font-weight:800;color:{col_bord};text-align:right;">
                {r['Días sin comprar']}d
                <div style="font-size:9px;font-weight:400;color:{_T3};">sin comprar</div>
              </div>
            </div>""")

# ── Enfriándose ───────────────────────────────────────────────────────────────
with tab_enfr:
    enfr_rows = []
    if not df_vl_all.empty and "FECHAEMB" in df_vl_all.columns and "CLIENTE" in df_vl_all.columns:
        vl = df_vl_all.copy()
        vl["FECHAEMB"] = pd.to_datetime(vl["FECHAEMB"], errors="coerce")
        vl = vl.dropna(subset=["FECHAEMB"])
        # Periodos: últimos 3 meses vs 3 meses anteriores
        corte1 = _hoy - pd.DateOffset(months=3)
        corte2 = _hoy - pd.DateOffset(months=6)
        reciente  = vl[vl["FECHAEMB"] >= corte1].groupby("CLIENTE")["PESO_TON"].sum()
        anterior  = vl[(vl["FECHAEMB"] >= corte2) & (vl["FECHAEMB"] < corte1)].groupby("CLIENTE")["PESO_TON"].sum()
        merged_e  = pd.DataFrame({"reciente": reciente, "anterior": anterior}).dropna()
        merged_e["cambio"] = (merged_e["reciente"] - merged_e["anterior"]) / merged_e["anterior"].replace(0, float("nan")) * 100
        frios = merged_e[merged_e["cambio"] <= -30].sort_values("cambio")
        for cli, row in frios.iterrows():
            pct = row["cambio"]
            vol_ant = row["anterior"]
            vol_rec = row["reciente"]
            col_bord = _ER if pct <= -50 else _WA
            enfr_rows.append((cli, pct, vol_ant, vol_rec, col_bord))

    if not enfr_rows:
        st.success("Sin clientes con caída >30% en los últimos 3 meses.")
    else:
        st.caption(f"{len(enfr_rows)} cliente(s) con volumen ≥ 30% abajo respecto a los 3 meses previos.")
        for cli, pct, vol_ant, vol_rec, col_bord in enfr_rows[:15]:
            st.html(f"""<div style="background:#fff;border-radius:10px;padding:10px 14px;
                 border-left:4px solid {col_bord};border:1px solid #E2E8F0;
                 margin-bottom:5px;display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="font-size:12.5px;font-weight:700;color:{_T1};">{cli}</div>
                <div style="font-size:11px;color:{_T2};margin-top:2px;">
                  Ant. 3m: {vol_ant:,.1f} ton -> Rec. 3m: {vol_rec:,.1f} ton
                </div>
              </div>
              <div style="font-size:22px;font-weight:800;color:{col_bord};text-align:right;">
                {pct:+.0f}%
                <div style="font-size:9px;font-weight:400;color:{_T3};">variación volumen</div>
              </div>
            </div>""")

# ── Cambiando Mix ─────────────────────────────────────────────────────────────
with tab_mix:
    mix_rows = []
    if not df_vl_all.empty and "FECHAEMB" in df_vl_all.columns \
            and "CLIENTE" in df_vl_all.columns and "PRODUCTO_LIMPIO" in df_vl_all.columns:
        vl2 = df_vl_all.copy()
        vl2["FECHAEMB"] = pd.to_datetime(vl2["FECHAEMB"], errors="coerce")
        vl2 = vl2.dropna(subset=["FECHAEMB"])
        anio_act_m = _hoy.year
        act_m  = vl2[vl2["FECHAEMB"].dt.year == anio_act_m]
        prev_m = vl2[vl2["FECHAEMB"].dt.year == anio_act_m - 1]

        def _top_prod(df_sub):
            if df_sub.empty:
                return pd.Series(dtype=str)
            return df_sub.groupby(["CLIENTE", "PRODUCTO_LIMPIO"])["PESO_TON"].sum() \
                         .reset_index().sort_values("PESO_TON", ascending=False) \
                         .drop_duplicates("CLIENTE").set_index("CLIENTE")["PRODUCTO_LIMPIO"]

        top_act  = _top_prod(act_m)
        top_prev = _top_prod(prev_m)
        comunes  = top_act.index.intersection(top_prev.index)
        cambiaron = comunes[top_act[comunes] != top_prev[comunes]]

        for cli in cambiaron[:20]:
            mix_rows.append({
                "Cliente":       cli,
                "Producto anterior": top_prev[cli],
                "Producto actual":   top_act[cli],
            })

    if not mix_rows:
        st.success("Sin cambios significativos en el producto principal de los clientes.")
    else:
        st.caption(f"{len(mix_rows)} cliente(s) cambiaron su producto #1 vs año anterior.")
        for r in mix_rows:
            st.html(f"""<div style="background:#fff;border-radius:10px;padding:10px 14px;
                 border-left:4px solid #8B5CF6;border:1px solid #E2E8F0;margin-bottom:5px;">
              <div style="font-size:12.5px;font-weight:700;color:{_T1};margin-bottom:4px;">
                {r['Cliente']}
              </div>
              <div style="display:flex;align-items:center;gap:8px;font-size:11.5px;">
                <span style="background:#F1F5F9;padding:3px 8px;border-radius:6px;
                     color:{_T2};">{r['Producto anterior']}</span>
                <span style="color:#8B5CF6;font-weight:700;">-></span>
                <span style="background:#F0FDF4;padding:3px 8px;border-radius:6px;
                     color:#166534;">{r['Producto actual']}</span>
              </div>
            </div>""")
