"""
pages/mercado/05_sentimiento.py — Termómetro de Sentimiento Siderúrgico.
Clasifica noticias en tiempo real con Gemini y muestra la temperatura del mercado
desde la perspectiva de TYASA como productora EAF de acero plano.
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
_OK = "#16A34A"; _WA = "#D97706"; _ER = "#DC2626"
_T1 = "#0F172A"; _T2 = "#64748B"; _T3 = "#94A3B8"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.html("""<style>
.sm-card{background:#fff;border-radius:12px;padding:14px 16px;
  border:1px solid #E2E8F0;box-shadow:0 1px 3px rgba(0,0,0,.05);margin-bottom:6px;}
.sm-label{font-size:9.5px;font-weight:700;color:#94A3B8;text-transform:uppercase;
  letter-spacing:.07em;margin-bottom:3px;}
.sm-val{font-size:19px;font-weight:800;line-height:1.1;}
.sm-badge{display:inline-block;padding:2px 9px;border-radius:20px;
  font-size:10px;font-weight:700;letter-spacing:.04em;}
.sm-news{background:#F8FAFC;border-radius:8px;padding:9px 13px;
  border-left:4px solid #E2E8F0;margin-bottom:5px;}
</style>""")

# ── Sidebar ───────────────────────────────────────────────────────────────────
sidebar_header("Sentimiento", "🌡️")
dias_hist = st.sidebar.slider("Período de análisis (días)", 7, 90, 30, key="sent_dias")
grupo_filtro = st.sidebar.selectbox(
    "Filtrar por grupo",
    ["Todos", "Urgente", "Mercado Global", "Materias Primas", "Regulación",
     "Energía", "Infraestructura", "Industria", "Economía", "Empresas", "Comercio"],
    key="sent_grupo",
)
alcance_filtro = st.sidebar.radio(
    "Alcance", ["Todos", "nacional", "internacional", "ambos"],
    key="sent_alcance",
)

# ── Título ────────────────────────────────────────────────────────────────────
st.html(f"""
<div style="margin-bottom:6px;">
  <h2 style="color:{_P};margin:0;font-size:1.5rem;">🌡️ Termómetro de Sentimiento Siderúrgico</h2>
  <p style="color:{_T2};margin:0;font-size:0.85rem;">
    Clasificación IA de noticias desde la perspectiva de TYASA — actualizado diariamente
  </p>
</div>
""")
st.divider()

# ── Carga de datos BQ ─────────────────────────────────────────────────────────
_bq_ok = False
df_sent = pd.DataFrame()
df_hist = pd.DataFrame()

try:
    from mercado_noticias.loaders import load_sentimiento_noticias, load_sentimiento_historico
    with st.spinner("Cargando sentimiento desde BigQuery..."):
        df_sent = load_sentimiento_noticias(dias=dias_hist)
        df_hist = load_sentimiento_historico(dias=dias_hist)
    _bq_ok = True
except Exception as _e:
    st.info(f"Datos históricos no disponibles ({_e}). Puedes clasificar noticias en tiempo real.")

# Aplicar filtros
if _bq_ok and not df_sent.empty:
    if grupo_filtro != "Todos" and "grupo_tematico" in df_sent.columns:
        df_sent = df_sent[df_sent["grupo_tematico"] == grupo_filtro]
    if alcance_filtro != "Todos" and "alcance" in df_sent.columns:
        df_sent = df_sent[df_sent["alcance"] == alcance_filtro]

# ══════════════════════════════════════════════════════════════════════════════
# ANÁLISIS EN TIEMPO REAL — botón para clasificar noticias frescas
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Análisis en Tiempo Real", "Clasifica noticias de hoy con Gemini")

_RT_KEY = f"sentimiento_rt_{date.today().isoformat()}_{grupo_filtro}_{alcance_filtro}"

col_btn, col_info = st.columns([1, 3])
with col_btn:
    run_rt = st.button(
        "🤖 Clasificar noticias de hoy",
        key="btn_sent_rt",
        disabled=not bool(_GEMINI_KEY),
        use_container_width=True,
    )
with col_info:
    if not _GEMINI_KEY:
        st.caption("Configura GEMINI_API_KEY en secrets.toml.")
    else:
        st.caption("Busca y clasifica noticias siderúrgicas de hoy con IA. Usa caché — no repite llamadas ya realizadas.")

if run_rt and _GEMINI_KEY:
    from mercado_noticias.analytics.noticias import buscar_noticias_sector, GRUPOS_INDUSTRIA, GRUPOS_NACIONAL, GRUPOS_INTERNACIONAL
    from mercado_noticias.analytics.sentimiento import clasificar_lote, calcular_indice_sentimiento, resultados_a_dataframe

    grupos_buscar = {}
    if grupo_filtro == "Todos":
        grupos_buscar = {**GRUPOS_INDUSTRIA, **GRUPOS_NACIONAL, **GRUPOS_INTERNACIONAL}
    else:
        grupos_buscar = {grupo_filtro: (
            {**GRUPOS_INDUSTRIA, **GRUPOS_NACIONAL, **GRUPOS_INTERNACIONAL}.get(grupo_filtro, [grupo_filtro])
        )}

    noticias_frescas: list[dict] = []
    seen: set[str] = set()
    for grp in list(grupos_buscar.keys())[:6]:
        nots = buscar_noticias_sector(grp, max_resultados=6)
        for n in nots:
            if n.get("url", "") not in seen:
                seen.add(n.get("url", ""))
                n["grupo"] = grp
                noticias_frescas.append(n)

    resultados_rt = clasificar_lote(noticias_frescas, _GEMINI_KEY, max_noticias=40)
    indice_rt = calcular_indice_sentimiento(resultados_rt)
    st.session_state[_RT_KEY] = {"resultados": resultados_rt, "indice": indice_rt}


# ══════════════════════════════════════════════════════════════════════════════
# MOSTRAR RESULTADOS — tiempo real o histórico
# ══════════════════════════════════════════════════════════════════════════════
rt_data   = st.session_state.get(_RT_KEY)
usar_rt   = rt_data is not None
resultados_activos = rt_data["resultados"] if usar_rt else []
indice_activo = rt_data["indice"] if usar_rt else None

if not usar_rt and _bq_ok and not df_sent.empty:
    from mercado_noticias.analytics.sentimiento import calcular_indice_sentimiento
    indice_activo = calcular_indice_sentimiento([
        {"sentimiento": r.sentimiento if hasattr(r, "sentimiento") else r.get("sentimiento","neutro"),
         "score": r.score if hasattr(r, "score") else r.get("score", 0.0)}
        for _, r in df_sent.iterrows()
    ] if not df_sent.empty else [])

st.divider()

# ── SECCIÓN: Termómetro global ────────────────────────────────────────────────
seccion_titulo("Temperatura del Mercado", f"Últimos {dias_hist} días — perspectiva TYASA")

if indice_activo:
    col_gauge, col_kpis = st.columns([1, 2])

    with col_gauge:
        indice_val = indice_activo["indice"]
        gauge_val  = (indice_val + 1) / 2 * 10   # escala -1..1 → 0..10

        fig_t = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=gauge_val,
            number={"font": {"size": 28, "color": indice_activo["color"]},
                    "suffix": "/10", "valueformat": ".1f"},
            delta={"reference": 5, "valueformat": ".1f",
                   "increasing": {"color": _OK}, "decreasing": {"color": _ER}},
            title={"text": f"<b>{indice_activo['nivel']}</b>",
                   "font": {"size": 13, "color": indice_activo["color"]}},
            gauge={
                "axis": {"range": [0, 10], "tickfont": {"size": 9}},
                "bar":  {"color": indice_activo["color"], "thickness": 0.25},
                "bgcolor": "white", "borderwidth": 0,
                "steps": [
                    {"range": [0,  3.5], "color": "#FEE2E2"},
                    {"range": [3.5, 6.5], "color": "#FEF3C7"},
                    {"range": [6.5, 10],  "color": "#DCFCE7"},
                ],
            },
        ))
        fig_t.update_layout(
            height=220, margin=dict(t=30, b=0, l=10, r=10),
            paper_bgcolor="white", font=dict(family="Segoe UI, sans-serif"),
        )
        st.plotly_chart(fig_t, use_container_width=True, config={"displayModeBar": False})
        st.caption(f"Score: {indice_activo['indice']:+.3f} (–1 muy negativo → +1 muy positivo)")

    with col_kpis:
        n_pos = indice_activo.get("n_positivas", 0)
        n_neg = indice_activo.get("n_negativas", 0)
        n_neu = indice_activo.get("n_neutras",   0)
        total = indice_activo.get("total", n_pos + n_neg + n_neu) or 1

        st.html(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px;">
          <div style="background:#DCFCE7;border-radius:10px;padding:12px;text-align:center;">
            <div style="font-size:9.5px;font-weight:700;color:#166534;text-transform:uppercase;">
              Positivas para TYASA
            </div>
            <div style="font-size:26px;font-weight:800;color:{_OK};">{n_pos}</div>
            <div style="font-size:10px;color:#166534;">{n_pos/total*100:.0f}% del total</div>
          </div>
          <div style="background:#F1F5F9;border-radius:10px;padding:12px;text-align:center;">
            <div style="font-size:9.5px;font-weight:700;color:#64748B;text-transform:uppercase;">
              Neutras
            </div>
            <div style="font-size:26px;font-weight:800;color:{_T2};">{n_neu}</div>
            <div style="font-size:10px;color:{_T3};">{n_neu/total*100:.0f}% del total</div>
          </div>
          <div style="background:#FEE2E2;border-radius:10px;padding:12px;text-align:center;">
            <div style="font-size:9.5px;font-weight:700;color:#991B1B;text-transform:uppercase;">
              Negativas para TYASA
            </div>
            <div style="font-size:26px;font-weight:800;color:{_ER};">{n_neg}</div>
            <div style="font-size:10px;color:#991B1B;">{n_neg/total*100:.0f}% del total</div>
          </div>
        </div>""")

        # Top señales detectadas
        por_señal = indice_activo.get("por_señal", {})
        if por_señal:
            señal_items = sorted(por_señal.items(), key=lambda x: x[1], reverse=True)[:5]
            señal_html = "".join(
                f'<span class="sm-badge" style="background:#EFF6FF;color:#1E40AF;margin:2px;">'
                f'{s.replace("_"," ")} ({n})</span>'
                for s, n in señal_items
            )
            st.html(f'<div style="margin-top:4px;"><div style="font-size:10px;font-weight:700;'
                    f'color:{_T3};text-transform:uppercase;margin-bottom:4px;">Señales detectadas</div>'
                    f'{señal_html}</div>')

st.divider()

# ── SECCIÓN: Tendencia histórica ──────────────────────────────────────────────
seccion_titulo("Tendencia de Sentimiento", "Score promedio diario — positivo = favorable para TYASA")

df_trend = df_hist if _bq_ok and not df_hist.empty else pd.DataFrame()

if not df_trend.empty and "fecha_pub" in df_trend.columns:
    trend_diario = df_trend.groupby("fecha_pub")["score_avg"].mean().reset_index()
    trend_diario = trend_diario.sort_values("fecha_pub")

    colors_bar = [_OK if v >= 0.05 else (_ER if v <= -0.05 else _T3)
                  for v in trend_diario["score_avg"]]

    fig_trend = go.Figure(go.Bar(
        x=trend_diario["fecha_pub"], y=trend_diario["score_avg"],
        marker_color=colors_bar,
        hovertemplate="%{x|%d %b}<br>Score: %{y:+.3f}<extra></extra>",
        name="Score diario",
    ))
    fig_trend.add_hline(y=0, line_dash="dot", line_color="#94A3B8", line_width=1.5,
                        annotation_text="Neutro", annotation_font_size=9)
    fig_trend.update_layout(
        height=240, margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="white", plot_bgcolor="#F8FAFC", showlegend=False,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#EEF2FF", title="Score"),
        font=dict(family="Segoe UI, sans-serif", size=11),
    )
    st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})
