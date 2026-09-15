"""
06_inteligencia_clientes.py — Inteligencia de Clientes — Aceros Planos Negros.
Ficha 360°: perfil, semáforo de salud, comportamiento, YoY, mix, estacionalidad, briefing IA.
Power BI + Apple design system.
"""

import os, sys, calendar
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from aceros_planos.negros.loaders import (
    load_gold_demanda_cliente,
    load_gold_cliente_producto,
    load_transacciones_cliente,
    get_catalogo_clientes,
)
from mercado_noticias.analytics.ai_analysis import generar_briefing_cliente

# ── API key ──────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

# ── Design tokens ────────────────────────────────────────────────────────────
_P  = "#1B3A5C"    # TYASA primary
_A  = "#E05C2D"    # accent
_OK = "#22C55E"    # active green
_WA = "#F59E0B"    # at-risk amber
_ER = "#EF4444"    # inactive red
_BG = "#F8FAFC"
_CARD = "#FFFFFF"
_BD  = "#E2E8F0"
_T1  = "#0F172A"
_T2  = "#64748B"
_T3  = "#94A3B8"

_MES = ["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

# ── CSS (inject once) ────────────────────────────────────────────────────────
_CSS = """<style>
.ic-card{background:#FFFFFF;border-radius:14px;padding:18px 20px;
  border:1px solid #E2E8F0;box-shadow:0 1px 3px rgba(0,0,0,.05),0 4px 12px rgba(0,0,0,.04);}
.ic-label{font-size:10px;font-weight:700;color:#94A3B8;text-transform:uppercase;
  letter-spacing:.07em;margin-bottom:5px;}
.ic-num{font-size:26px;font-weight:800;color:#0F172A;letter-spacing:-.02em;line-height:1.1;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}
.ic-sub{font-size:11px;color:#94A3B8;margin-top:2px;}
.ic-badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:10.5px;font-weight:700;letter-spacing:.04em;}
.ic-sep{border:none;border-top:1px solid #F1F5F9;margin:10px 0;}
.ic-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;
  border-bottom:1px solid #F8FAFC;}
.ic-stat-lbl{font-size:11.5px;color:#64748B;}
.ic-stat-val{font-size:12px;font-weight:700;color:#0F172A;}
</style>"""


# ── Utilities ────────────────────────────────────────────────────────────────
def _fmt(v, dec=1) -> str:
    try:
        f = float(v)
        if abs(f) >= 1000:
            return f"{f:,.{dec}f}"
        return f"{f:.{dec}f}"
    except Exception:
        return "—"

def _arrow(v, suffix="%"):
    try:
        f = float(v)
        c = _OK if f >= 0 else _ER
        s = f"{'▲' if f>=0 else '▼'} {abs(f):.1f}{suffix}"
        return c, s
    except Exception:
        return _T3, "—"

def _abc_colors(clase):
    return {
        "A": ("#1D4ED8", "#EFF6FF"),
        "B": ("#059669", "#ECFDF5"),
        "C": ("#DC2626", "#FEF2F2"),
    }.get(clase, (_T3, _BG))


# ── Analytics ────────────────────────────────────────────────────────────────
def _calcular_abc(df_all: pd.DataFrame, cliente: str) -> str:
    if df_all.empty:
        return "—"
    df = df_all.sort_values("PESO_TON", ascending=False).copy()
    total = df["PESO_TON"].sum()
    if total == 0:
        return "C"
    df["_cum"] = df["PESO_TON"].cumsum() / total * 100
    row = df[df["CLIENTE"] == cliente]
    if row.empty:
        return "C"
    p = float(row.iloc[0]["_cum"])
    return "A" if p <= 80 else "B" if p <= 95 else "C"


def _salud(df_perfil_row) -> tuple:
    """Retorna (estado, dias, color)."""
    try:
        uc = pd.to_datetime(df_perfil_row.get("ULTIMA_COMPRA"), errors="coerce")
        if pd.isna(uc):
            return "sin datos", 999, _T3
        dias = (pd.Timestamp.today() - uc).days
        if dias <= 90:
            return "Activo", dias, _OK
        elif dias <= 180:
            return "En riesgo", dias, _WA
        else:
            return "Inactivo", dias, _ER
    except Exception:
        return "sin datos", 999, _T3


def _pred_proximo(df_trans: pd.DataFrame, ultima_compra) -> str:
    try:
        periodos = df_trans.groupby("PERIODO")["PESO_TON"].sum()
        periodos = periodos[periodos > 0].index.sort_values()
        if len(periodos) < 3:
            return "sin suficientes datos"
        gaps = [(periodos[i+1]-periodos[i]).days for i in range(len(periodos)-1)]
        avg  = sum(gaps) / len(gaps)
        pred = pd.to_datetime(ultima_compra) + pd.Timedelta(days=avg)
        diff = (pred - pd.Timestamp.today()).days
        label = f"~{abs(diff)}d {'atrasado' if diff < 0 else 'restantes'}"
        return f"{pred.strftime('%d %b %Y')}  ({label})"
    except Exception:
        return "—"


def _tendencia(df_mens: pd.DataFrame) -> str:
    if df_mens.empty or len(df_mens) < 6:
        return "insuficientes datos"
    s = df_mens.sort_values("PERIODO")["PESO_TON"].tail(6).values
    mid = len(s) // 2
    return "creciente ▲" if s[mid:].mean() > s[:mid].mean() * 1.05 else \
           "decreciente ▼" if s[mid:].mean() < s[:mid].mean() * 0.95 else "estable"


def _mix_change(df_trans: pd.DataFrame) -> pd.DataFrame:
    if df_trans.empty:
        return pd.DataFrame()
    fechas = df_trans["PERIODO"].dropna().sort_values().unique()
    if len(fechas) < 4:
        return pd.DataFrame()
    mid = fechas[len(fechas) // 2]
    ant = df_trans[df_trans["PERIODO"] <= mid].groupby("PRODUCTO_ORIGINAL")["PESO_TON"].sum()
    rec = df_trans[df_trans["PERIODO"] > mid].groupby("PRODUCTO_ORIGINAL")["PESO_TON"].sum()
    prods = set(ant.index) | set(rec.index)
    rows = []
    ta, tr = ant.sum() or 1, rec.sum() or 1
    for p in prods:
        sa = ant.get(p, 0) / ta * 100
        sr = rec.get(p, 0) / tr * 100
        rows.append({"producto": p, "ant": sa, "rec": sr, "delta": sr - sa})
    return pd.DataFrame(rows).sort_values("delta")


# ── HTML Builders ────────────────────────────────────────────────────────────
def _html_kpis(tons_total, n_emb, clase, antiguedad_str, dias, estado, color_salud) -> str:
    abc_c, abc_bg = _abc_colors(clase)
    estado_badge = (
        f'<span class="ic-badge" style="background:{color_salud}22;color:{color_salud};">'
        f'● {estado}</span>'
    )
    items = [
        ("Toneladas históricas", _fmt(tons_total) + " t", None),
        ("Embarques", str(n_emb), None),
        ("Clase ABC", f'<span class="ic-badge" style="background:{abc_bg};color:{abc_c};">{clase}</span>', None),
        ("Antigüedad", antiguedad_str, None),
        ("Días sin pedido", f'<span style="color:{color_salud};font-weight:800;">{dias}</span> · {estado_badge}', None),
    ]
    cols = ""
    for lbl, val, _ in items:
        cols += (
            f'<div style="flex:1;background:#FFF;border-radius:12px;padding:12px 16px;'
            f'border:1px solid #E2E8F0;box-shadow:0 1px 3px rgba(0,0,0,.04);">'
            f'<div class="ic-label">{lbl}</div>'
            f'<div style="font-size:18px;font-weight:800;color:#0F172A;line-height:1.2;">{val}</div>'
            f'</div>'
        )
    return f'<div style="display:flex;gap:10px;margin-bottom:4px;">{cols}</div>'


def _html_profile(df_row, clase, antiguedad_str, n_prods, estado, dias,
                  pred_str, color_salud, tons_avg_12m) -> str:
    abc_c, abc_bg = _abc_colors(clase)
    division = str(df_row.get("DIVISION", "—")) if df_row is not None else "—"
    pc = f"<strong>Próx. pedido:</strong><br><span style='color:{_P};font-size:12px;'>{pred_str}</span>"
    return f"""<div class="ic-card" style="height:100%;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
    <div style="width:10px;height:10px;border-radius:50%;background:{color_salud};flex-shrink:0;"></div>
    <span style="font-size:13px;font-weight:700;color:#0F172A;">Perfil del Cliente</span>
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
    <span class="ic-badge" style="background:{abc_bg};color:{abc_c};">CLASE {clase}</span>
    <span class="ic-badge" style="background:#F1F5F9;color:#475569;">{division}</span>
    <span class="ic-badge" style="background:{color_salud}22;color:{color_salud};">● {estado}</span>
  </div>
  <hr class="ic-sep">
  <div class="ic-row"><span class="ic-stat-lbl">Antigüedad</span><span class="ic-stat-val">{antiguedad_str}</span></div>
  <div class="ic-row"><span class="ic-stat-lbl">Días sin pedido</span>
    <span class="ic-stat-val" style="color:{color_salud};">{dias} días</span></div>
  <div class="ic-row"><span class="ic-stat-lbl">Productos activos</span><span class="ic-stat-val">{n_prods}</span></div>
  <div class="ic-row"><span class="ic-stat-lbl">Prom. 12m</span><span class="ic-stat-val">{_fmt(tons_avg_12m)} t/mes</span></div>
  <hr class="ic-sep">
  <div style="font-size:11px;color:{_T2};line-height:1.7;">{pc}</div>
</div>"""


def _html_yoy(df_mens: pd.DataFrame) -> str:
    if df_mens.empty:
        return '<div class="ic-card"><div class="ic-label">Año vs Año anterior</div><div style="color:#94A3B8;font-size:12px;">Sin datos</div></div>'
    hoy   = date.today()
    anio  = hoy.year
    ant   = anio - 1
    t_act = df_mens[df_mens["ANIO"] == anio]["PESO_TON"].sum()
    t_ant = df_mens[df_mens["ANIO"] == ant]["PESO_TON"].sum()
    var   = (t_act - t_ant) / t_ant * 100 if t_ant > 0 else 0
    vc, vs = _arrow(var)
    pct_act = min(100, t_act / max(t_act, t_ant) * 100) if max(t_act, t_ant) > 0 else 0
    pct_ant = min(100, t_ant / max(t_act, t_ant) * 100) if max(t_act, t_ant) > 0 else 0
    bar_act = f'<div style="height:6px;border-radius:4px;background:{_P};width:{pct_act:.0f}%;margin-top:4px;"></div>'
    bar_ant = f'<div style="height:6px;border-radius:4px;background:#CBD5E1;width:{pct_ant:.0f}%;margin-top:4px;"></div>'
    return f"""<div class="ic-card" style="height:100%;">
  <div class="ic-label">Año actual vs anterior</div>
  <div style="margin:10px 0;">
    <div style="font-size:11px;color:{_T2};margin-bottom:2px;">{anio}</div>
    <div style="font-size:20px;font-weight:800;color:{_T1};">{_fmt(t_act)} t</div>
    {bar_act}
  </div>
  <div style="margin:10px 0;">
    <div style="font-size:11px;color:{_T2};margin-bottom:2px;">{ant}</div>
    <div style="font-size:18px;font-weight:700;color:{_T3};">{_fmt(t_ant)} t</div>
    {bar_ant}
  </div>
  <hr class="ic-sep">
  <div style="font-size:22px;font-weight:800;color:{vc};">{vs}</div>
  <div style="font-size:10px;color:{_T3};margin-top:2px;">variación interanual</div>
</div>"""


def _html_mix_change(df_change: pd.DataFrame) -> str:
    if df_change.empty:
        return ""
    rows_html = ""
    for _, r in df_change.head(5).iterrows():
        d = float(r["delta"])
        bar_w = min(abs(d) * 4, 60)
        color = _OK if d > 0 else _ER
        bar = f'<div style="height:4px;width:{bar_w:.0f}px;background:{color};border-radius:2px;"></div>'
        rows_html += (
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;'
            f'border-bottom:1px solid #F8FAFC;">'
            f'<div style="flex:1;font-size:10.5px;color:{_T1};white-space:nowrap;overflow:hidden;'
            f'text-overflow:ellipsis;">{str(r["producto"])[:28]}</div>'
            f'<div style="width:64px;">{bar}</div>'
            f'<div style="font-size:10.5px;font-weight:700;color:{color};width:36px;text-align:right;">'
            f'{"+" if d>0 else ""}{d:.1f}%</div>'
            f'</div>'
        )
    return (
        f'<div style="background:#FFF;border-radius:12px;padding:12px 14px;'
        f'border:1px solid #E2E8F0;box-shadow:0 1px 3px rgba(0,0,0,.04);margin-top:10px;">'
        f'<div class="ic-label">Cambio en mix  (1ª mitad vs 2ª mitad)</div>'
        f'{rows_html}</div>'
    )


def _html_briefing_result(result: dict | None) -> str:
    if not result:
        return (
            f'<div style="color:{_T3};font-size:12px;padding:14px;text-align:center;'
            f'background:#FFF;border-radius:12px;border:1px dashed #E2E8F0;">'
            f'Haz clic en "Generar Briefing" para crear el brief de visita con IA</div>'
        )
    error = result.get("_error")
    briefing = result.get("briefing", "")
    if error and not briefing:
        return f'<div style="color:{_ER};padding:10px;font-size:12px;border-radius:8px;background:#FEF2F2;">{error}</div>'
    cached = ' <span style="font-size:9px;color:#94A3B8;">caché</span>' if result.get("_cached") else ""
    lines = [l.strip() for l in briefing.strip().split("\n") if l.strip()]
    bullets = ""
    for line in lines:
        bullets += (
            f'<div style="display:flex;gap:10px;align-items:flex-start;padding:7px 0;'
            f'border-bottom:1px solid #F8FAFC;">'
            f'<span style="font-size:16px;flex-shrink:0;">{line[:2]}</span>'
            f'<span style="font-size:13px;color:{_T1};line-height:1.6;">{line[2:].strip()}</span>'
            f'</div>'
        )
    return (
        f'<div style="background:#FFF;border-radius:14px;padding:20px 22px;'
        f'border-left:4px solid {_P};border:1px solid #E2E8F0;'
        f'box-shadow:0 1px 4px rgba(0,0,0,.06);">'
        f'<div style="font-size:10px;font-weight:700;color:{_T3};text-transform:uppercase;'
        f'letter-spacing:.07em;margin-bottom:14px;">BRIEFING DE VISITA · IA GEMINI{cached}</div>'
        f'{bullets}</div>'
    )


# ── Charts ───────────────────────────────────────────────────────────────────
def _chart_24m(df_mens: pd.DataFrame) -> go.Figure:
    df_s = df_mens.sort_values("PERIODO").tail(24).copy()
    df_s["trend"] = df_s["PESO_TON"].rolling(3, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_s["PERIODO"], y=df_s["PESO_TON"], name="Tons",
        marker_color="#DBEAFE", marker_line_color="#1B3A5C", marker_line_width=0.8,
        hovertemplate="%{x|%b %Y}: %{y:,.1f}t<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_s["PERIODO"], y=df_s["trend"], name="Media móvil 3m",
        mode="lines", line=dict(color=_A, width=2.5, dash="dot"),
        hovertemplate="%{x|%b %Y}: %{y:,.1f}t<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=_T3, size=10),
        xaxis=dict(gridcolor="#F1F5F9", showgrid=True, title=None, tickformat="%b %y"),
        yaxis=dict(gridcolor="#F1F5F9", showgrid=True, title="ton"),
        margin=dict(l=48, r=12, t=12, b=36), height=230, showlegend=True,
        legend=dict(orientation="h", y=-0.22, x=0, font_size=9),
        hovermode="x unified",
    )
    return fig


def _chart_yoy_bars(df_mens: pd.DataFrame) -> go.Figure:
    hoy  = date.today()
    anio = hoy.year
    ant  = anio - 1
    def _monthly(yr):
        d = df_mens[df_mens["ANIO"] == yr].groupby("MES")["PESO_TON"].sum().reindex(range(1,13), fill_value=0)
        return d.values
    vals_act = _monthly(anio)
    vals_ant = _monthly(ant)
    meses = [_MES[m] for m in range(1, 13)]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=meses, y=vals_ant, name=str(ant), marker_color="#E2E8F0",
                         hovertemplate="%{x}: %{y:,.1f}t<extra></extra>"))
    fig.add_trace(go.Bar(x=meses, y=vals_act, name=str(anio), marker_color=_P,
                         hovertemplate="%{x}: %{y:,.1f}t<extra></extra>"))
    fig.update_layout(
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=_T3, size=9),
        xaxis=dict(gridcolor="#F1F5F9", title=None),
        yaxis=dict(gridcolor="#F1F5F9", title="ton"),
        margin=dict(l=44, r=8, t=10, b=30), height=200, showlegend=True,
        legend=dict(orientation="h", y=-0.28, x=0, font_size=9),
    )
    return fig


