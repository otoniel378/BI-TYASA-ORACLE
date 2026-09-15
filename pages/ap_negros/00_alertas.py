"""
pages/ap_negros/00_alertas.py — Centro de Alertas y Pulso del Negocio.
Aceros Planos Negros — detección automática de anomalías + contexto externo.
"""

import os, sys, hashlib
from datetime import date, datetime, timedelta

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import COLORS
from aceros_planos.negros.loaders import (
    load_gold_demanda_cliente,
    load_gold_demanda_mensual_total,
    load_serie_mensual_cliente,
    load_ventas_limpias,
)
from core.components.filters import sidebar_header
from core.components.kpi_cards import seccion_titulo

# ── Gemini key ────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

# ── Design tokens ─────────────────────────────────────────────────────────────
_P   = "#1B3A5C"
_OK  = "#16A34A"
_WA  = "#D97706"
_ER  = "#DC2626"
_T1  = "#0F172A"
_T2  = "#64748B"
_T3  = "#94A3B8"
_BD  = "#E2E8F0"
_BG  = "#F8FAFC"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.html("""<style>
.al-card{background:#fff;border-radius:12px;padding:16px 18px;
  border:1px solid #E2E8F0;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:8px;}
.al-label{font-size:10px;font-weight:700;color:#94A3B8;text-transform:uppercase;
  letter-spacing:.07em;margin-bottom:4px;}
.al-val{font-size:22px;font-weight:800;color:#0F172A;line-height:1.1;}
.al-sub{font-size:11px;color:#94A3B8;margin-top:2px;}
.al-badge{display:inline-block;padding:2px 9px;border-radius:20px;
  font-size:10.5px;font-weight:700;letter-spacing:.04em;}
.al-anom{background:#fff;border-radius:10px;padding:12px 14px;
  border-left:4px solid #94A3B8;border:1px solid #E2E8F0;margin-bottom:6px;}
.al-sep{border:none;border-top:1px solid #F1F5F9;margin:8px 0;}
</style>""")

# ── Sidebar ───────────────────────────────────────────────────────────────────
sidebar_header("Centro de Alertas")

# ── Título ────────────────────────────────────────────────────────────────────
st.html(f"""
<div style="margin-bottom:6px;">
  <h2 style="color:{_P};margin:0;font-size:1.5rem;">Centro de Alertas</h2>
  <p style="color:{_T2};margin:0;font-size:0.85rem;">
    Aceros Planos Negros — Pulso del negocio en tiempo real
  </p>
</div>
""")
st.divider()

# ── Carga de datos ────────────────────────────────────────────────────────────
with st.spinner("Cargando datos..."):
    df_mensual  = load_gold_demanda_mensual_total()
    df_cliente  = load_gold_demanda_cliente()
    df_cli_ts   = load_serie_mensual_cliente()

# Carga de contexto externo — graceful si falla
_ctx_ok = False
df_vars_ext  = pd.DataFrame()
df_inegi_ext = pd.DataFrame()
df_quiebres  = pd.DataFrame()
try:
    from aceros_planos.negros.loaders_contexto import (
        load_vars_mercado_planos,
        load_alertas_inegi_planos,
        load_quiebres_relevantes_planos,
    )
    df_vars_ext  = load_vars_mercado_planos(dias=90)
    df_inegi_ext = load_alertas_inegi_planos()
    df_quiebres  = load_quiebres_relevantes_planos()
    _ctx_ok = True