elif not usar_rt:
    st.info("Ejecuta el script `update_sentimiento_noticias.py` para acumular histórico de sentimiento.")

# ── SECCIÓN: Mapa de calor por variable ───────────────────────────────────────
if _bq_ok and not df_hist.empty and "variable_principal" in df_hist.columns:
    st.divider()
    seccion_titulo("Sentimiento por Variable Siderúrgica", "Promedio de score por tema")

    var_scores = (
        df_hist.groupby("variable_principal")["score_avg"]
        .mean()
        .reset_index()
        .sort_values("score_avg")
    )
    var_scores["color"] = var_scores["score_avg"].apply(
        lambda v: _OK if v >= 0.1 else (_ER if v <= -0.1 else _T3)
    )
    var_scores["label"] = var_scores["variable_principal"].str.replace("_", " ")

    fig_var = go.Figure(go.Bar(
        x=var_scores["score_avg"], y=var_scores["label"], orientation="h",
        marker_color=var_scores["color"].tolist(),
        text=var_scores["score_avg"].apply(lambda v: f"{v:+.2f}"),
        textposition="outside", textfont=dict(size=9),
        hovertemplate="%{y}<br>Score: %{x:+.3f}<extra></extra>",
    ))
    fig_var.add_vline(x=0, line_dash="solid", line_color="#94A3B8", line_width=1)
    fig_var.update_layout(
        height=max(280, len(var_scores) * 28 + 60),
        margin=dict(t=10, b=10, l=10, r=80),
        paper_bgcolor="white", plot_bgcolor="#F8FAFC", showlegend=False,
        xaxis=dict(title="Score promedio", gridcolor="#EEF2FF"),
        yaxis=dict(tickfont=dict(size=10)),
        font=dict(family="Segoe UI, sans-serif", size=11),
    )
    st.plotly_chart(fig_var, use_container_width=True, config={"displayModeBar": False})