def _chart_donut(df_mix: pd.DataFrame) -> go.Figure:
    if df_mix.empty:
        return go.Figure()
    top = df_mix.nlargest(6, "PESO_TON").copy()
    otros = df_mix["PESO_TON"].sum() - top["PESO_TON"].sum()
    if otros > 0:
        top = pd.concat([top, pd.DataFrame([{"PRODUCTO_ORIGINAL": "Otros", "PESO_TON": otros}])], ignore_index=True)
    palette = [_P, "#4A7BA7", "#7B9EC0", "#B8CFE3", _A, "#EFA07A", "#CBD5E1"]
    fig = go.Figure(go.Pie(
        labels=top["PRODUCTO_ORIGINAL"], values=top["PESO_TON"],
        hole=0.62, sort=True,
        textinfo="percent", textfont_size=9,
        marker=dict(colors=palette[:len(top)], line=dict(color="#FFF", width=2)),
        hovertemplate="%{label}: %{value:,.1f}t (%{percent})<extra></extra>",
    ))
    total_tons = df_mix["PESO_TON"].sum()
    fig.add_annotation(text=f"<b>{_fmt(total_tons)}</b><br><span style='font-size:9px'>ton</span>",
                       x=0.5, y=0.5, showarrow=False, font_size=14, font_color=_T1)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
        legend=dict(orientation="v", x=1.02, y=0.5, font_size=9),
        margin=dict(l=10, r=80, t=10, b=10), height=230,
    )
    return fig


