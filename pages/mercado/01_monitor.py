"""
01_monitor.py — Monitor de Quiebres de Mercado — TYASA BI
Alertas en tiempo real · Análisis IA · Chat · Explorar variable
"""
import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from config import COLORS

from mercado_noticias.loaders import load_variables_mercado, get_categorias_disponibles
from mercado_noticias.analytics.detector import detectar_quiebres_automatico
from mercado_noticias.analytics.noticias import (
    buscar_noticias_multifuente, get_google_news_url, QUERIES
)
from mercado_noticias.analytics.ai_analysis import (
    analizar_alerta, _call_gemini_text,
    _cache_key, _cache_load,
)
from core.components.filters import sidebar_header
from core.components.kpi_cards import render_kpi_row, seccion_titulo
from core.components.market_summary import build_indicadores_html

# ── API key ───────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

# ── Paleta de severidad ───────────────────────────────────────────────────────
SEV_COLORS = {
    "Crítico":  ("#C0392B", "#FCEBEB"),
    "Alto":     ("#D68910", "#FAEEDA"),
    "Moderado": ("#185FA5", "#E6F1FB"),
}
SEV_ORDEN = {"Crítico": 4, "Alto": 3, "Moderado": 2, "Normal": 1}


# ════════════════════════════════════════════════════════════════════════════
# HELPERS (solo HTML puro — cero componentes Streamlit condicionales)
# ════════════════════════════════════════════════════════════════════════════

def _ai_html(result: dict | None, color_txt: str) -> str:
    """Convierte resultado de IA a HTML. Retorna '' si no hay resultado."""
    if not result:
        return ""
    D_ICO = {"Oferta":"🏭","Demanda":"📊","Geopolitica":"🌍","Macro":"🏦","Sectorial":"⚙️"}
    S_ICO = {"Alcista":"📈","Bajista":"📉","Neutral":"➡️"}
    C_COL = {"Alta":"#2E7D32","Media":"#D68910","Baja":"#C62828"}
    d  = result.get("driver_principal","—")
    s  = result.get("sentimiento","—")
    c  = result.get("confianza","—")
    ca = result.get("_cached", False)
    di = D_ICO.get(d,"🔍"); si = S_ICO.get(s,"➡️"); cc = C_COL.get(c,"#6B7280")
    cb = '<span style="background:#F3F4F6;color:#888;padding:2px 7px;border-radius:8px;font-size:10px;margin-left:4px;">💾</span>' if ca else ""
    err = result.get("_error","")
    eh  = f"<div style='color:#C62828;font-size:11px;margin-bottom:4px;'>⚠️ {err}</div>" if err else ""
    badges = (
        f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin:8px 0;'>"
        f"<span style='background:#EEF2FF;color:#3730A3;padding:3px 8px;border-radius:20px;font-size:11px;font-weight:600;'>{di} {d}</span>"
        f"<span style='background:#F0FDF4;color:#166534;padding:3px 8px;border-radius:20px;font-size:11px;font-weight:600;'>{si} {s}</span>"
        f"<span style='background:#FFF7ED;color:{cc};padding:3px 8px;border-radius:20px;font-size:11px;font-weight:600;'>✓ {c}</span>"
        f"{cb}</div>"
    )
    puntos = result.get("puntos_clave",[])
    items  = "".join(
        f"<div style='border-left:3px solid {color_txt};padding:4px 10px;margin-bottom:4px;"
        f"font-size:12px;background:#FAFAFA;border-radius:0 4px 4px 0;'><b>{i}.</b> {p}</div>"
        for i, p in enumerate(puntos[:5], 1)
    ) if puntos else ""
    pkh = f"<b style='font-size:12px;'>Puntos clave:</b>{items}" if items else ""
    imp = result.get("impacto_tyasa","")
    imph = (
        f"<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:5px;"
        f"padding:8px 12px;margin-top:6px;font-size:12px;color:#1E40AF;'>"
        f"🏭 <b>Impacto TYASA:</b> {imp}</div>"
    ) if imp and imp != "—" else ""
    return (
        f"<div style='margin:8px 0;padding:10px;background:#F9FAFB;"
        f"border-radius:6px;border:1px solid #E5E7EB;'>{eh}{badges}{pkh}{imph}</div>"
    )


