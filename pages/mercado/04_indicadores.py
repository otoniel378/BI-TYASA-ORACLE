"""
04_indicadores.py — Dashboard INEGI interactivo con alertas Z-score.
Cards compactas de overview + expanders con gráfica Plotly + análisis IA por indicador.
"""

import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from mercado.inegi.loaders import (
    GRUPOS_INEGI,
    INDICADORES_LABEL,
    calcular_alertas,
    load_sparklines,
    load_serie,
)
from mercado_noticias.analytics.ai_analysis import analizar_indicador_inegi

# ── API key ──────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

# ── Paleta de alertas ────────────────────────────────────────────────────────
_ALERT = {
    "Critico":  {"color": "#EF5350", "bg": "rgba(239,83,80,0.15)",   "icon": "⚠️"},
    "Alto":     {"color": "#FF9800", "bg": "rgba(255,152,0,0.15)",   "icon": "🔶"},
    "Moderado": {"color": "#FFC107", "bg": "rgba(255,193,7,0.12)",   "icon": "🔸"},
    "Normal":   {"color": "#66BB6A", "bg": "rgba(102,187,106,0.10)", "icon": "✅"},
}
_SURFACE = "#1A2535"
_ORDER   = {"Critico": 0, "Alto": 1, "Moderado": 2, "Normal": 3}


# ── Utilidades ───────────────────────────────────────────────────────────────
def _fmt(v) -> str:
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:.2f}M"
        if abs(f) >= 10_000:
            return f"{f:,.0f}"
        return f"{f:,.1f}"
    except Exception:
        return "—"


def _hex_rgba(hex_color: str, alpha: float = 0.15) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _calc_yoy(df_serie: pd.DataFrame):
    if df_serie.empty or len(df_serie) < 13:
        return None
    try:
        df_s = df_serie.sort_values("fecha")
        v_now = float(df_s.iloc[-1]["valor"])
        v_ago = float(df_s.iloc[-13]["valor"])
        return (v_now - v_ago) / abs(v_ago) * 100 if v_ago != 0 else None
    except Exception:
        return None


def _serie_to_list(df_serie: pd.DataFrame) -> list:
    if df_serie.empty:
        return []
    df_s = df_serie.sort_values("fecha").tail(12)
    result = []
    for _, r in df_s.iterrows():
        try:
            result.append((str(r["fecha"])[:7], float(r["valor"])))
        except Exception:
            pass
    return result


# ── SVG Sparkline ────────────────────────────────────────────────────────────
def _sparkline(values: list, color: str, uid: str, h: int = 40) -> str:
    try:
        vals = [float(v) for v in values if v is not None]
    except Exception:
        return ""
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1e-9
    W = 200
    pts = " ".join(
        f"{i/(len(vals)-1)*W:.1f},{h-4-(v-mn)/rng*(h-8):.1f}"
        for i, v in enumerate(vals)
    )
    area = f"0,{h} {pts} {W},{h}"
    return (
        f'<svg viewBox="0 0 {W} {h}" width="100%" height="{h}" '
        f'preserveAspectRatio="none" style="display:block;">'
        f'<defs><linearGradient id="{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#{uid})"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


# ── Tarjeta compacta (overview) ──────────────────────────────────────────────
def _card(clave: str, label: str, valor, var_mom, alerta: str,
          spk_vals: list, group_color: str) -> str:
    am = _ALERT.get(alerta, _ALERT["Normal"])
    badge = (
        f'<span style="font-size:9px;font-weight:700;padding:2px 7px;border-radius:20px;'
        f'background:{am["bg"]};color:{am["color"]};white-space:nowrap;">'
        f'{am["icon"]} {alerta.upper()}</span>'
    )
    try:
        v = float(var_mom)
        arrow = "▲" if v >= 0 else "▼"
        vc    = "#66BB6A" if v >= 0 else "#EF5350"
        var_html = f'<span style="color:{vc};font-size:11px;font-weight:500;">{arrow} {abs(v):.1f}% MoM</span>'
    except Exception:
        var_html = '<span style="color:#475569;font-size:11px;">— MoM</span>'
    svg = _sparkline(spk_vals, group_color, f"sg_{clave}", h=36)
    return (
        f'<div style="background:{_SURFACE};border-radius:12px;padding:14px 15px 10px;'
        f'border-left:4px solid {group_color};">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">'
        f'<div style="font-size:10px;color:#94A3B8;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.06em;line-height:1.35;flex:1;min-width:0;">{label}</div>'
        f'{badge}</div>'
        f'<div style="margin-top:8px;font-size:22px;font-weight:700;color:#E2E8F0;'
        f'font-family:\'Courier New\',monospace;">{_fmt(valor)}</div>'
        f'<div style="margin-top:3px;">{var_html}</div>'
        f'<div style="margin-top:8px;opacity:0.7;">{svg}</div>'
        f'</div>'
    )


def _group_grid(claves, alerts_idx, sparklines, group_color, desc) -> str:
    header = (
        f'<p style="color:#94A3B8;font-size:12.5px;margin:4px 0 14px;line-height:1.5;">{desc}</p>'
    )
    cards_html = ""
    for clave in claves:
        label = INDICADORES_LABEL.get(clave, clave)
        if clave in alerts_idx.index:
            row    = alerts_idx.loc[clave]
            valor  = row.get("ult_valor")
            var_m  = row.get("var_mom")
            alerta = row.get("alerta", "Normal")
        else:
            valor, var_m, alerta = None, None, "Normal"
        spk = sparklines.get(clave, [])
        cards_html += _card(clave, label, valor, var_m, alerta, spk, group_color)
    grid = (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));'
        f'gap:12px;">{cards_html}</div>'
    )
    return header + grid