except Exception as _e:
    print(f"[00_alertas] contexto externo no disponible: {_e}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt(v, dec=1) -> str:
    try:
        f = float(v)
        return f"{f:,.{dec}f}" if abs(f) >= 100 else f"{f:.{dec}f}"
    except Exception:
        return "—"

def _hoy_mes_anio():
    hoy = date.today()
    return hoy.year, hoy.month

def _sparkline_svg(vals: list, color: str = "#1B3A5C", h: int = 28, w: int = 60) -> str:
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

def _semaforo_color(val, umbral_ok, umbral_warn, mayor_es_mejor=True) -> str:
    try:
        v = float(val)
        if mayor_es_mejor:
            return _OK if v >= umbral_ok else _WA if v >= umbral_warn else _ER
        else:
            return _OK if v <= umbral_ok else _WA if v <= umbral_warn else _ER
    except Exception:
        return _T3

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — TERMÓMETRO DEL MES
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Termómetro del Mes", "Avance actual vs histórico")

hoy = date.today()
anio_act, mes_act = hoy.year, hoy.month
dias_habiles_mes  = 22   # aproximación estándar

if df_mensual.empty:
    st.info("Sin datos de demanda mensual disponibles.")
else:
    # Mes actual (datos parciales desde silver si existen)
    df_mes_act = df_mensual[
        (df_mensual["ANIO"] == anio_act) & (df_mensual["MES"] == mes_act)
    ]
    ton_act = float(df_mes_act["PESO_TON"].sum()) if not df_mes_act.empty else 0.0

    # Mismo mes en años anteriores (promedio últimos 3 años)
    df_hist_mes = df_mensual[
        (df_mensual["MES"] == mes_act) & (df_mensual["ANIO"] < anio_act)
    ].tail(3 * 1)   # 1 fila por año
    prom_hist = float(df_hist_mes["PESO_TON"].mean()) if not df_hist_mes.empty else 0.0

    # Proyección de cierre: ratio de días hábiles transcurridos
    dia_hoy = hoy.day
    dias_est_transcurridos = min(dia_hoy * 22 / 30, 22)
    pct_mes = dias_est_transcurridos / dias_habiles_mes
    ton_proy = (ton_act / pct_mes) if pct_mes > 0.05 else ton_act
    pct_vs_hist = ((ton_proy - prom_hist) / prom_hist * 100) if prom_hist > 0 else 0.0
    col_proy = _OK if pct_vs_hist >= -5 else _WA if pct_vs_hist >= -15 else _ER

    col1, col2, col3, col4 = st.columns(4)
    MESES = ["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

    with col1:
        st.html(f"""<div class="al-card">
          <div class="al-label">Mes actual</div>
          <div class="al-val">{MESES[mes_act]} {anio_act}</div>
          <div class="al-sub">Día {dia_hoy} de ~{dias_habiles_mes} hábiles</div>
        </div>""")
    with col2:
        st.html(f"""<div class="al-card">
          <div class="al-label">Toneladas del mes</div>
          <div class="al-val">{_fmt(ton_act)} ton</div>
          <div class="al-sub">{pct_mes*100:.0f}% del mes transcurrido</div>
        </div>""")
    with col3:
        st.html(f"""<div class="al-card">
          <div class="al-label">Proyección de cierre</div>
          <div class="al-val" style="color:{col_proy};">{_fmt(ton_proy)} ton</div>
          <div class="al-sub">Mismo mes últ. 3 años: {_fmt(prom_hist)} ton</div>
        </div>""")
    with col4:
        icono = "▲" if pct_vs_hist >= 0 else "▼"
        st.html(f"""<div class="al-card">
          <div class="al-label">vs Histórico mismo mes</div>
          <div class="al-val" style="color:{col_proy};">{icono} {abs(pct_vs_hist):.1f}%</div>
          <div class="al-sub">Prom. 3 años: {_fmt(prom_hist)} ton</div>
        </div>""")

    # Barra de progreso visual
    pct_bar = min(100, pct_mes * 100)
    pct_hist_bar = min(100, ton_act / max(prom_hist, 1) * 100)
    st.html(f"""
    <div style="background:#F1F5F9;border-radius:8px;padding:10px 14px;margin:6px 0 14px;">
      <div style="display:flex;justify-content:space-between;font-size:11px;color:{_T2};margin-bottom:4px;">
        <span>Avance del mes</span><span>{pct_bar:.0f}%</span>
      </div>
      <div style="background:#E2E8F0;border-radius:4px;height:8px;">
        <div style="width:{pct_bar:.0f}%;background:{_P};height:8px;border-radius:4px;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:11px;color:{_T2};margin:6px 0 2px;">
        <span>Avance vs histórico</span><span>{pct_hist_bar:.0f}%</span>
      </div>
      <div style="background:#E2E8F0;border-radius:4px;height:8px;">
        <div style="width:{pct_hist_bar:.0f}%;background:{col_proy};height:8px;border-radius:4px;"></div>
      </div>
    </div>""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — SEMÁFORO DEL ÁREA
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Semáforo del Área", "4 KPIs con indicador verde / amarillo / rojo")

if df_mensual.empty:
    st.info("Sin datos para calcular semáforo.")
else:
    hoy_dt = pd.Timestamp.today()

    # KPI 1: Velocidad de ventas (este mes vs promedio mismo mes años anteriores)
    vel_act   = ton_act
    vel_hist  = prom_hist
    vel_pct   = (vel_act / vel_hist * 100) if vel_hist > 0 else 100
    col_vel   = _OK if vel_pct >= 90 else _WA if vel_pct >= 70 else _ER

    # KPI 2: Clientes activos este mes vs histórico
    cli_act_count = 0
    cli_hist_avg  = 0
    if not df_mensual.empty and "N_CLIENTES" in df_mensual.columns:
        row_m = df_mensual[(df_mensual["ANIO"] == anio_act) & (df_mensual["MES"] == mes_act)]
        cli_act_count = int(row_m["N_CLIENTES"].sum()) if not row_m.empty else 0
        hist_rows = df_mensual[(df_mensual["MES"] == mes_act) & (df_mensual["ANIO"] < anio_act)]
        cli_hist_avg = float(hist_rows["N_CLIENTES"].mean()) if not hist_rows.empty else cli_act_count
    cli_pct   = (cli_act_count / cli_hist_avg * 100) if cli_hist_avg > 0 else 100
    col_cli   = _OK if cli_pct >= 85 else _WA if cli_pct >= 65 else _ER

    # KPI 3: Concentración top 3 clientes este mes
    conc_pct = 0.0
    if not df_cli_ts.empty:
        ts_mes = df_cli_ts[
            (pd.to_datetime(df_cli_ts["PERIODO"], errors="coerce").dt.year == anio_act) &
            (pd.to_datetime(df_cli_ts["PERIODO"], errors="coerce").dt.month == mes_act)
        ]
        if not ts_mes.empty:
            top3 = ts_mes.nlargest(3, "PESO_TON")["PESO_TON"].sum()
            total_m = ts_mes["PESO_TON"].sum()
            conc_pct = top3 / total_m * 100 if total_m > 0 else 0
    col_conc = _OK if conc_pct <= 50 else _WA if conc_pct <= 70 else _ER

    # KPI 4: Variación MoM
    mes_ant = mes_act - 1 if mes_act > 1 else 12
    anio_ant_mom = anio_act if mes_act > 1 else anio_act - 1
    row_ant = df_mensual[(df_mensual["ANIO"] == anio_ant_mom) & (df_mensual["MES"] == mes_ant)]
    ton_ant = float(row_ant["PESO_TON"].sum()) if not row_ant.empty else 0.0
    mom_pct = ((ton_act - ton_ant) / ton_ant * 100) if ton_ant > 0 else 0.0
    col_mom = _OK if mom_pct >= 0 else _WA if mom_pct >= -10 else _ER

    c1, c2, c3, c4 = st.columns(4)
    for col_st, lbl, val_str, sub, col in [
        (c1, "Velocidad de Ventas", f"{vel_pct:.0f}%",    f"{_fmt(vel_act)} ton vs hist. {_fmt(vel_hist)} ton", col_vel),
        (c2, "Clientes Activos",    f"{cli_act_count}",   f"{cli_pct:.0f}% del histórico ({cli_hist_avg:.0f} prom.)", col_cli),
        (c3, "Conc. Top 3",         f"{conc_pct:.0f}%",   "del volumen en solo 3 clientes", col_conc),
        (c4, "Variación MoM",       f"{mom_pct:+.1f}%",   f"vs mes anterior ({_fmt(ton_ant)} ton)", col_mom),
    ]:
        with col_st:
            st.html(f"""<div class="al-card" style="border-left:4px solid {col};">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{col};"></span>
                <span class="al-label" style="margin-bottom:0;">{lbl}</span>
              </div>
              <div class="al-val" style="color:{col};">{val_str}</div>
              <div class="al-sub">{sub}</div>
            </div>""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — CONTEXTO EXTERNO RÁPIDO
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Contexto Externo Rápido", "Variables clave de mercado e INEGI")

if not _ctx_ok:
    st.info("Contexto externo no disponible. Verifica conexión a BigQuery.")
else:
    # 4 mini-cards: ETF_Acero, USD_MXN, IMAI_Manufactureras, VIX
    from mercado.inegi.loaders import INDICADORES_LABEL

    def _last_mkt(nombre: str):
        if df_vars_ext.empty or "nombre" not in df_vars_ext.columns:
            return None, None
        sub = df_vars_ext[df_vars_ext["nombre"] == nombre].sort_values("fecha")
        if sub.empty:
            return None, None
        vals = pd.to_numeric(sub["valor"], errors="coerce").dropna()
        if vals.empty:
            return None, None
        ult  = float(vals.iloc[-1])
        d7   = (ult - float(vals.iloc[-8])) / abs(float(vals.iloc[-8])) * 100 if len(vals) >= 8 and float(vals.iloc[-8]) != 0 else 0
        return ult, d7

    def _last_inegi(clave: str):
        if df_inegi_ext.empty or "Clave" not in df_inegi_ext.columns:
            return None, "Normal"
        row = df_inegi_ext[df_inegi_ext["Clave"] == clave]
        if row.empty:
            return None, "Normal"
        v = row.iloc[0].get("ult_valor")
        a = row.iloc[0].get("alerta", "Normal")
        return v, a

    cards_data = []
    for nombre, label, fmt in [
        ("ETF_Acero_Global", "ETF Acero Global", ".2f"),
        ("USD_MXN",          "USD / MXN",        ".4f"),
    ]:
        val, d7 = _last_mkt(nombre)
        if val is None:
            cards_data.append((label, "N/D", "—", _T3, ""))
            continue
        icono = "▲" if (d7 or 0) >= 0 else "▼"
        col_d = _OK if (d7 or 0) >= 0 else _ER
        spk_data = df_vars_ext[df_vars_ext["nombre"] == nombre].sort_values("fecha")
        spk_vals = pd.to_numeric(spk_data["valor"], errors="coerce").dropna().tail(30).tolist()
        spk = _sparkline_svg(spk_vals)
        cards_data.append((label, f"{val:{fmt}}", f"{icono} {abs(d7):.1f}% (7d)", col_d, spk))

    for clave, label in [("736418", "IMAI Manufactureras"), ("737149", "IGAE Sec. Var. Anual")]:
        val, alerta = _last_inegi(clave)
        if val is None:
            cards_data.append((label, "N/D", "—", _T3, ""))
            continue
        col_a = _OK if alerta == "Normal" else _WA if alerta == "Moderado" else _ER
        cards_data.append((label, f"{float(val):.1f}", alerta, col_a, ""))

    cols_ext = st.columns(4)
    for i, (lbl, val_s, sub_s, col, spk) in enumerate(cards_data):
        with cols_ext[i]:
            spk_html = f'<div style="margin-top:6px;">{spk}</div>' if spk else ""
            st.html(f"""<div class="al-card">
              <div class="al-label">{lbl}</div>
              <div class="al-val">{val_s}</div>
              <div class="al-sub" style="color:{col};">{sub_s}</div>
              {spk_html}
            </div>""")

    # Badge de quiebres activos
    if not df_quiebres.empty:
        n_q = len(df_quiebres)
        vars_q = ", ".join(df_quiebres["variable"].head(3).tolist()) if "variable" in df_quiebres.columns else ""
        st.html(f"""
        <div style="background:#FEF3C7;border:1px solid #D97706;border-radius:8px;
             padding:8px 14px;display:flex;align-items:center;gap:10px;margin-top:4px;">
          <span style="font-size:12px;color:#92400E;">
            <strong>{n_q} quiebre(s) estructural(es) activo(s)</strong> en variables de mercado:
            {vars_q}{' …' if n_q > 3 else ''}
          </span>
        </div>""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — ANOMALÍAS DETECTADAS
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Anomalías Detectadas", "Señales automáticas desde los datos")

anomalias: list[dict] = []
hoy_ts = pd.Timestamp.today()

# A1: Clientes en fuga (> 60 días sin comprar)
if not df_cliente.empty and "ULTIMA_COMPRA" in df_cliente.columns and "PESO_TON" in df_cliente.columns:
    df_c = df_cliente.copy()
    df_c["ULTIMA_COMPRA"] = pd.to_datetime(df_c["ULTIMA_COMPRA"], errors="coerce")
    df_c["dias_sin_compra"] = (hoy_ts - df_c["ULTIMA_COMPRA"]).dt.days
    en_fuga = df_c[df_c["dias_sin_compra"] > 60].sort_values("PESO_TON", ascending=False)
    for _, row in en_fuga.head(5).iterrows():
        dias = int(row["dias_sin_compra"])
        col  = _ER if dias > 90 else _WA
        anomalias.append({
            "tipo": "Cliente en fuga",
            "desc": f"{row.get('CLIENTE','?')} — {dias} días sin comprar",
            "accion": "Contactar equipo de ventas para reactivación urgente",
            "color": col,
        })

# A2: Productos en caída > 25% MoM
if not df_mensual.empty and "PRODUCTO_LIMPIO" not in df_mensual.columns:
    # df_mensual_total no tiene columna de producto — usar df_mensual_gran si aplica
    pass

# A2 alternativo: clientes con volumen inusual (> 2x promedio histórico este mes)
if not df_cli_ts.empty:
    ts = df_cli_ts.copy()
    ts["PERIODO"] = pd.to_datetime(ts["PERIODO"], errors="coerce")
    ts = ts.dropna(subset=["PERIODO"])
    # promedio histórico por cliente
    ts_hist = ts[(ts["PERIODO"].dt.year < anio_act) | (ts["PERIODO"].dt.month != mes_act)]
    ts_mes_act = ts[(ts["PERIODO"].dt.year == anio_act) & (ts["PERIODO"].dt.month == mes_act)]
    if not ts_mes_act.empty and not ts_hist.empty:
        avg_hist = ts_hist.groupby("CLIENTE")["PESO_TON"].mean().reset_index().rename(columns={"PESO_TON": "avg_hist"})
        merged = ts_mes_act.merge(avg_hist, on="CLIENTE", how="left")
        inusuales = merged[(merged["PESO_TON"] > merged["avg_hist"] * 2) & (merged["avg_hist"] > 0)]
        for _, row in inusuales.head(3).iterrows():
            anomalias.append({
                "tipo": "Volumen inusual",
                "desc": f"{row.get('CLIENTE','?')} — {_fmt(row['PESO_TON'])} ton ({row['PESO_TON']/row['avg_hist']:.1f}x su promedio)",
                "accion": "Confirmar pedidos y disponibilidad de material; posible oportunidad de contrato",
                "color": _OK,
            })

# A3: Nuevos clientes (última 30 días)
if not df_cliente.empty and "PRIMERA_COMPRA" in df_cliente.columns:
    df_nc = df_cliente.copy()
    df_nc["PRIMERA_COMPRA"] = pd.to_datetime(df_nc["PRIMERA_COMPRA"], errors="coerce")
    nuevos = df_nc[df_nc["PRIMERA_COMPRA"] >= (hoy_ts - timedelta(days=30))]
    if not nuevos.empty:
        lista_n = ", ".join(nuevos["CLIENTE"].head(3).tolist())
        anomalias.append({
            "tipo": "Nuevos clientes",
            "desc": f"{len(nuevos)} cliente(s) nuevo(s) en últimos 30 días: {lista_n}",
            "accion": "Hacer seguimiento de segunda compra; incluir en campaña de fidelización",
            "color": _OK,
        })

if not anomalias:
    st.success("Sin anomalías críticas detectadas en este período.")
else:
    n_rojas  = sum(1 for a in anomalias if a["color"] == _ER)
    n_amaril = sum(1 for a in anomalias if a["color"] == _WA)
    st.html(f"""
    <div style="display:flex;gap:10px;margin-bottom:10px;">
      <span class="al-badge" style="background:#FEE2E2;color:#991B1B;">{n_rojas} crítica(s)</span>
      <span class="al-badge" style="background:#FEF3C7;color:#92400E;">{n_amaril} en seguimiento</span>
      <span class="al-badge" style="background:#DCFCE7;color:#166534;">{len(anomalias)-n_rojas-n_amaril} positiva(s)</span>
    </div>""")

    for a in anomalias:
        st.html(f"""<div class="al-anom" style="border-left-color:{a['color']};">
          <div style="display:flex;align-items:flex-start;gap:8px;">
            <span style="display:inline-block;width:8px;height:8px;margin-top:6px;border-radius:50%;background:{a['color']};flex-shrink:0;"></span>
            <div style="flex:1;">
              <div style="font-size:11px;font-weight:700;color:{_T2};text-transform:uppercase;
                   letter-spacing:.04em;">{a['tipo']}</div>
              <div style="font-size:13px;font-weight:600;color:{_T1};margin:2px 0;">{a['desc']}</div>
              <div style="font-size:11.5px;color:{_T2};">▶ {a['accion']}</div>
            </div>
          </div>
        </div>""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — RESUMEN IA
# ══════════════════════════════════════════════════════════════════════════════
seccion_titulo("Resumen IA del Estado", "Análisis ejecutivo generado por Gemini")

_IA_KEY = f"alertas_resumen_ia_{date.today().isoformat()}"

col_btn, col_info = st.columns([1, 3])
with col_btn:
    run_ia = st.button("Generar resumen IA", key="btn_alertas_ia",
                       disabled=not bool(_GEMINI_KEY))
with col_info:
    if not _GEMINI_KEY:
        st.caption("Configura GEMINI_API_KEY en secrets.toml para habilitar el análisis IA.")

if run_ia and _GEMINI_KEY:
    anom_txt = "\n".join([f"- {a['tipo']}: {a['desc']}" for a in anomalias]) or "- Sin anomalías detectadas"
    ctx_txt  = ""
    if _ctx_ok and not df_inegi_ext.empty:
        alertas_activas = df_inegi_ext[df_inegi_ext.get("alerta", pd.Series(dtype=str)).isin(["Critico","Alto"])] if "alerta" in df_inegi_ext.columns else pd.DataFrame()
        if not alertas_activas.empty:
            ctx_txt = "INEGI: " + ", ".join(alertas_activas.get("nombre", alertas_activas.get("Clave", pd.Series())).head(3).tolist())

    prompt = f"""Eres analista comercial senior de TYASA (acería mexicana de acero plano).
Resume el estado actual del negocio en 3 bullets ejecutivos y accionables.
Máximo 20 palabras por bullet. No uses emojis. Sin introducción.

Estado del mes:
- Toneladas actuales: {_fmt(ton_act)} ton
- Proyección de cierre: {_fmt(ton_proy)} ton ({pct_vs_hist:+.1f}% vs histórico)
- Clientes activos: {cli_act_count}
- Concentración top 3: {conc_pct:.0f}%
- Variación MoM: {mom_pct:+.1f}%

Anomalías detectadas:
{anom_txt}

Contexto externo: {ctx_txt or 'Sin alertas INEGI críticas.'}"""

    from mercado_noticias.analytics.ai_analysis import _call_gemini_text
    st.session_state[_IA_KEY] = _call_gemini_text(prompt, _GEMINI_KEY)


def _render_ia(txt: str | None) -> str:
    if not txt:
        return ""
    bullets = [l.strip() for l in txt.strip().split("\n") if l.strip()]
    items = "".join(f"<li style='margin-bottom:8px;font-size:13px;color:{_T1};'>{b}</li>" for b in bullets)
    return f"""<div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;
         padding:16px 20px;margin-top:8px;">
      <div style="font-size:10px;font-weight:700;color:#0369A1;text-transform:uppercase;
           letter-spacing:.06em;margin-bottom:10px;">Análisis IA — {date.today().strftime('%d %b %Y')}</div>
      <ul style="margin:0;padding-left:18px;">{items}</ul>
    </div>"""

st.html(_render_ia(st.session_state.get(_IA_KEY)))