def _news_card_html(n: dict, c_txt: str, c_bg: str) -> str:
    titulo = (n.get("titulo","") or "")
    desc   = (n.get("descripcion","") or "")[:200]
    fuente = (n.get("fuente","") or "")
    url    = (n.get("url","") or "")
    fecha  = (n.get("fecha_pub","") or "")
    badge  = n.get("fuente_api","")
    bc     = "#1B3A5C" if badge == "Google News" else "#6B7280"
    link   = (f'<a href="{url}" target="_blank" style="color:{c_txt};font-weight:600;'
              f'font-size:11px;text-decoration:none;">Ver →</a>') if url else ""
    return (
        f"<div style='border-left:3px solid {c_txt};background:{c_bg};"
        f"padding:8px 12px;border-radius:0 5px 5px 0;margin-bottom:6px;'>"
        f"<div style='font-size:12px;font-weight:600;color:{c_txt};line-height:1.4;'>{titulo}</div>"
        f"<div style='font-size:11px;color:#444;margin-top:3px;line-height:1.4;'>{desc}</div>"
        f"<div style='font-size:10px;color:#888;margin-top:4px;display:flex;gap:8px;"
        f"flex-wrap:wrap;align-items:center;'>"
        f"📅 {fecha} · 📰 {fuente} "
        f"<span style='background:{bc};color:white;padding:1px 5px;border-radius:3px;"
        f"font-size:9px;'>{badge}</span> {link}</div></div>"
    )


# ════════════════════════════════════════════════════════════════════════════
# COMPONENTES REUTILIZABLES (componentes Streamlit estables)
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)
def _noticias_var_cached(variable: str, max_r: int = 10) -> list[dict]:
    """Caché 15 min por variable. Evita llamadas HTTP repetidas en cada rerender."""
    return buscar_noticias_multifuente(variable, ventana_dias=7, max_resultados=max_r)


def _render_ai_inline(var: str, sigma_a: float, cambio7: float,
                       val_act: float, mu_base: float, tend: str,
                       color_txt: str):
    """
    AI inline dentro del expander.
    Exactamente 1 st.button + 1 st.markdown — árbol DOM estable.
    Sin st.spinner, sin condicionales de árbol.
    """
    if not _GEMINI_KEY:
        return
    skey = f"ai_{var}_{round(sigma_a, 1)}"
    if st.button("🤖 Análisis IA", key=f"aibtn_{var}"):
        nots = _noticias_var_cached(variable=var)
        st.session_state[skey] = analizar_alerta(
            variable=var, sigma=sigma_a, cambio7=cambio7,
            valor=val_act, media_base=mu_base, tendencia=tend,
            noticias=nots, api_key=_GEMINI_KEY,
            scrape_articles=False, force_refresh=False,
        )
    result = st.session_state.get(skey)
    if result is None:
        disk = _cache_load(_cache_key(var, sigma_a))
        if disk:
            disk["_cached"] = True
            st.session_state[skey] = disk
            result = disk
    st.markdown(_ai_html(result, color_txt), unsafe_allow_html=True)


def _render_noticias_tabs(variable: str, color_txt: str, color_bg: str):
    """Noticias últimos 7 días (sin tabs — una sola llamada HTTP cacheada)."""
    col_t, col_g = st.columns([3, 1])
    with col_g:
        st.markdown(
            f"<a href='{get_google_news_url(variable)}' target='_blank' style='"
            f"display:inline-block;padding:5px 10px;background:{color_txt};color:white;"
            f"border-radius:5px;font-size:11px;text-decoration:none;font-weight:600;'>"
            f"🔍 Google News</a>",
            unsafe_allow_html=True
        )
    nots = _noticias_var_cached(variable)
    if not nots:
        st.caption("Sin noticias en los últimos 7 días.")
        return
    st.caption(f"{len(nots)} artículo(s) · últimos 7 días")
    html = "".join(_news_card_html(n, color_txt, color_bg) for n in nots)
    st.markdown(html, unsafe_allow_html=True)