def _alert_summary(df: pd.DataFrame) -> str:
    counts = df["alerta"].value_counts().to_dict() if not df.empty else {}
    items = ""
    for nivel in ["Critico", "Alto", "Moderado", "Normal"]:
        c  = counts.get(nivel, 0)
        am = _ALERT[nivel]
        items += (
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'padding:10px 22px;background:{am["bg"]};border-radius:10px;'
            f'border:1px solid {am["color"]}33;">'
            f'<span style="font-size:28px;font-weight:800;color:{am["color"]};line-height:1;">{c}</span>'
            f'<span style="font-size:10px;color:#94A3B8;margin-top:3px;white-space:nowrap;">'
            f'{am["icon"]} {nivel}</span></div>'
        )
    note = (
        f'<div style="flex:1;display:flex;align-items:center;padding-left:16px;">'
        f'<span style="font-size:11.5px;color:#475569;line-height:1.6;">'
        f'Sistema de alertas Z-score · ventana 24 meses<br>'
        f'<span style="color:#374151;">Crítico |z|&gt;2.5 · Alto |z|&gt;1.5 · Moderado |z|&gt;1.0</span>'
        f'</span></div>'
    )
    return (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;'
        f'padding:14px 16px;background:{_SURFACE};border-radius:14px;margin-bottom:2px;">'
        f'{items}{note}</div>'
    )


# ── Gráfica Plotly ───────────────────────────────────────────────────────────
def _make_chart(df_serie: pd.DataFrame, label: str, color: str) -> go.Figure:
    df_s = df_serie.sort_values("fecha")
    fig  = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_s["fecha"], y=df_s["valor"],
        mode="lines+markers", name=label,
        line=dict(color=color, width=2.5),
        fill="tozeroy", fillcolor=_hex_rgba(color, 0.12),
        marker=dict(size=5, color=color),
        hovertemplate="%{x|%Y-%m}: %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#0F1923", plot_bgcolor="#1A2535",
        font=dict(color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#2A3A52", showgrid=True, title=None, tickformat="%b %Y"),
        yaxis=dict(gridcolor="#2A3A52", showgrid=True, title=None),
        margin=dict(l=50, r=20, t=20, b=50),
        height=280, showlegend=False, hovermode="x unified",
    )
    return fig