st.divider()

# ── SECCIÓN: Alertas de cambio de sentimiento ─────────────────────────────────
if _bq_ok and not df_sent.empty:
    seccion_titulo("Alertas de Cambio Brusco", "Variables con viraje de sentimiento reciente")

    from mercado_noticias.analytics.sentimiento import detectar_cambio_sentimiento
    alertas_sent = detectar_cambio_sentimiento(df_sent, ventana_reciente=3, ventana_base=dias_hist)

    if not alertas_sent:
        st.success("✅ Sin cambios bruscos de sentimiento en los últimos 3 días.")
    else:
        for a in alertas_sent[:6]:
            col_bord = _ER if a["cambio"] < 0 else _OK
            bg = "#FEE2E2" if a["cambio"] < 0 else "#DCFCE7"
            dot = "🔴" if a["nivel"] == "Alta" else "🟠" if a["nivel"] == "Media" else "🟡"
            st.html(f"""<div style="background:{bg};border-radius:10px;padding:12px 14px;
                 border-left:4px solid {col_bord};margin-bottom:6px;
                 display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="font-size:12.5px;font-weight:700;color:{_T1};">
                  {dot} {a['variable'].replace('_',' ')}
                </div>
                <div style="font-size:11px;color:{_T2};margin-top:2px;">{a['descripcion']}</div>
              </div>
              <div style="text-align:right;">
                <div style="font-size:18px;font-weight:800;color:{col_bord};">{a['cambio']:+.2f}</div>
                <div style="font-size:9px;color:{_T3};">cambio score</div>
              </div>
            </div>""")
    st.divider()