def _render_chart(df_vars: pd.DataFrame, var: str,
                  mu_base: float, umbral_sigma: float, color: str = "#1B3A5C"):
    df_var = df_vars[df_vars["nombre"] == var].sort_values("fecha")
    if df_var.empty:
        return
    std_val = df_var["valor"].std()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_var["fecha"], y=df_var["valor"],
        line=dict(color=color, width=1.8),
        hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f}<extra></extra>",
        name=var.replace("_", " ")
    ))
    fig.add_hrect(
        y0=mu_base - umbral_sigma * std_val,
        y1=mu_base + umbral_sigma * std_val,
        fillcolor="rgba(27,58,92,0.07)", line_width=0,
        annotation_text=f"Rango normal (±{umbral_sigma}σ)",
        annotation_position="top left", annotation_font_size=9,
    )
    fig.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=30, b=40),
        height=220, showlegend=False,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB"),
    )
    st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
sidebar_header("Monitor de Mercado", "📡")
categorias    = get_categorias_disponibles()
cat_sel       = st.sidebar.selectbox("Categoría", ["Todas"] + categorias, key="mkt_cat")
sev_sel       = st.sidebar.selectbox("Severidad mínima", ["Todas","Crítico","Alto","Moderado"], key="mkt_sev")
umbral_sigma  = st.sidebar.slider("Sensibilidad (σ)", 1.0, 5.0, 2.0, 0.5, key="mkt_sigma")
st.sidebar.divider()
st.sidebar.caption(
    "Detección automática z-score respecto a la media pre-evento.\n\n"
    "Datos actualizados diariamente desde BigQuery."
)

# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════
st.markdown(
    f"<h2 style='color:{COLORS['primary']};margin-bottom:0;'>📡 Monitor de Quiebres de Mercado</h2>"
    f"<p style='color:#6B7280;'>Variables siderúrgicas globales · Detección automática · "
    f"Noticias vinculadas · Análisis IA</p>",
    unsafe_allow_html=True,
)
st.divider()

# ════════════════════════════════════════════════════════════════════════════
# DATA
# ════════════════════════════════════════════════════════════════════════════
with st.spinner("Cargando datos de mercado..."):
    df_vars = load_variables_mercado(dias=400)

# ── Resumen de indicadores financieros al tope ────────────────────────────
_ind_html = build_indicadores_html(df_vars)
if _ind_html:
    st.html(_ind_html)
    st.divider()

alertas_live: list[dict] = []
if not df_vars.empty:
    alertas_live = detectar_quiebres_automatico(df_vars, umbral_sigma=umbral_sigma)

nivel_min = SEV_ORDEN.get(sev_sel, 1) if sev_sel != "Todas" else 0
alertas_filt = [
    a for a in alertas_live
    if (cat_sel == "Todas" or a["categoria"] == cat_sel)
    and SEV_ORDEN.get(a["severidad"], 1) >= nivel_min
]

