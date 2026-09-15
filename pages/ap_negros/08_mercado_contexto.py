"""
pages/ap_negros/08_mercado_contexto.py — Contexto de Mercado Aplicado.
Aceros Planos Negros — Conecta entorno macro/mercado con la demanda interna.
"""

import os, sys
from datetime import date

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from config import COLORS
from core.components.filters import sidebar_header
from core.components.kpi_cards import seccion_titulo

# ── Gemini key ────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

# ── Design tokens ─────────────────────────────────────────────────────────────
_P  = "#1B3A5C"
_OK = "#16A34A"
_WA = "#D97706"
_ER = "#DC2626"
_T1 = "#0F172A"
_T2 = "#64748B"
_T3 = "#94A3B8"
_BD = "#E2E8F0"
_BG = "#F8FAFC"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.html("""<style>
.mc-card{background:#fff;border-radius:12px;padding:16px 18px;
  border:1px solid #E2E8F0;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:8px;}
.mc-label{font-size:10px;font-weight:700;color:#94A3B8;text-transform:uppercase;
  letter-spacing:.07em;margin-bottom:4px;}
.mc-val{font-size:20px;font-weight:800;color:#0F172A;line-height:1.1;}
.mc-sub{font-size:11px;color:#94A3B8;margin-top:2px;}
.mc-badge{display:inline-block;padding:3px 10px;border-radius:20px;
  font-size:10.5px;font-weight:700;letter-spacing:.04em;}
.mc-vent{background:#fff;border-radius:10px;padding:14px 16px;
  border-left:4px solid #94A3B8;border:1px solid #E2E8F0;margin-bottom:8px;}
.mc-news{background:#F8FAFC;border-radius:8px;padding:10px 14px;
  border:1px solid #E2E8F0;margin-bottom:6px;}
</style>""")

# ── Sidebar ───────────────────────────────────────────────────────────────────
sidebar_header("Contexto de Mercado")

# ── Título ────────────────────────────────────────────────────────────────────
st.html(f"""
<div style="margin-bottom:6px;">
  <h2 style="color:{_P};margin:0;font-size:1.5rem;">Contexto de Mercado</h2>
  <p style="color:{_T2};margin:0;font-size:0.85rem;">
    Aceros Planos Negros — Entorno macroeconómico y de mercado aplicado
  </p>
</div>
""")
st.divider()

# ── Carga de datos ────────────────────────────────────────────────────────────
_ctx_ok = False
df_vars      = pd.DataFrame()
df_inegi     = pd.DataFrame()
df_quiebres  = pd.DataFrame()
df_mensual   = pd.DataFrame()
spk_inegi    = {}
noticias     = []

try:
    from aceros_planos.negros.loaders_contexto import (
        load_vars_mercado_planos,
        load_alertas_inegi_planos,
        load_quiebres_relevantes_planos,
        load_sparklines_inegi_planos,
        load_noticias_acero_plano,
    )
    from aceros_planos.negros.loaders import load_gold_demanda_mensual_total

    with st.spinner("Cargando datos de mercado..."):
        df_vars     = load_vars_mercado_planos(dias=400)
        df_inegi    = load_alertas_inegi_planos()
        df_quiebres = load_quiebres_relevantes_planos()
        spk_inegi   = load_sparklines_inegi_planos()
        df_mensual  = load_gold_demanda_mensual_total()

    with st.spinner("Cargando noticias..."):
        noticias = load_noticias_acero_plano()

    _ctx_ok = True