# ── Panel de estadísticas ────────────────────────────────────────────────────
def _stats_card(row, df_serie: pd.DataFrame, color: str) -> str:
    if row is None:
        return '<div style="color:#64748B;padding:8px;font-size:12px;">Sin estadísticas disponibles.</div>'

    alerta  = row.get("alerta", "Normal")
    am      = _ALERT.get(alerta, _ALERT["Normal"])
    var_yoy = _calc_yoy(df_serie)

    def arrow(v):
        try:
            f = float(v)
            c = "#66BB6A" if f >= 0 else "#EF5350"
            return c, f"{'▲' if f >= 0 else '▼'} {abs(f):.1f}%"
        except Exception:
            return "#64748B", "—"

    mom_c, mom_s = arrow(row.get("var_mom"))
    yoy_c, yoy_s = arrow(var_yoy) if var_yoy is not None else ("#64748B", "—")

    try:
        z  = float(row.get("z_score") or 0)
        zs = "—" if z != z else f"{z:+.2f}σ"   # z != z → NaN check
        zc = am["color"] if alerta != "Normal" else "#66BB6A"
    except Exception:
        zs, zc = "—", "#64748B"

    def row_html(lbl, val, vc="#E2E8F0"):
        return (
            f'<div style="display:flex;justify-content:space-between;'
            f'padding:7px 0;border-bottom:1px solid #2A3A52;">'
            f'<span style="color:#94A3B8;font-size:11.5px;">{lbl}</span>'
            f'<span style="color:{vc};font-size:12px;font-weight:600;">{val}</span></div>'
        )

    ult_fecha = str(row.get("ult_fecha", ""))[:7]
    badge = (
        f'<div style="display:inline-block;padding:4px 12px;background:{am["bg"]};'
        f'border-radius:20px;font-size:11px;font-weight:700;color:{am["color"]};">'
        f'{am["icon"]} {alerta.upper()}</div>'
    )
    rows = (
        row_html("Último dato", ult_fecha) +
        row_html("Valor actual", _fmt(row.get("ult_valor"))) +
        row_html("Variación MoM", mom_s, mom_c) +
        row_html("Variación YoY", yoy_s, yoy_c) +
        row_html("Media 24 meses", _fmt(row.get("media"))) +
        row_html("Desv. estándar", _fmt(row.get("std"))) +
        row_html("Z-score", zs, zc)
    )
    return (
        f'<div style="background:{_SURFACE};border-radius:12px;padding:16px 18px;'
        f'border-left:4px solid {color};">'
        f'<div style="margin-bottom:12px;">{badge}</div>'
        f'{rows}</div>'
    )


# ── Resultado del análisis IA ────────────────────────────────────────────────
def _render_ai_result(result: dict | None) -> str:
    if not result:
        return (
            f'<div style="color:#475569;font-size:12px;padding:12px;text-align:center;'
            f'background:{_SURFACE};border-radius:10px;">'
            f'Haz clic en "🤖 Analizar" para generar el análisis de impacto en TYASA.</div>'
        )
    error   = result.get("_error")
    analisis = result.get("analisis", "")
    if error and not analisis:
        return (
            f'<div style="color:#EF5350;padding:12px;font-size:12px;border-radius:8px;'
            f'background:rgba(239,83,80,0.08);">{error}</div>'
        )
    cached_badge = (
        ' <span style="font-size:9px;color:#475569;">📦 caché</span>'
        if result.get("_cached") else ""
    )
    p_html = "".join(
        f'<p style="margin:0 0 12px;color:#CBD5E1;font-size:13px;line-height:1.7;">{p}</p>'
        for p in analisis.strip().split("\n\n") if p.strip()
    ) or f'<p style="color:#CBD5E1;font-size:13px;">{analisis.strip()}</p>'

    return (
        f'<div style="background:{_SURFACE};border-radius:12px;padding:18px 20px;'
        f'border-left:4px solid #4A7BA7;margin-top:4px;">'
        f'<div style="font-size:10px;color:#64748B;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:12px;">ANÁLISIS IA · IMPACTO TYASA{cached_badge}</div>'
        f'{p_html}</div>'
    )