# ── KPIs ───────────────────────────────────────────────────────────────────
n_crit = sum(1 for a in alertas_live if a["severidad"] == "Crítico")
n_alto = sum(1 for a in alertas_live if a["severidad"] == "Alto")
n_mod  = sum(1 for a in alertas_live if a["severidad"] == "Moderado")
render_kpi_row([
    {"label": "Alertas activas",    "value": len(alertas_live), "icon": "⚡",
     "help_text": f"Variables superando {umbral_sigma}σ en los últimos 5 días hábiles"},
    {"label": "Críticas",           "value": n_crit,            "icon": "🔴"},
    {"label": "Altas",              "value": n_alto,            "icon": "🟠"},
    {"label": "Moderadas",          "value": n_mod,             "icon": "🟡"},
])
st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN A — ALERTAS EN TIEMPO REAL
# ════════════════════════════════════════════════════════════════════════════
if alertas_filt:
    seccion_titulo(
        f"⚡ Alertas detectadas ({len(alertas_filt)})",
        "Variables con comportamiento anómalo en los últimos 5 días hábiles"
    )
    for alerta in alertas_filt[:10]:
        var     = alerta["variable"]
        sigma_a = alerta["sigma_actual"]
        sev     = alerta["severidad"]
        cambio7 = alerta["cambio_7d_pct"]
        val_act = alerta["valor_actual"]
        mu_base = alerta["media_base"]
        tend    = alerta["tendencia"]
        cat     = alerta["categoria"]
        fecha_d = alerta["fecha_deteccion"]

        color_txt, color_bg = SEV_COLORS.get(sev, ("#6B7280", "#F3F4F6"))
        flecha = "↑" if tend == "sube" else "↓"
        sev_badge = f"<span style='background:{color_txt};color:white;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;'>{sev}</span>"

        with st.expander(
            f"**{var.replace('_',' ')}** — {flecha} {cambio7:+.1f}% (7d) · {sigma_a:+.2f}σ · {sev}",
            expanded=False
        ):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Sigma actual",  f"{sigma_a:+.2f}σ")
            col2.metric("Cambio 7 días", f"{cambio7:+.1f}%")
            col3.metric("Valor actual",  f"{val_act:,.2f}")
            col4.metric("Media base",    f"{mu_base:,.2f}")

            st.markdown(
                f"<div style='background:{color_bg};border-left:4px solid {color_txt};"
                f"border-radius:6px;padding:8px 14px;margin:6px 0;font-size:13px;'>"
                f"<b>Categoría:</b> {cat} &nbsp;|&nbsp; "
                f"<b>Última observación:</b> {pd.Timestamp(fecha_d).strftime('%d %b %Y')}"
                f"</div>",
                unsafe_allow_html=True
            )

            # Gráfica
            _render_chart(df_vars, var, mu_base, umbral_sigma, color_txt)

            # ── AI inline (1 button + 1 markdown — DOM estable) ───────────
            if sev in ("Crítico", "Alto"):
                st.markdown(
                    f"<div style='border-top:1px solid #E5E7EB;margin:10px 0 6px;'></div>",
                    unsafe_allow_html=True
                )
                col_ai, col_chat = st.columns([1, 1])
                with col_ai:
                    _render_ai_inline(var, sigma_a, cambio7, val_act, mu_base, tend, color_txt)
                with col_chat:
                    if st.button("💬 Preguntar al analista", key=f"chat_open_{var}"):
                        st.session_state["chat_var"] = var
                        st.session_state["chat_alerta"] = alerta
                        if f"chat_msgs_{var}" not in st.session_state:
                            st.session_state[f"chat_msgs_{var}"] = []

            # Noticias
            st.markdown("**📰 Noticias relacionadas:**")
            _render_noticias_tabs(var, color_txt, color_bg)

    # ── Noticias consolidadas de las alertas más críticas ─────────────────────
    _top_alertas = [a for a in alertas_filt if a["severidad"] in ("Crítico", "Alto")][:4]
    if not _top_alertas:
        _top_alertas = alertas_filt[:3]

    _cards_nots = ""
    for _alerta in _top_alertas:
        _var    = _alerta["variable"]
        _sev    = _alerta["severidad"]
        _ct, _cb = SEV_COLORS.get(_sev, ("#6B7280", "#F3F4F6"))
        _sigma  = _alerta["sigma_actual"]
        _cam7   = _alerta["cambio_7d_pct"]
        _flecha = "↑" if _alerta["tendencia"] == "sube" else "↓"
        _nots   = _noticias_var_cached(_var, max_r=5)[:3]
        if not _nots:
            continue
        _nots_html = ""
        for _n in _nots:
            _tit   = (_n.get("titulo") or "")[:75]
            _url   = (_n.get("url") or "").replace('"', "%22").replace("'", "%27")
            _src   = _n.get("fuente", "")
            _fech  = (_n.get("fecha_pub") or "")[:10]
            _link_open  = f'<a href="{_url}" target="_blank" style="font-size:11.5px;color:#1B3A5C;text-decoration:none;line-height:1.4;display:block;">' if _url else '<span style="font-size:11.5px;color:#374151;">'
            _link_close = "</a>" if _url else "</span>"
            _nots_html += (
                f"<div style='border-left:2px solid {_ct};padding:4px 8px;"
                f"margin-bottom:4px;background:#FAFAFA;border-radius:0 5px 5px 0;'>"
                f"{_link_open}{_tit}{_link_close}"
                f"<span style='font-size:10px;color:#9CA3AF;'>{_src} · {_fech}</span>"
                f"</div>"
            )
        _cards_nots += (
            f"<div style='background:{_cb};border:1px solid {_ct}33;"
            f"border-radius:8px;padding:10px 12px;'>"
            f"<div style='font-size:11px;font-weight:700;color:{_ct};"
            f"letter-spacing:.03em;margin-bottom:6px;'>"
            f"📡 {_var.replace('_', ' ')}&nbsp;"
            f"<span style='background:{_ct};color:#fff;padding:1px 7px;"
            f"border-radius:10px;font-size:10px;'>{_sev}</span> "
            f"<span style='font-size:10px;font-weight:400;'>"
            f"{_flecha} {_cam7:+.1f}% · {_sigma:+.2f}σ</span></div>"
            f"{_nots_html}"
            f"</div>"
        )

    if _cards_nots:
        seccion_titulo("📰 Noticias relacionadas con las alertas",
                       "Artículos recientes de las variables con mayor anomalía")
        st.html(
            "<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;"
            "margin-bottom:8px;'>"
            + _cards_nots
            + "</div>"
        )

    st.divider()