# ── SECCIÓN: Noticias clasificadas ────────────────────────────────────────────
seccion_titulo("Noticias Clasificadas", "Ordenadas por impacto en TYASA")

# Fuente: tiempo real o BQ
noticias_mostrar = []
if usar_rt and resultados_activos:
    noticias_mostrar = sorted(resultados_activos, key=lambda x: abs(x.get("score", 0.0)), reverse=True)
elif _bq_ok and not df_sent.empty:
    noticias_mostrar = df_sent.sort_values("score", ascending=False, key=abs).to_dict("records")

_SENT_STYLE = {
    "positivo": (_OK, "#DCFCE7", "✅"),
    "negativo": (_ER, "#FEE2E2", "⚠️"),
    "neutro":   (_T3, "#F1F5F9", "ℹ️"),
}

filtro_sent = st.radio(
    "Mostrar:", ["Todas", "Positivas para TYASA", "Negativas para TYASA"],
    horizontal=True, key="sent_filtro_noticia",
)

if filtro_sent == "Positivas para TYASA":
    noticias_mostrar = [n for n in noticias_mostrar if n.get("sentimiento") == "positivo"]
elif filtro_sent == "Negativas para TYASA":
    noticias_mostrar = [n for n in noticias_mostrar if n.get("sentimiento") == "negativo"]

if not noticias_mostrar:
    st.info("Sin noticias clasificadas. Ejecuta el análisis en tiempo real o el script diario.")