# ── Contenido del expander (chart + stats + AI) ──────────────────────────────
def _render_detail(clave: str, tab_key: str, g: dict,
                   alerts_idx: pd.DataFrame, gemini_key: str) -> None:
    label = INDICADORES_LABEL.get(clave, clave)
    row   = alerts_idx.loc[clave] if clave in alerts_idx.index else None

    # Cargar serie histórica (cached en BQ)
    with st.spinner(f"Cargando {label}..."):
        df_serie = load_serie(clave, periodos=36)

    # Chart + stats
    col_chart, col_stats = st.columns([3, 2])
    with col_chart:
        if not df_serie.empty:
            st.plotly_chart(
                _make_chart(df_serie, label, g["color"]),
                use_container_width=True,
                key=f"plt_{clave}_{tab_key}",
            )
        else:
            st.info("Sin datos históricos para este indicador en BigQuery.")
    with col_stats:
        st.html(_stats_card(row, df_serie, g["color"]))

    # AI analysis
    st.divider()
    skey = f"inegi_ai_{clave}"
    col_lbl, col_btn, col_frz = st.columns([4, 1.5, 1])
    with col_lbl:
        st.markdown(
            "<p style='color:#94A3B8;font-size:12px;margin:8px 0 0;'>"
            "Análisis de impacto con Gemini · contexto TYASA y la industria siderúrgica mexicana</p>",
            unsafe_allow_html=True,
        )
    with col_btn:
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        run_ai = st.button(
            "🤖 Analizar", key=f"runai_{clave}_{tab_key}", use_container_width=True
        )
    with col_frz:
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        frz = st.checkbox("Regenerar", value=False, key=f"frz_{clave}_{tab_key}")

    if run_ai and gemini_key:
        st.session_state[skey] = analizar_indicador_inegi(
            clave       = clave,
            label       = label,
            group_label = g["label"],
            group_desc  = g["desc"],
            alerta      = row.get("alerta", "Normal") if row is not None else "Normal",
            z_score     = float(row.get("z_score", 0)) if row is not None else 0.0,
            ult_valor   = row.get("ult_valor") if row is not None else None,
            var_mom     = row.get("var_mom") if row is not None else None,
            var_yoy     = _calc_yoy(df_serie),
            media       = row.get("media") if row is not None else None,
            valores_recientes = _serie_to_list(df_serie),
            api_key     = gemini_key,
            force_refresh = frz,
        )
    elif run_ai:
        st.session_state[skey] = {
            "analisis": "",
            "_cached": False,
            "_error": "Configura GEMINI_API_KEY en .streamlit/secrets.toml",
        }

    st.html(_render_ai_result(st.session_state.get(skey)))


# ── Página principal ─────────────────────────────────────────────────────────
def main():
    render()