else:
    st.info(
        f"No hay alertas activas con umbral {umbral_sigma}σ. "
        "Reduce la sensibilidad en el sidebar para ver más variables."
    )
    st.divider()


# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN B — EXPLORAR VARIABLE
# Permite ver tendencia, noticias y análisis IA de cualquier variable
# sin necesidad de que esté en alerta
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo(
    "🔍 Explorar Variable de Mercado",
    "Selecciona cualquier variable para ver su tendencia, noticias y análisis IA"
)

all_vars   = sorted(QUERIES.keys())
var_expl   = st.selectbox("Variable", all_vars, key="expl_var",
                           format_func=lambda v: v.replace("_", " "))

df_expl    = df_vars[df_vars["nombre"] == var_expl].sort_values("fecha") if not df_vars.empty else pd.DataFrame()
color_expl = COLORS["primary"]

if not df_expl.empty:
    mu_expl = float(df_expl["valor"].iloc[:-45].mean()) if len(df_expl) > 50 else float(df_expl["valor"].mean())
    val_expl = float(df_expl["valor"].iloc[-1])
    sigma_expl_val = float(
        (df_expl["valor"].iloc[-5:].mean() - mu_expl) / (df_expl["valor"].iloc[:-45].std() + 1e-9)
    ) if len(df_expl) > 50 else 0.0
    cambio_expl = float(
        (df_expl["valor"].iloc[-1] / df_expl["valor"].iloc[-8] - 1) * 100
    ) if len(df_expl) >= 8 else 0.0

    col_e1, col_e2, col_e3 = st.columns(3)
    col_e1.metric("Valor actual",    f"{val_expl:,.2f}")
    col_e2.metric("Cambio 7 días",   f"{cambio_expl:+.1f}%")
    col_e3.metric("Sigma vs base",   f"{sigma_expl_val:+.2f}σ")

    _render_chart(df_expl.assign(nombre=var_expl), var_expl, mu_expl, umbral_sigma, color_expl)