except Exception as _e:
    st.warning(f"Datos de contexto no disponibles: {_e}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt(v, dec=1) -> str:
    try:
        f = float(v)
        return f"{f:,.{dec}f}" if abs(f) >= 100 else f"{f:.{dec}f}"
    except Exception:
        return "—"

def _color_alerta(nivel: str) -> str:
    return {"Critico": _ER, "Alto": _WA, "Moderado": "#D97706", "Normal": _OK}.get(nivel, _T3)

def _badge_alerta(nivel: str) -> str:
    cfg = {
        "Critico":  ("#FEE2E2", "#991B1B"),
        "Alto":     ("#FEF3C7", "#92400E"),
        "Moderado": ("#FFFBEB", "#78350F"),
        "Normal":   ("#DCFCE7", "#166534"),
    }.get(nivel, ("#F1F5F9", "#64748B"))
    bg, tx = cfg
    return f'<span class="mc-badge" style="background:{bg};color:{tx};">{nivel}</span>'

def _sparkline_svg(vals: list, color="#1B3A5C", h=28, w=70) -> str:
    if not vals or len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1
    n   = len(vals)
    pts = " ".join(
        f"{i / (n-1) * w:.1f},{h - (v - mn) / rng * h:.1f}"
        for i, v in enumerate(vals)
    )
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/></svg>'


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — GAUGE DE CONDICIÓN COMERCIAL
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Índice de Condición Comercial", "Qué tan favorable está el entorno para vender acero plano")

if not _ctx_ok:
    st.info("Datos de mercado no disponibles.")
else:
    from aceros_planos.negros.analytics.contexto_mercado import calcular_indice_condicion_comercial
    icc = calcular_indice_condicion_comercial(df_vars, df_inegi)

    col_gauge, col_factores = st.columns([1, 1.5])

    with col_gauge:
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=icc["indice"],
            number={"font": {"size": 36, "color": icc["color"]}, "suffix": " / 10"},
            title={"text": f"<b>{icc['nivel']}</b>", "font": {"size": 15, "color": icc["color"]}},
            gauge={
                "axis": {"range": [0, 10], "tickwidth": 1, "tickcolor": _T3,
                         "tickfont": {"size": 10}},
                "bar":  {"color": icc["color"], "thickness": 0.3},
                "bgcolor": "white",
                "borderwidth": 0,
                "steps": [
                    {"range": [0,  4],  "color": "#FEE2E2"},
                    {"range": [4,  6.5],"color": "#FEF3C7"},
                    {"range": [6.5,10], "color": "#DCFCE7"},
                ],
                "threshold": {
                    "line": {"color": icc["color"], "width": 3},
                    "thickness": 0.75,
                    "value": icc["indice"],
                },
            },
        ))
        fig_g.update_layout(
            height=240, margin=dict(t=30, b=10, l=20, r=20),
            font=dict(family="Segoe UI, sans-serif"),
            paper_bgcolor="white",
        )
        st.plotly_chart(fig_g, width="stretch", config={"displayModeBar": False})

        st.html(f"""<div style="display:flex;justify-content:center;gap:16px;
             font-size:11px;color:{_T2};margin-top:-8px;">
          <span>Mercado: <b>{icc['score_mercado']}/10</b></span>
          <span>INEGI: <b>{icc['score_inegi']}/10</b></span>
          <span style="color:{_T3};">Act: {icc['ultima_actualizacion']}</span>
        </div>""")

    with col_factores:
        pos = icc.get("factores_positivos", [])
        neg = icc.get("factores_negativos", [])
        pos_items = "".join(
            f"<li style='margin-bottom:6px;font-size:12px;color:#166534;'>"
            f"<span style='color:{_OK};'>▲</span> {p}</li>"
            for p in pos
        ) or f"<li style='font-size:12px;color:{_T3};'>Sin señales positivas detectadas</li>"
        neg_items = "".join(
            f"<li style='margin-bottom:6px;font-size:12px;color:#991B1B;'>"
            f"<span style='color:{_ER};'>▼</span> {n}</li>"
            for n in neg
        ) or f"<li style='font-size:12px;color:{_T3};'>Sin señales negativas detectadas</li>"

        st.html(f"""
        <div style="display:flex;flex-direction:column;gap:10px;padding-top:8px;">
          <div style="background:#DCFCE7;border-radius:10px;padding:12px 14px;">
            <div style="font-size:10px;font-weight:700;color:#166534;
                 text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;">
              Factores Positivos
            </div>
            <ul style="margin:0;padding-left:14px;">{pos_items}</ul>
          </div>
          <div style="background:#FEE2E2;border-radius:10px;padding:12px 14px;">
            <div style="font-size:10px;font-weight:700;color:#991B1B;
                 text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;">
              Factores de Riesgo
            </div>
            <ul style="margin:0;padding-left:14px;">{neg_items}</ul>
          </div>
        </div>""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — INDICADORES INEGI
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Indicadores INEGI Relevantes", "Últimas lecturas y tendencias por categoría")

if not _ctx_ok or df_inegi.empty:
    st.info("Indicadores INEGI no disponibles.")
else:
    # Sub-grupos para Aceros Planos
    SUBTABS_INEGI = {
        "Manufactura":    ["736418", "736476", "736481", "736491", "910503"],
        "Hierro y Acero": ["736475", "736476", "736526", "736594", "910468", "910470"],
        "Inversión":      ["741034", "741030", "741025", "737173", "737149"],
        "Precios":        ["910396", "909294", "910398", "910393"],
    }

    tabs_inegi = st.tabs(list(SUBTABS_INEGI.keys()))

    for tab, (subtab_name, claves) in zip(tabs_inegi, SUBTABS_INEGI.items()):
        with tab:
            df_sub = df_inegi[df_inegi["Clave"].isin(claves)].copy() if "Clave" in df_inegi.columns else pd.DataFrame()

            if df_sub.empty:
                st.info("Sin datos disponibles para este grupo.")
                continue

            cols_tab = st.columns(min(len(df_sub), 4))
            for i, (_, row) in enumerate(df_sub.iterrows()):
                clave   = str(row.get("Clave", ""))
                nombre  = str(row.get("Nombre", row.get("nombre", clave)))
                valor   = row.get("ult_valor")
                alerta  = str(row.get("alerta", "Normal"))
                var_mom = row.get("var_mom")
                z_score = row.get("z_score")

                spk_vals = spk_inegi.get(clave, [])
                spk_html = _sparkline_svg(spk_vals, color=_color_alerta(alerta)) if spk_vals else ""

                badge = _badge_alerta(alerta)
                val_txt = _fmt(valor) if valor is not None else "N/D"
                mom_txt = f"{float(var_mom):+.1f}% MoM" if var_mom is not None else ""
                z_txt   = f"z={float(z_score):+.2f}σ" if z_score is not None else ""

                col_idx = i % 4
                with cols_tab[col_idx if len(cols_tab) > col_idx else -1]:
                    st.html(f"""<div class="mc-card">
                      <div class="mc-label">{nombre[:35]}</div>
                      <div class="mc-val">{val_txt}</div>
                      <div style="margin:4px 0;">{badge}</div>
                      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
                        <div style="font-size:10.5px;color:{_T2};">{mom_txt}{"  " if mom_txt and z_txt else ""}{z_txt}</div>
                        {spk_html}
                      </div>
                    </div>""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — VARIABLES DE MERCADO CON OVERLAY SOBRE DEMANDA
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Variables de Mercado vs Demanda", "Comparación con doble eje — selecciona variable")

if not _ctx_ok or df_vars.empty or df_mensual.empty:
    st.info("Datos insuficientes para comparación de series.")
else:
    VARS_DISP = {
        "ETF_Acero_Global": "ETF Acero Global",
        "Ternium_MX":       "Ternium MX",
        "ArcelorMittal":    "ArcelorMittal",
        "USD_MXN":          "USD / MXN",
        "VIX":              "VIX",
        "SP500":            "SP500",
        "Cobre_USD":        "Cobre USD",
        "Aluminio_USD":     "Aluminio USD",
    }
    var_opts = [v for v in VARS_DISP if v in df_vars.get("nombre", pd.Series()).unique()]

    if var_opts:
        c_sel, c_lbl = st.columns([2, 4])
        with c_sel:
            var_sel = st.selectbox("Variable de mercado:", var_opts,
                                   format_func=lambda x: VARS_DISP.get(x, x),
                                   key="mc_var_sel")
        with c_lbl:
            st.markdown(f"<div style='padding-top:22px;font-size:12px;color:{_T2};'>"
                        f"Barras = demanda mensual (ton) · Línea = {VARS_DISP.get(var_sel, var_sel)}</div>",
                        unsafe_allow_html=True)

        # Preparar demanda mensual
        dem = df_mensual.copy()
        dem["PERIODO"] = pd.to_datetime(dem.get("PERIODO", pd.Series(dtype="datetime64[ns]")), errors="coerce")
        dem = dem.dropna(subset=["PERIODO"]).sort_values("PERIODO")
        dem["ym"] = dem["PERIODO"].dt.to_period("M")
        dem_m = dem.groupby("ym")["PESO_TON"].sum().reset_index()
        dem_m["fecha"] = dem_m["ym"].dt.to_timestamp()

        # Preparar variable de mercado
        df_v = df_vars[df_vars["nombre"] == var_sel].copy()
        df_v["fecha"] = pd.to_datetime(df_v["fecha"], errors="coerce")
        df_v = df_v.dropna(subset=["fecha"]).sort_values("fecha")
        df_v["valor"] = pd.to_numeric(df_v["valor"], errors="coerce")
        df_v["ym"] = df_v["fecha"].dt.to_period("M")
        var_m = df_v.groupby("ym")["valor"].mean().reset_index()
        var_m["fecha"] = var_m["ym"].dt.to_timestamp()

        # Limitar a últimos 24 meses
        if not dem_m.empty:
            cutoff = dem_m["fecha"].max() - pd.DateOffset(months=24)
            dem_m = dem_m[dem_m["fecha"] >= cutoff]
            var_m = var_m[var_m["fecha"] >= cutoff]

        fig_ov = go.Figure()
        fig_ov.add_trace(go.Bar(
            x=dem_m["fecha"], y=dem_m["PESO_TON"],
            name="Demanda (ton)", marker_color=_P,
            opacity=0.75, yaxis="y1",
        ))
        fig_ov.add_trace(go.Scatter(
            x=var_m["fecha"], y=var_m["valor"],
            name=VARS_DISP.get(var_sel, var_sel),
            mode="lines+markers",
            line=dict(color=_WA, width=2.5),
            marker=dict(size=5), yaxis="y2",
        ))
        fig_ov.update_layout(
            height=340,
            margin=dict(t=20, b=10, l=10, r=10),
            legend=dict(orientation="h", y=1.08, x=0),
            paper_bgcolor="white", plot_bgcolor="#F8FAFC",
            yaxis=dict(title="Toneladas", gridcolor="#EEF2FF", showgrid=True),
            yaxis2=dict(title=VARS_DISP.get(var_sel, var_sel), overlaying="y",
                        side="right", showgrid=False),
            xaxis=dict(showgrid=False),
            font=dict(family="Segoe UI, sans-serif", size=11),
            barmode="overlay",
        )
        st.plotly_chart(fig_ov, width="stretch", config={"displayModeBar": False})
    else:
        st.info("Variables de mercado no disponibles en BigQuery.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — CORRELACIONES HISTÓRICAS
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Correlaciones Históricas", "¿Qué variables de mercado predicen la demanda?")

if not _ctx_ok or df_vars.empty or df_mensual.empty:
    st.info("Datos insuficientes para calcular correlaciones.")
else:
    from aceros_planos.negros.analytics.contexto_mercado import calcular_correlaciones_lag

    VARS_CORR = [
        "ETF_Acero_Global", "Ternium_MX", "ArcelorMittal",
        "USD_MXN", "VIX", "SP500", "Cobre_USD", "Aluminio_USD",
    ]

    with st.spinner("Calculando correlaciones..."):
        corrs = calcular_correlaciones_lag(df_mensual, df_vars, VARS_CORR, max_lag_dias=90)

    if not corrs:
        st.info("No se encontraron correlaciones significativas (r ≥ 0.15).")
    else:
        df_corr = pd.DataFrame(corrs)

        col_tbl, col_sct = st.columns([1.4, 1])

        with col_tbl:
            st.markdown(f"<div style='font-size:11px;font-weight:700;color:{_T2};margin-bottom:6px;'>"
                        f"Top correlaciones detectadas</div>", unsafe_allow_html=True)
            for r in corrs[:8]:
                sig_badge = (f'<span class="mc-badge" style="background:#EFF6FF;color:#1E40AF;">'
                             f'Significativa</span>') if r["significativa"] else ""
                corr_color = _OK if r["correlacion"] > 0 else _ER
                corr_bar_w = abs(r["correlacion"]) * 100
                lag_txt = f"{r['mejor_lag_dias']}d lag" if r["mejor_lag_dias"] > 0 else "simultáneo"
                st.html(f"""<div class="mc-card" style="padding:10px 14px;margin-bottom:4px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span style="font-size:12px;font-weight:700;color:{_T1};">
                      {r['variable'].replace('_',' ')}
                    </span>
                    <span style="font-size:12px;font-weight:800;color:{corr_color};">
                      r = {r['correlacion']:+.2f}
                    </span>
                  </div>
                  <div style="background:#E2E8F0;border-radius:3px;height:5px;margin-bottom:6px;">
                    <div style="width:{corr_bar_w:.0f}%;background:{corr_color};height:5px;border-radius:3px;"></div>
                  </div>
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:10.5px;color:{_T2};">{lag_txt} · {r['interpretacion'][:60]}…</span>
                    {sig_badge}
                  </div>
                </div>""")

        with col_sct:
            # Scatter de mejor correlación
            best = corrs[0]
            var_b = best["variable"]
            lag_b = best["mejor_lag_dias"]

            dem_s = df_mensual.copy()
            dem_s["PERIODO"] = pd.to_datetime(dem_s.get("PERIODO", pd.Series(dtype="datetime64[ns]")), errors="coerce")
            dem_s = dem_s.dropna(subset=["PERIODO"]).sort_values("PERIODO")
            dem_s["ym"] = dem_s["PERIODO"].dt.to_period("M")
            dem_s = dem_s.groupby("ym")["PESO_TON"].sum().reset_index()

            df_vb = df_vars[df_vars["nombre"] == var_b].copy()
            df_vb["fecha"] = pd.to_datetime(df_vb["fecha"], errors="coerce")
            df_vb = df_vb.dropna(subset=["fecha"]).sort_values("fecha")
            df_vb["valor"] = pd.to_numeric(df_vb["valor"], errors="coerce")
            df_vb["fecha_adj"] = df_vb["fecha"] - pd.Timedelta(days=lag_b)
            df_vb["ym"] = df_vb["fecha_adj"].dt.to_period("M")
            vb_m = df_vb.groupby("ym")["valor"].mean().reset_index()

            merged_s = dem_s.merge(vb_m, on="ym", how="inner")

            if len(merged_s) >= 4:
                fig_sc = px.scatter(
                    merged_s, x="valor", y="PESO_TON",
                    labels={"valor": var_b.replace("_", " "), "PESO_TON": "Demanda (ton)"},
                    trendline="ols",
                    color_discrete_sequence=[_P],
                )
                fig_sc.update_traces(marker=dict(size=7, opacity=0.7))
                fig_sc.update_layout(
                    height=280, margin=dict(t=30, b=10, l=10, r=10),
                    paper_bgcolor="white", plot_bgcolor="#F8FAFC",
                    title=dict(
                        text=f"{var_b.replace('_',' ')} vs Demanda (r={best['correlacion']:+.2f})",
                        font=dict(size=11, color=_T2),
                    ),
                    font=dict(family="Segoe UI, sans-serif", size=10),
                    showlegend=False,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(gridcolor="#EEF2FF"),
                )
                st.plotly_chart(fig_sc, width="stretch",
                                config={"displayModeBar": False})

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — VENTANAS DE OPORTUNIDAD ACTIVAS
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Ventanas de Oportunidad Activas", "Señales del entorno que el equipo comercial puede aprovechar")

if not _ctx_ok:
    st.info("Datos de mercado no disponibles.")
else:
    from aceros_planos.negros.analytics.contexto_mercado import detectar_ventanas_oportunidad
    ventanas = detectar_ventanas_oportunidad(df_vars, df_inegi)

    if not ventanas:
        st.success("Sin ventanas de oportunidad activas detectadas en este momento.")
    else:
        n_alta  = sum(1 for v in ventanas if v["nivel"] == "Alta")
        n_media = sum(1 for v in ventanas if v["nivel"] == "Media")
        n_baja  = sum(1 for v in ventanas if v["nivel"] == "Baja")

        st.html(f"""<div style="display:flex;gap:10px;margin-bottom:12px;">
          <span class="mc-badge" style="background:#DCFCE7;color:#166534;">
            {n_alta} Alta prioridad
          </span>
          <span class="mc-badge" style="background:#FEF3C7;color:#92400E;">
            {n_media} Prioridad media
          </span>
          <span class="mc-badge" style="background:#F1F5F9;color:#64748B;">
            {n_baja} Señal informativa
          </span>
        </div>""")

        COLOR_NIV = {"Alta": (_OK, "#DCFCE7"), "Media": (_WA, "#FEF3C7"), "Baja": (_T3, "#F1F5F9")}

        vent_cols = st.columns(2)
        for i, v in enumerate(ventanas):
            bord, bg = COLOR_NIV.get(v["nivel"], (_T3, "#F1F5F9"))
            vars_txt = " · ".join(v.get("variables_involucradas", []))[:80]
            with vent_cols[i % 2]:
                st.html(f"""<div class="mc-vent" style="border-left-color:{bord};background:{bg};">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;
                       margin-bottom:4px;">
                    <span style="font-size:12.5px;font-weight:700;color:{_T1};">{v['tipo']}</span>
                    <span class="mc-badge" style="background:white;color:{bord};
                         border:1.5px solid {bord};font-size:9.5px;">{v['nivel']}</span>
                  </div>
                  <div style="font-size:12px;color:{_T2};margin-bottom:6px;">{v['descripcion']}</div>
                  <div style="background:rgba(255,255,255,.7);border-radius:6px;
                       padding:6px 10px;font-size:11.5px;color:{_T1};">
                    <strong>▶</strong> {v['accion_sugerida']}
                  </div>
                  {f'<div style="font-size:9.5px;color:{_T3};margin-top:6px;">Variables: {vars_txt}</div>' if vars_txt else ''}
                </div>""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 6 — NOTICIAS RELEVANTES
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Noticias del Sector", "Últimas noticias sobre acero plano, HRC y mercado siderúrgico")

_IA_KEY = f"mc_noticias_ia_{date.today().isoformat()}"

col_nw, col_ia = st.columns([3, 1])

with col_nw:
    if not noticias:
        st.info("Sin noticias disponibles. Verifica la conexión a internet.")
    else:
        for n in noticias[:8]:
            titulo   = n.get("titulo", n.get("title", "Sin título"))[:90]
            fuente   = n.get("fuente", n.get("source", ""))
            fecha_p  = n.get("fecha_pub", n.get("pubDate", ""))[:10] if n.get("fecha_pub") or n.get("pubDate") else ""
            url      = n.get("url", n.get("link", "#"))
            resumen  = n.get("resumen", n.get("summary", ""))[:120]

            fecha_html = f'<span class="mc-badge" style="background:#EFF6FF;color:#1E40AF;">{fecha_p}</span>' if fecha_p else ""
            fuente_html = f'<span style="color:{_T3};font-size:10px;">{fuente}</span>' if fuente else ""
            res_html = f'<div style="font-size:11px;color:{_T2};margin-top:3px;">{resumen}…</div>' if resumen else ""

            st.html(f"""<div class="mc-news">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;
                   gap:8px;margin-bottom:3px;">
                <a href="{url}" target="_blank" style="font-size:12.5px;font-weight:600;
                   color:{_P};text-decoration:none;flex:1;line-height:1.3;">
                  {titulo}
                </a>
                {fecha_html}
              </div>
              {fuente_html}
              {res_html}
            </div>""")

with col_ia:
    st.html(f"""<div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;
         padding:14px;margin-bottom:10px;">
      <div style="font-size:10px;font-weight:700;color:#0369A1;text-transform:uppercase;
           letter-spacing:.06em;margin-bottom:8px;">Análisis IA</div>
      <div style="font-size:11.5px;color:{_T2};">
        Genera un resumen ejecutivo de las noticias y las ventanas de oportunidad actuales.
      </div>
    </div>""")

    run_ia = st.button("Analizar con IA", key="btn_mc_ia",
                       disabled=not bool(_GEMINI_KEY),
                       width="stretch")

    if run_ia and _GEMINI_KEY:
        vent_txt = "\n".join(
            f"- {v['tipo']} ({v['nivel']}): {v['descripcion']}" for v in (ventanas if _ctx_ok else [])
        ) or "- Sin ventanas detectadas"
        noticias_txt = "\n".join(
            f"- {n.get('titulo', '')}" for n in noticias[:5]
        ) or "- Sin noticias disponibles"

        prompt = f"""Eres analista comercial senior de TYASA (acería mexicana de acero plano).
En máximo 4 bullets ejecutivos de 15 palabras cada uno, resume:
1. Estado del entorno de mercado para acero plano
2. Principales oportunidades comerciales activas
3. Riesgos inmediatos a monitorear
4. Acción concreta recomendada para el equipo de ventas

Datos actuales:
Ventanas de oportunidad:
{vent_txt}

Titulares recientes:
{noticias_txt}

Sin introducción. Sin cierre. Solo los 4 bullets, sin emojis."""

        from mercado_noticias.analytics.ai_analysis import _call_gemini_text
        st.session_state[_IA_KEY] = _call_gemini_text(prompt, _GEMINI_KEY)

def _render_ia_noticias(txt: str | None) -> str:
    if not txt:
        return ""
    bullets = [l.strip() for l in txt.strip().split("\n") if l.strip()]
    items = "".join(
        f"<li style='margin-bottom:7px;font-size:11.5px;color:{_T1};line-height:1.4;'>{b}</li>"
        for b in bullets
    )
    return f"""<div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;
         padding:14px;margin-top:8px;">
      <div style="font-size:10px;font-weight:700;color:#0369A1;text-transform:uppercase;
           letter-spacing:.06em;margin-bottom:8px;">Resumen — {date.today().strftime('%d %b %Y')}</div>
      <ul style="margin:0;padding-left:16px;">{items}</ul>
    </div>"""

with col_ia:
    st.html(_render_ia_noticias(st.session_state.get(_IA_KEY)))