def render():
    col_title, col_btn = st.columns([6, 1])
    with col_title:
        st.markdown(
            "<h2 style='color:#E2E8F0;margin-bottom:2px;'>Indicadores INEGI</h2>"
            "<p style='color:#64748B;margin:0;'>37 series macroeconómicas · 10 grupos · "
            "alertas Z-score · análisis IA por indicador</p>",
            unsafe_allow_html=True,
        )
    with col_btn:
        st.markdown("<div style='padding-top:14px;'></div>", unsafe_allow_html=True)
        if st.button("⟳ Refrescar", use_container_width=True, key="inegi_refresh"):
            calcular_alertas.clear()
            load_sparklines.clear()
            load_serie.clear()
            st.rerun()

    st.divider()

    # ── Carga de datos ───────────────────────────────────────────────────────
    try:
        with st.spinner("Calculando alertas Z-score..."):
            df_alerts  = calcular_alertas()
            sparklines = load_sparklines(12)
    except Exception as exc:
        st.error(f"Error al conectar con BigQuery: {exc}")
        st.info("Verifica que `gold_indicadores_inegi` exista y que la autenticación GCP esté activa.")
        return

    if df_alerts.empty:
        st.info("Sin datos en `gold_indicadores_inegi`. Ejecuta `scripts/script_inegi.py` para cargar datos.")
        return

    df_alerts["clave"] = df_alerts["clave"].astype(str)
    alerts_idx = df_alerts.drop_duplicates("clave").set_index("clave")

    # ── Banner de alertas ────────────────────────────────────────────────────
    st.html(_alert_summary(df_alerts))
    st.markdown("<div style='margin-bottom:6px;'></div>", unsafe_allow_html=True)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    group_keys  = list(GRUPOS_INEGI.keys())
    non_normal  = df_alerts[df_alerts["alerta"] != "Normal"]
    alert_count = len(non_normal)
    alert_label = f"🔔 Alertas ({alert_count})" if alert_count else "🔔 Alertas"
    tabs = st.tabs(
        [f"{GRUPOS_INEGI[g]['icon']} {g}" for g in group_keys] + [alert_label]
    )

    # ── Group tabs ───────────────────────────────────────────────────────────
    for i, gkey in enumerate(group_keys):
        g      = GRUPOS_INEGI[gkey]
        claves = g["claves"]
        with tabs[i]:
            # Overview compacto
            st.html(_group_grid(claves, alerts_idx, sparklines, g["color"], g["desc"]))

            st.markdown(
                "<p style='color:#64748B;font-size:11px;margin:16px 0 8px;'>"
                "▼  Haz clic en un indicador para ver su gráfica completa y análisis IA</p>",
                unsafe_allow_html=True,
            )

            # Expander por indicador
            for clave in claves:
                label  = INDICADORES_LABEL.get(clave, clave)
                alerta = alerts_idx.loc[clave]["alerta"] if clave in alerts_idx.index else "Normal"
                am     = _ALERT[alerta]
                try:
                    z_val  = float(alerts_idx.loc[clave]["z_score"]) if clave in alerts_idx.index else 0.0
                    z_str  = f"  z={z_val:+.2f}" if alerta != "Normal" else ""
                except Exception:
                    z_str = ""
                exp_label = f"{am['icon']} {label}  ·  {alerta.upper()}{z_str}"
                with st.expander(exp_label, expanded=False):
                    _render_detail(clave, gkey, g, alerts_idx, _GEMINI_KEY)

    # ── Alerts tab ───────────────────────────────────────────────────────────
    with tabs[-1]:
        if non_normal.empty:
            st.success("Todos los indicadores están en rango normal.")
        else:
            df_sorted = non_normal.copy()
            df_sorted["_ord"] = df_sorted["alerta"].map(_ORDER).fillna(3)
            df_sorted = df_sorted.sort_values("_ord")

            st.html(
                f"<p style='color:#94A3B8;font-size:13px;margin:4px 0 12px;'>"
                f"{len(df_sorted)} indicadores fuera de rango normal — ordenados por severidad.</p>"
            )

            clave_to_group = {}
            for gk, gv in GRUPOS_INEGI.items():
                for c in gv["claves"]:
                    clave_to_group[c] = gk

            for _, arow in df_sorted.iterrows():
                clave_a  = str(arow["clave"])
                label_a  = INDICADORES_LABEL.get(clave_a, clave_a)
                alerta_a = arow.get("alerta", "Normal")
                am_a     = _ALERT[alerta_a]
                gkey_a   = clave_to_group.get(clave_a, "?")
                g_a      = GRUPOS_INEGI.get(gkey_a, GRUPOS_INEGI["IMAI"])
                try:
                    z_val = float(arow["z_score"])
                    z_str = f"  z={z_val:+.2f}"
                except Exception:
                    z_str = ""
                exp_label = (
                    f"{am_a['icon']} {label_a}  ·  {alerta_a.upper()}{z_str}  "
                    f"[{g_a['icon']} {gkey_a}]"
                )
                with st.expander(exp_label, expanded=(alerta_a == "Critico")):
                    _render_detail(clave_a, f"alerta_{clave_a}", g_a, alerts_idx, _GEMINI_KEY)

    # ── Footer ───────────────────────────────────────────────────────────────
    ult = ""
    if "ult_fecha" in df_alerts.columns:
        try:
            ult = f" · último dato: {str(df_alerts['ult_fecha'].dropna().max())[:7]}"
        except Exception:
            pass
    st.caption(
        f"Fuente: INEGI BIE · tabla gold_indicadores_inegi · "
        f"{len(df_alerts)} indicadores activos{ult}"
    )


if __name__ == "__main__":
    main()