else:
    mu_expl       = 0.0
    sigma_expl_val = 0.0
    cambio_expl   = 0.0
    st.info("Sin datos para esta variable.")

# AI para variable explorada — fuera de expander/loop → DOM estable
if _GEMINI_KEY:
    skey_expl = f"ai_{var_expl}_{round(sigma_expl_val, 1)}"
    col_btn_e, col_frz_e = st.columns([1, 2])
    with col_btn_e:
        run_expl = st.button("🤖 Análisis IA", key="expl_ai_btn")
    with col_frz_e:
        frz_expl = st.checkbox("Regenerar (ignorar caché)", key="expl_ai_chk")
    if run_expl:
        nots_expl = _noticias_var_cached(var_expl)
        st.session_state[skey_expl] = analizar_alerta(
            variable=var_expl, sigma=sigma_expl_val, cambio7=cambio_expl,
            valor=val_expl if not df_expl.empty else 0.0,
            media_base=mu_expl, tendencia="sube" if cambio_expl > 0 else "baja",
            noticias=nots_expl, api_key=_GEMINI_KEY,
            scrape_articles=False, force_refresh=frz_expl,
        )
    res_expl = st.session_state.get(skey_expl) or _cache_load(_cache_key(var_expl, sigma_expl_val))
    st.markdown(_ai_html(res_expl, color_expl), unsafe_allow_html=True)

st.markdown("**📰 Noticias:**")
_render_noticias_tabs(var_expl, color_expl, "#EBF5FB")

# ── Comparación multi-variable ────────────────────────────────────────────────
st.markdown(
    "<div style='border-top:1px solid #E5E7EB;margin:18px 0 12px;'></div>"
    "<div style='font-size:14px;font-weight:700;color:#1B3A5C;margin-bottom:4px;'>"
    "🔗 Cruzar variables y consultar al analista</div>"
    "<div style='font-size:12px;color:#6B7280;margin-bottom:10px;'>"
    "Selecciona 2 a 5 variables — el analista cruzará su información y responderá en contexto</div>",
    unsafe_allow_html=True
)

vars_compare = st.multiselect(
    "Variables a cruzar",
    all_vars,
    default=[var_expl],
    max_selections=5,
    key="expl_vars_compare",
    format_func=lambda v: v.replace("_", " "),
)

# Métricas compactas de cada variable seleccionada
if vars_compare and not df_vars.empty:
    cols_cmp = st.columns(len(vars_compare))
    for i, v in enumerate(vars_compare):
        df_v = df_vars[df_vars["nombre"] == v].sort_values("fecha")
        if not df_v.empty:
            val_v    = float(df_v["valor"].iloc[-1])
            mu_v     = float(df_v["valor"].iloc[:-45].mean()) if len(df_v) > 50 else float(df_v["valor"].mean())
            cambio_v = float((df_v["valor"].iloc[-1] / df_v["valor"].iloc[-8] - 1) * 100) if len(df_v) >= 8 else 0.0
            sigma_v  = float((df_v["valor"].iloc[-5:].mean() - mu_v) / (df_v["valor"].iloc[:-45].std() + 1e-9)) if len(df_v) > 50 else 0.0
            with cols_cmp[i]:
                st.metric(
                    v.replace("_", " "),
                    f"{val_v:,.2f}",
                    f"{cambio_v:+.1f}% · {sigma_v:+.1f}σ",
                )

col_cmp_btn, col_cmp_info = st.columns([1, 3])
with col_cmp_btn:
    if st.button("💬 Preguntar al analista", key="expl_chat_open", use_container_width=True):
        st.session_state["chat_compare_vars"] = vars_compare
        if "chat_compare_msgs" not in st.session_state:
            st.session_state["chat_compare_msgs"] = []
with col_cmp_info:
    st.caption("El analista recibirá datos actuales, sigma y tendencia de todas las variables seleccionadas.")

st.divider()


# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN C — CHAT CON EL ANALISTA
# C1: alerta específica (botón dentro de alertas)
# C2: cruce de variables (botón en Explorador)
# Ambos fuera de loops/expanders → DOM estable
# ════════════════════════════════════════════════════════════════════════════
chat_var    = st.session_state.get("chat_var")
chat_alerta = st.session_state.get("chat_alerta", {})

if chat_var and _GEMINI_KEY:
    color_chat, bg_chat = SEV_COLORS.get(
        chat_alerta.get("severidad","Moderado"), ("#185FA5","#E6F1FB")
    )
    seccion_titulo(
        f"💬 Chat · {chat_var.replace('_',' ')}",
        f"Conversa con el analista de IA sobre esta alerta · {chat_alerta.get('severidad','')} "
        f"({chat_alerta.get('sigma_actual', 0):+.2f}σ)"
    )

    chat_key = f"chat_msgs_{chat_var}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    # Contexto de la alerta para el LLM
    _ctx = (
        f"Variable: {chat_var.replace('_',' ')} | Sigma: {chat_alerta.get('sigma_actual',0):+.2f}σ "
        f"({chat_alerta.get('severidad','')}) | Cambio 7d: {chat_alerta.get('cambio_7d_pct',0):+.1f}% | "
        f"Valor: {chat_alerta.get('valor_actual',0):,.2f} | Base: {chat_alerta.get('media_base',0):,.2f} | "
        f"Tendencia: {chat_alerta.get('tendencia','')}"
    )

    # Mostrar historial
    messages = st.session_state[chat_key]
    with st.container(height=380):
        if not messages:
            st.markdown(
                f"<div style='text-align:center;color:#9CA3AF;padding:40px;font-size:13px;'>"
                f"Escribe una pregunta sobre <b>{chat_var.replace('_',' ')}</b> "
                f"para iniciar la conversación.</div>",
                unsafe_allow_html=True
            )
        for msg in messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Input de chat (inline — no floating)
    prompt = st.chat_input(
        f"Pregunta sobre {chat_var.replace('_',' ')}...",
        key=f"chat_input_{chat_var}"
    )
    if prompt:
        messages.append({"role": "user", "content": prompt})
        # Construir prompt con contexto + historial
        hist_txt = "\n".join(
            ("Analista" if m['role'] == 'assistant' else "Usuario") + ": " + m['content']
            for m in messages[:-1]
        )
        conv_block = ("Conversación previa:\n" + hist_txt) if hist_txt else ""
        full_prompt = (
            f"Contexto de alerta: {_ctx}\n\n"
            f"{conv_block}\n\n"
            f"Usuario: {prompt}"
        )
        resp_txt = _call_gemini_text(full_prompt, _GEMINI_KEY)
        messages.append({"role": "assistant", "content": resp_txt})
        st.session_state[chat_key] = messages
        st.rerun()

    if st.button("🗑 Limpiar conversación", key="chat_clear"):
        st.session_state[chat_key] = []
        st.session_state["chat_var"] = None
        st.rerun()


# ── C2: Chat cruce de variables ───────────────────────────────────────────────
chat_compare_vars = st.session_state.get("chat_compare_vars", [])