def _chart_seasonality(df_trans: pd.DataFrame) -> go.Figure:
    if df_trans.empty:
        return go.Figure()
    n_anios = max(df_trans["ANIO"].nunique(), 1)
    monthly = df_trans.groupby("MES")["PESO_TON"].sum().reindex(range(1, 13), fill_value=0) / n_anios
    mx = monthly.max() or 1
    colors = [_P if v == mx else ("#7B9EC0" if v >= mx * 0.7 else "#CBD5E1") for v in monthly.values]
    fig = go.Figure(go.Bar(
        x=[_MES[m] for m in range(1, 13)],
        y=monthly.values,
        marker_color=colors,
        text=[f"{v:.0f}" for v in monthly.values],
        textposition="outside", textfont_size=9,
        hovertemplate="%{x}: %{y:,.1f}t prom.<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=_T3, size=10),
        xaxis=dict(gridcolor="#F1F5F9", title=None),
        yaxis=dict(gridcolor="#F1F5F9", title="ton prom.", showgrid=True),
        margin=dict(l=44, r=12, t=24, b=24), height=210, showlegend=False,
    )
    return fig


# ── Render principal ─────────────────────────────────────────────────────────
def render():
    # CSS global
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Título + selector ────────────────────────────────────────────────────
    col_h, col_sel = st.columns([2, 3])
    with col_h:
        st.markdown(
            f"<h2 style='color:{_P};margin:0;font-size:22px;'>Inteligencia de Clientes</h2>"
            f"<p style='color:{_T3};font-size:12px;margin:2px 0 0;'>Ficha 360° · Aceros Planos Negros</p>",
            unsafe_allow_html=True,
        )
    with col_sel:
        clientes = get_catalogo_clientes()
        if not clientes:
            st.warning("No hay clientes disponibles. Verifica la conexión a BigQuery.")
            return
        cliente = st.selectbox(
            "Cliente", clientes, key="ic_cliente",
            label_visibility="collapsed",
            placeholder="Buscar cliente…",
        )

    st.markdown("<div style='margin:6px 0 2px;'></div>", unsafe_allow_html=True)

    # ── Carga de datos ───────────────────────────────────────────────────────
    with st.spinner(f"Cargando datos de {cliente}…"):
        df_todos     = load_gold_demanda_cliente()
        df_cli_prod  = load_gold_cliente_producto()
        df_trans     = load_transacciones_cliente(cliente)

    # Perfil básico
    df_perf = df_todos[df_todos["CLIENTE"] == cliente]
    perf    = df_perf.iloc[0].to_dict() if not df_perf.empty else None

    # Serie mensual del cliente (de transacciones)
    if not df_trans.empty:
        df_mens = (df_trans.groupby(["PERIODO", "ANIO", "MES"])["PESO_TON"]
                   .sum().reset_index().sort_values("PERIODO"))
    else:
        df_mens = pd.DataFrame(columns=["PERIODO", "ANIO", "MES", "PESO_TON"])

    # Mix de productos
    df_mix_cliente = df_cli_prod[df_cli_prod["CLIENTE"] == cliente] if not df_cli_prod.empty else pd.DataFrame()
    if not df_mix_cliente.empty:
        df_mix = df_mix_cliente.rename(columns={"PRODUCTO_LIMPIO": "PRODUCTO_ORIGINAL"})
    elif not df_trans.empty:
        df_mix = df_trans.groupby("PRODUCTO_ORIGINAL")["PESO_TON"].sum().reset_index()
    else:
        df_mix = pd.DataFrame(columns=["PRODUCTO_ORIGINAL", "PESO_TON"])

    # Cálculos
    clase     = _calcular_abc(df_todos, cliente)
    estado, dias, color_salud = _salud(perf)

    try:
        pc = pd.to_datetime(perf.get("PRIMERA_COMPRA"), errors="coerce") if perf else None
        ant_yrs = (pd.Timestamp.today() - pc).days / 365 if pc and not pd.isna(pc) else 0
        antiguedad_str = f"{ant_yrs:.1f} años"
    except Exception:
        antiguedad_str = "—"

    try:
        uc = pd.to_datetime(perf.get("ULTIMA_COMPRA"), errors="coerce") if perf else None
    except Exception:
        uc = None

    pred_str  = _pred_proximo(df_trans, uc) if (uc is not None and not pd.isna(uc)) else "—"
    n_prods   = df_mix["PRODUCTO_ORIGINAL"].nunique() if not df_mix.empty else 0
    tons_total = float(perf.get("PESO_TON", 0)) if perf else 0
    n_emb      = int(perf.get("N_EMBARQUES", 0)) if perf else 0

    # Toneladas promedio mensual últimos 12 meses
    tons_avg_12m = 0.0
    if not df_mens.empty:
        ult12 = df_mens.sort_values("PERIODO").tail(12)["PESO_TON"]
        tons_avg_12m = float(ult12.mean()) if len(ult12) > 0 else 0.0

    # ── KPI chips ────────────────────────────────────────────────────────────
    st.html(_html_kpis(tons_total, n_emb, clase, antiguedad_str, dias, estado, color_salud))

    # ── Fila principal: perfil | serie 24m | YoY ─────────────────────────────
    c1, c2, c3 = st.columns([2.8, 4.8, 2.4])

    with c1:
        st.html(_html_profile(perf, clase, antiguedad_str, n_prods,
                               estado, dias, pred_str, color_salud, tons_avg_12m))

    with c2:
        st.markdown(
            f"<div style='font-size:11px;font-weight:700;color:{_T3};text-transform:uppercase;"
            f"letter-spacing:.07em;margin-bottom:4px;'>Comportamiento 24 meses</div>",
            unsafe_allow_html=True,
        )
        if not df_mens.empty:
            st.plotly_chart(_chart_24m(df_mens), width="stretch", key="ic_24m")
        else:
            st.info("Sin historial de compras registrado.")
        st.markdown(
            f"<div style='font-size:11px;font-weight:700;color:{_T3};text-transform:uppercase;"
            f"letter-spacing:.07em;margin:4px 0 2px;'>Año actual vs año anterior</div>",
            unsafe_allow_html=True,
        )
        if not df_mens.empty:
            st.plotly_chart(_chart_yoy_bars(df_mens), width="stretch", key="ic_yoy")

    with c3:
        st.html(_html_yoy(df_mens))

    # ── Fila inferior: mix | estacionalidad ──────────────────────────────────
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    c4, c5 = st.columns([4, 6])

    with c4:
        st.markdown(
            f"<div style='font-size:11px;font-weight:700;color:{_T3};text-transform:uppercase;"
            f"letter-spacing:.07em;margin-bottom:4px;'>Mix de productos</div>",
            unsafe_allow_html=True,
        )
        if not df_mix.empty:
            st.plotly_chart(_chart_donut(df_mix), width="stretch", key="ic_donut")
        df_change = _mix_change(df_trans)
        st.html(_html_mix_change(df_change))

    with c5:
        st.markdown(
            f"<div style='font-size:11px;font-weight:700;color:{_T3};text-transform:uppercase;"
            f"letter-spacing:.07em;margin-bottom:4px;'>Estacionalidad histórica  (prom. mensual)</div>",
            unsafe_allow_html=True,
        )
        if not df_trans.empty:
            st.plotly_chart(_chart_seasonality(df_trans), width="stretch", key="ic_season")
        else:
            st.info("Sin datos de estacionalidad.")

    # ── Briefing IA ──────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:11px;font-weight:700;color:{_T3};text-transform:uppercase;"
        f"letter-spacing:.07em;margin-bottom:6px;'>Briefing de Visita — IA</div>",
        unsafe_allow_html=True,
    )

    col_desc, col_btn, col_frz = st.columns([5, 1.5, 1])
    with col_desc:
        st.markdown(
            f"<p style='color:{_T2};font-size:12px;margin:6px 0;'>"
            f"Genera 4-5 bullets accionables para el vendedor combinando el perfil del cliente "
            f"con contexto de mercado TYASA. Gemini 2.5-flash · caché diario.</p>",
            unsafe_allow_html=True,
        )
    with col_btn:
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
        run_brief = st.button("Generar Briefing", key="ic_brief_run", width="stretch")
    with col_frz:
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
        frz_brief = st.checkbox("Regenerar", value=False, key="ic_brief_frz")

    skey = f"ic_brief_{cliente}"

    if run_brief and _GEMINI_KEY:
        # Preparar argumentos para la IA
        monthly_by_mes = (df_trans.groupby("MES")["PESO_TON"].sum()
                          .reindex(range(1,13), fill_value=0))
        mes_peak_n = int(monthly_by_mes.idxmax()) if not monthly_by_mes.empty else 0
        mes_low_n  = int(monthly_by_mes.idxmin()) if not monthly_by_mes.empty else 0
        mes_peak = _MES[mes_peak_n] if 1 <= mes_peak_n <= 12 else "—"
        mes_low  = _MES[mes_low_n]  if 1 <= mes_low_n  <= 12 else "—"
        mes_act  = _MES[date.today().month]

        # 3-month avg vs same 3 months last year
        hoy_m = date.today()
        try:
            ultimos3 = df_mens[df_mens["ANIO"] == hoy_m.year].tail(3)["PESO_TON"]
            avg_3m   = float(ultimos3.mean()) if len(ultimos3) > 0 else 0.0
            yoy_3m   = df_mens[(df_mens["ANIO"] == hoy_m.year - 1)].tail(3)["PESO_TON"]
            avg_3m_yoy = float(yoy_3m.mean()) if len(yoy_3m) > 0 else 0.0
        except Exception:
            avg_3m, avg_3m_yoy = 0.0, 0.0

        prods_lista = "\n".join(
            f"- {r['PRODUCTO_ORIGINAL']}: {_fmt(r['PESO_TON'])} t"
            for _, r in df_mix.sort_values("PESO_TON", ascending=False).head(5).iterrows()
        ) if not df_mix.empty else "(sin datos)"

        st.session_state[skey] = generar_briefing_cliente(
            cliente     = cliente,
            clase       = clase,
            division    = str(perf.get("DIVISION", "—")) if perf else "—",
            antiguedad  = antiguedad_str,
            estado      = estado,
            dias        = dias,
            pred_prox   = pred_str,
            n_prods     = n_prods,
            avg_3m      = avg_3m,
            avg_3m_yoy  = avg_3m_yoy,
            tendencia   = _tendencia(df_mens),
            lista_prods = prods_lista,
            mes_peak    = mes_peak,
            mes_low     = mes_low,
            mes_actual  = mes_act,
            api_key     = _GEMINI_KEY,
            force_refresh = frz_brief,
        )
    elif run_brief:
        st.session_state[skey] = {
            "briefing": "", "_cached": False,
            "_error": "Configura GEMINI_API_KEY en .streamlit/secrets.toml",
        }

    st.html(_html_briefing_result(st.session_state.get(skey)))
    st.caption(f"Aceros Planos Negros · Inteligencia de Clientes · {cliente}")


def main():
    render()


if __name__ == "__main__":
    main()