else:
    st.caption(f"Mostrando {min(len(noticias_mostrar), 20)} de {len(noticias_mostrar)} noticias clasificadas.")
    for n in noticias_mostrar[:20]:
        sent  = n.get("sentimiento", "neutro")
        score = float(n.get("score", 0.0) or 0.0)
        color, bg, dot = _SENT_STYLE.get(sent, (_T3, "#F1F5F9", "ℹ️"))

        titulo  = (n.get("titulo", "") or "Sin título")[:90]
        fuente  = n.get("fuente", "")
        fecha   = str(n.get("fecha_pub", ""))[:10]
        var     = (n.get("variable_principal", "") or "").replace("_", " ")
        señal   = (n.get("señal", "") or "").replace("_", " ")
        razon   = n.get("razon", "")
        url     = n.get("url", "#")
        alcance = n.get("alcance", "")
        grupo   = n.get("grupo_tematico") or n.get("grupo", "")

        alcance_badge = (
            f'<span class="sm-badge" style="background:#EFF6FF;color:#1E40AF;">{alcance}</span>'
            if alcance else ""
        )
        grupo_badge = (
            f'<span class="sm-badge" style="background:#F3F4F6;color:#374151;">{grupo}</span>'
            if grupo else ""
        )

        st.html(f"""<div class="sm-news" style="border-left-color:{color};background:{bg};">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
            <div style="flex:1;">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
                <span style="font-size:14px;">{dot}</span>
                <a href="{url}" target="_blank" style="font-size:12.5px;font-weight:700;
                   color:{_P};text-decoration:none;">{titulo}</a>
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px;">
                {alcance_badge}{grupo_badge}
                <span class="sm-badge" style="background:white;color:{color};
                      border:1.5px solid {color};">{sent} {score:+.2f}</span>
                {"<span class='sm-badge' style='background:#F0FDF4;color:#166534;'>" + señal + "</span>" if señal else ""}
              </div>
              {"<div style='font-size:11px;color:" + _T2 + ";font-style:italic;'>" + razon + "</div>" if razon else ""}
            </div>
            <div style="text-align:right;min-width:80px;">
              <div style="font-size:10px;color:{_T3};">{fuente}</div>
              <div style="font-size:10px;color:{_T3};">{fecha}</div>
              {"<div style='font-size:9.5px;font-weight:700;color:" + _T2 + ";'>" + var + "</div>" if var else ""}
            </div>
          </div>
        </div>""")

# ── SECCIÓN: Síntesis IA ──────────────────────────────────────────────────────
st.divider()
seccion_titulo("Síntesis Ejecutiva IA", "Resumen del clima de mercado para TYASA")

_SINT_KEY = f"sentimiento_sintesis_{date.today().isoformat()}_{grupo_filtro}"

col_sb, col_si = st.columns([1, 3])
with col_sb:
    run_sint = st.button("🤖 Generar síntesis", key="btn_sint_sent",
                         disabled=not bool(_GEMINI_KEY), use_container_width=True)
with col_si:
    if not _GEMINI_KEY:
        st.caption("Requiere GEMINI_API_KEY.")

if run_sint and _GEMINI_KEY:
    nots_sint = noticias_mostrar[:12]
    pos_txt = "\n".join(
        f"+ {n.get('titulo','')[:70]} ({n.get('variable_principal','').replace('_',' ')})"
        for n in nots_sint if n.get("sentimiento") == "positivo"
    )[:600] or "— Sin señales positivas —"
    neg_txt = "\n".join(
        f"- {n.get('titulo','')[:70]} ({n.get('variable_principal','').replace('_',' ')})"
        for n in nots_sint if n.get("sentimiento") == "negativo"
    )[:600] or "— Sin señales negativas —"

    score_gbl = indice_activo["indice"] if indice_activo else 0.0
    nivel_gbl = indice_activo["nivel"]  if indice_activo else "Neutro"

    prompt = f"""Eres analista sénior de TYASA, acería mexicana EAF de acero plano.
El índice de sentimiento siderúrgico HOY es {score_gbl:+.2f} ({nivel_gbl}).

Noticias POSITIVAS para TYASA:
{pos_txt}

Noticias NEGATIVAS para TYASA:
{neg_txt}

Genera exactamente 4 bullets ejecutivos (máx 20 palabras c/u) con emoji relevante:
1. Estado general del mercado de acero hoy
2. Principal oportunidad que debe aprovechar ventas
3. Principal riesgo que debe vigilar dirección
4. Acción concreta recomendada para esta semana

Sin introducción. Sin cierre. Solo los 4 bullets."""

    from mercado_noticias.analytics.ai_analysis import _call_gemini_text
    st.session_state[_SINT_KEY] = _call_gemini_text(prompt, _GEMINI_KEY)


def _render_sint(txt: str | None) -> str:
    if not txt:
        return ""
    bullets = [l.strip() for l in txt.strip().split("\n") if l.strip()]
    items   = "".join(
        f"<li style='margin-bottom:8px;font-size:13px;color:{_T1};line-height:1.4;'>{b}</li>"
        for b in bullets
    )
    return f"""<div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;
         padding:16px 20px;margin-top:8px;">
      <div style="font-size:10px;font-weight:700;color:#0369A1;text-transform:uppercase;
           letter-spacing:.06em;margin-bottom:10px;">
        🤖 Síntesis IA — {date.today().strftime('%d %b %Y')} — Perspectiva TYASA
      </div>
      <ul style="margin:0;padding-left:18px;">{items}</ul>
    </div>"""

st.html(_render_sint(st.session_state.get(_SINT_KEY)))