if chat_compare_vars and _GEMINI_KEY:
    seccion_titulo(
        f"💬 Analista · Cruce de variables ({len(chat_compare_vars)})",
        "El analista cruza los datos de todas las variables seleccionadas para responder tu pregunta"
    )

    # Construir contexto con stats de cada variable
    def _ctx_compare(vars_list: list[str]) -> str:
        partes = []
        for v in vars_list:
            df_v = df_vars[df_vars["nombre"] == v].sort_values("fecha") if not df_vars.empty else pd.DataFrame()
            if df_v.empty:
                partes.append(f"- {v.replace('_',' ')}: sin datos disponibles")
                continue
            val_v    = float(df_v["valor"].iloc[-1])
            mu_v     = float(df_v["valor"].iloc[:-45].mean()) if len(df_v) > 50 else float(df_v["valor"].mean())
            cambio_v = float((df_v["valor"].iloc[-1] / df_v["valor"].iloc[-8] - 1) * 100) if len(df_v) >= 8 else 0.0
            sigma_v  = float((df_v["valor"].iloc[-5:].mean() - mu_v) / (df_v["valor"].iloc[:-45].std() + 1e-9)) if len(df_v) > 50 else 0.0
            tend_v   = "alcista" if cambio_v > 0 else "bajista"
            # Última alerta detectada para esta variable (si existe)
            alerta_v = next((a for a in alertas_live if a["variable"] == v), None)
            alerta_txt = f" | Severidad: {alerta_v['severidad']}" if alerta_v else ""
            partes.append(
                f"- {v.replace('_',' ')}: valor={val_v:,.2f}, base={mu_v:,.2f}, "
                f"cambio_7d={cambio_v:+.1f}%, sigma={sigma_v:+.2f}σ, tendencia={tend_v}{alerta_txt}"
            )
        return "\n".join(partes)

    ctx_cmp = _ctx_compare(chat_compare_vars)

    # Badge visual con variables seleccionadas
    badges_html = "".join(
        f"<span style='background:#EEF2FF;color:#3730A3;padding:3px 10px;border-radius:20px;"
        f"font-size:12px;font-weight:600;margin-right:4px;'>{v.replace('_',' ')}</span>"
        for v in chat_compare_vars
    )
    st.markdown(
        f"<div style='margin-bottom:12px;'>Variables en contexto: {badges_html}</div>",
        unsafe_allow_html=True
    )

    cmp_key = "chat_compare_msgs"
    if cmp_key not in st.session_state:
        st.session_state[cmp_key] = []

    msgs_cmp = st.session_state[cmp_key]

    with st.container(height=380):
        if not msgs_cmp:
            nombres = ", ".join(v.replace("_", " ") for v in chat_compare_vars)
            st.markdown(
                f"<div style='text-align:center;color:#9CA3AF;padding:40px;font-size:13px;'>"
                f"Escribe una pregunta para analizar en conjunto:<br><b>{nombres}</b></div>",
                unsafe_allow_html=True
            )
        for msg in msgs_cmp:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    prompt_cmp = st.chat_input(
        "Pregunta sobre las variables seleccionadas...",
        key="chat_input_compare"
    )
    if prompt_cmp:
        msgs_cmp.append({"role": "user", "content": prompt_cmp})
        hist_txt_cmp = "\n".join(
            ("Analista" if m['role'] == 'assistant' else "Usuario") + ": " + m['content']
            for m in msgs_cmp[:-1]
        )
        conv_block_cmp = ("Conversación previa:\n" + hist_txt_cmp + "\n") if hist_txt_cmp else ""
        full_prompt_cmp = (
            f"Eres un analista de materias primas y mercados siderúrgicos para TYASA México.\n\n"
            f"Datos actuales de las variables seleccionadas:\n{ctx_cmp}\n\n"
            f"{conv_block_cmp}"
            f"Usuario: {prompt_cmp}\n\n"
            f"Responde cruzando la información de todas las variables, identifica correlaciones, "
            f"riesgos compartidos e impacto potencial en la operación de TYASA."
        )
        resp_cmp = _call_gemini_text(full_prompt_cmp, _GEMINI_KEY)
        msgs_cmp.append({"role": "assistant", "content": resp_cmp})
        st.session_state[cmp_key] = msgs_cmp
        st.rerun()

    col_cmp_clr, col_cmp_close = st.columns([1, 1])
    with col_cmp_clr:
        if st.button("🗑 Limpiar conversación", key="chat_compare_clear"):
            st.session_state[cmp_key] = []
            st.rerun()
    with col_cmp_close:
        if st.button("✕ Cerrar panel", key="chat_compare_close"):
            st.session_state["chat_compare_vars"] = []
            st.session_state[cmp_key] = []
            st.rerun()
