"""
pages/mercado/09_quiebres_ferroaleaciones.py — Monitor de quiebres de ferroaleaciones

Una ferroaleación a la vez: precio normalizado (mercado_fastmarkets/loaders.py::
FERROALEACIONES), rango normal sombreado de cada régimen, quiebres detectados y
validados estadísticamente (mercado_noticias/analytics/rupturas.py) y su vínculo
con los eventos curados de GOLD_EVENTOS_HISTORICOS (scripts/seed_eventos_historicos.py).
Un clic en un quiebre de la gráfica abre su detalle; para quiebres recientes se
agrega contexto de las noticias clasificadas del sistema.
"""

import os
import re
import sys
import urllib.parse

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config import COLORS, COLOR_SEQUENCE

from mercado_fastmarkets.loaders import FERROALEACIONES, load_ferroaleaciones
from mercado_noticias.loaders import load_eventos_todos, load_noticias_en_rango
from mercado_noticias.analytics.rupturas import (
    bandas_normales, detectar_rupturas, normalizar_mensual, rupturas_a_dataframe, vincular_eventos,
)
from core.components.kpi_cards import render_kpi_row, seccion_titulo

# Las noticias clasificadas del sistema empiezan en nov 2024; antes no hay con qué cruzar.
INICIO_NOTICIAS = pd.Timestamp("2024-11-01")
DIAS_CONTEXTO = 45
CATEGORIAS_CONTEXTO = ("aranceles_comercio", "china_sobrecapacidad", "energia_electricidad",
                       "chatarra_scrap", "demanda_general", "carbon_coquizable")
TERMINO_GOOGLE = {
    "FerroManganeso": "ferromanganese", "SilicoManganeso": "silicomanganese",
    "FerroSilicio": "ferrosilicon", "FerroCromo": "ferrochrome", "FerroVanadio": "ferrovanadium",
    "FerroMolibdeno": "ferromolybdenum", "FerroTitanio": "ferrotitanium", "FerroNiobio": "ferroniobium",
    "Niquel": "LME nickel",
}
COLOR_SERIE = {nombre: COLOR_SEQUENCE[i] for i, (nombre, _) in enumerate(FERROALEACIONES.values())}
DESCRIPCION_SERIE = dict(FERROALEACIONES.values())
EVIDENCIAS = ["Fuerte", "Moderada", "Débil"]
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _mes(fecha) -> str:
    f = pd.Timestamp(fecha)
    return f"{_MESES[f.month - 1]} {f.year}"


def _url_en(texto: str | None) -> str | None:
    m = re.search(r"https?://\S+", texto or "")
    return m.group(0) if m else None


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


@st.cache_data(ttl=3600, show_spinner="Detectando quiebres...")
def _calcular(serie: str, desde_anio: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(bandas del régimen por mes, quiebres con evento vinculado) de una serie."""
    crudo = load_ferroaleaciones()
    crudo = crudo[crudo["serie"] == serie]
    if crudo.empty:
        return pd.DataFrame(), pd.DataFrame()
    precio = normalizar_mensual(crudo)[serie]
    desde = pd.Timestamp(f"{desde_anio}-01-01")
    precio = precio[precio.index >= desde].dropna()
    rupturas = rupturas_a_dataframe(detectar_rupturas(precio, serie))
    rupturas = vincular_eventos(rupturas, load_eventos_todos())
    return bandas_normales(precio), rupturas


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------
seccion_titulo("Quiebres en ferroaleaciones", "Cambios de régimen en el precio y qué los provocó")

nombres = [n for n, _ in FERROALEACIONES.values()]
c1, c2, c3 = st.columns([2, 1, 2])
with c1:
    serie = st.selectbox("Ferroaleación", nombres, key="qf_serie")
with c2:
    desde_anio = st.selectbox("Desde", [2000, 2005, 2010, 2015, 2020], index=0, key="qf_desde")
with c3:
    evid_sel = st.multiselect("Evidencia estadística", EVIDENCIAS, default=["Fuerte", "Moderada"], key="qf_evid")

bandas, rupturas = _calcular(serie, desde_anio)
if bandas.empty:
    st.warning("Sin precios de esta ferroaleación en Oracle.")
    st.stop()

vista = (rupturas[rupturas["evidencia"].isin(evid_sel)].sort_values("fecha", ascending=False).reset_index(drop=True)
         if not rupturas.empty else rupturas)
ultimo = bandas.iloc[-1]
tend_actual = rupturas.sort_values("fecha").iloc[-1]["tendencia_post_anual"] if not rupturas.empty else None
fuera_12m = int(bandas["fuera"].iloc[-12:].sum())

render_kpi_row([
    {"label": "Quiebres", "value": len(vista)},
    {"label": "Explicados por evento", "value": int(vista["evento_id"].notna().sum()) if not vista.empty else 0},
    {"label": "Tendencia actual", "value": f"{tend_actual:+.0f}% anual" if tend_actual is not None else "—",
     "help_text": "Ritmo al que se mueve el precio en el régimen actual"},
    {"label": "Meses fuera de lo normal", "value": f"{fuera_12m} de 12",
     "help_text": "Últimos 12 meses con el precio fuera de la banda sombreada"},
])

# ---------------------------------------------------------------------------
# Gráfica interactiva
# ---------------------------------------------------------------------------
color = COLOR_SERIE[serie]
fig = go.Figure()
fig.add_trace(go.Scatter(x=bandas.index, y=bandas["banda_sup"], mode="lines", line=dict(width=0),
                         showlegend=False, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=bandas.index, y=bandas["banda_inf"], mode="lines", line=dict(width=0),
                         fill="tonexty", fillcolor=_hex_rgba(color, 0.18), hoverinfo="skip", name="Rango normal"))
fig.add_trace(go.Scatter(
    x=bandas.index, y=bandas["precio"], name="Precio", mode="lines", line=dict(color=color, width=2),
    customdata=bandas[["banda_inf", "banda_sup"]].values,
    hovertemplate="%{x|%b %Y}: %{y:,.2f}<br>Normal: %{customdata[0]:,.2f} – %{customdata[1]:,.2f}<extra></extra>",
))
fuera = bandas[bandas["fuera"]]
fig.add_trace(go.Scatter(
    x=fuera.index, y=fuera["precio"], name="Fuera de lo normal", mode="markers",
    marker=dict(size=6, color=COLORS["warning"]), hovertemplate="Fuera de lo normal · %{x|%b %Y}<extra></extra>",
))
if not vista.empty:
    y_q = bandas["precio"].reindex(vista["fecha"]).values
    for _, q in vista.iterrows():
        fig.add_vline(x=q["fecha"], line=dict(color=COLORS["neutral"], dash="dot", width=1))
    fig.add_trace(go.Scatter(
        x=vista["fecha"], y=y_q, name="Quiebre", mode="markers",
        marker=dict(
            size=14, line=dict(width=1.5, color="white"),
            color=[COLORS["danger"] if d == "Sube" else COLORS["success"] for d in vista["direccion"]],
            symbol=["star" if e else "diamond" for e in vista["evento_id"].notna()],
        ),
        customdata=pd.DataFrame({
            "i": vista.index, "regimen": vista["regimen"], "evidencia": vista["evidencia"],
            "evento": vista["evento_nombre"].fillna("Sin evento verificado"),
        }).values,
        hovertemplate=("<b>Quiebre · %{x|%b %Y}</b><br>%{customdata[1]}<br>Evidencia: %{customdata[2]}"
                       "<br>%{customdata[3]}<br><i>Clic para ver detalle</i><extra></extra>"),
    ))
fig.update_layout(
    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
    margin=dict(l=40, r=20, t=50, b=20), height=520, hovermode="closest", clickmode="event+select",
    yaxis=dict(gridcolor="#E5E7EB", title=DESCRIPCION_SERIE[serie]),
    xaxis=dict(
        showgrid=False, rangeslider=dict(visible=True, thickness=0.06),
        rangeselector=dict(buttons=[
            dict(count=2, label="2A", step="year", stepmode="backward"),
            dict(count=5, label="5A", step="year", stepmode="backward"),
            dict(count=10, label="10A", step="year", stepmode="backward"),
            dict(step="all", label="Todo"),
        ]),
    ),
    legend=dict(orientation="h", y=1.08, x=1, xanchor="right"),
    title=dict(text=f"{serie}: precio, rango normal y quiebres", font=dict(size=14, color=COLORS["primary"]), x=0),
)
evento_grafica = st.plotly_chart(fig, width="stretch", key="qf_chart", on_select="rerun", selection_mode="points")
st.caption("Sombra: rango normal según el año anterior · Naranja: fuera de lo normal · "
           "Rombo/estrella: quiebre (estrella = explicado por un evento) · Clic en un quiebre para ver su detalle")

if vista.empty:
    st.info("No hay quiebres con la evidencia seleccionada.")
    st.stop()

# Clic en un quiebre -> se selecciona en el detalle (solo si cambió, para no pisar el selector)
puntos = [p for p in (evento_grafica.selection.points if evento_grafica else [])
          if p.get("customdata") and len(p["customdata"]) == 4]
if puntos:
    i_click = int(puntos[0]["customdata"][0])
    if st.session_state.get("_qf_ultimo_click") != (serie, i_click):
        st.session_state["_qf_ultimo_click"] = (serie, i_click)
        st.session_state["qf_quiebre"] = i_click
if st.session_state.get("qf_quiebre") not in vista.index:
    st.session_state["qf_quiebre"] = 0

# ---------------------------------------------------------------------------
# Detalle del quiebre
# ---------------------------------------------------------------------------
etiquetas = {i: f"{_mes(r.fecha)} · {r.regimen} · evidencia {r.evidencia.lower()}" + (" · ★" if r.evento_id else "")
             for i, r in vista.iterrows()}
i_sel = st.selectbox("Quiebre", list(etiquetas), format_func=etiquetas.get, key="qf_quiebre")
q = vista.loc[i_sel]

col_d, col_e = st.columns([1, 1])
with col_d:
    p_chow = f"{q['p_chow']:.4f}" if pd.notna(q["p_chow"]) else "no aplica (tramo corto)"
    cambio = f"{q['cambio_precio_6m']:+.0f}%" if pd.notna(q["cambio_precio_6m"]) else "—"
    st.html(
        f"<div style='font-size:13px;line-height:1.7;color:{COLORS['text']};background:{COLORS['surface']};"
        f"border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'>"
        f"<div style='font-weight:700;color:{COLORS['primary']};margin-bottom:4px;'>"
        f"{serie} · {_mes(q['fecha'])} · {q['regimen']}</div>"
        f"<div><b>Tendencia:</b> {q['tendencia_pre_anual']:+.0f}% → {q['tendencia_post_anual']:+.0f}% anual "
        f"<span style='color:{COLORS['text_light']};'>(p = {q['p_tendencia']:.4f})</span></div>"
        f"<div><b>Volatilidad:</b> {q['vol_pre_anual']:.0f}% → {q['vol_post_anual']:.0f}% anual "
        f"<span style='color:{COLORS['text_light']};'>(p = {q['p_volatilidad']:.4f})</span></div>"
        f"<div><b>Cambio estructural (Chow):</b> p = {p_chow}</div>"
        f"<div><b>Precio 6 meses después vs. 6 antes:</b> {cambio}</div>"
        f"<div><b>Evidencia:</b> {q['evidencia']} · régimen anterior {q['meses_pre']} meses, nuevo {q['meses_post']}</div>"
        f"</div>"
    )
with col_e:
    if q["evento_id"]:
        url = _url_en(q["evento_fuente"])
        fuente = (f"<a href='{url}' target='_blank' style='color:{COLORS['secondary']};'>Fuente</a>"
                  if url else (q["evento_fuente"] or ""))
        st.html(
            f"<div style='border-left:3px solid {COLORS['primary']};background:#F3F6FA;"
            f"padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;line-height:1.5;'>"
            f"<div style='font-weight:700;color:{COLORS['primary']};'>{q['evento_nombre']}</div>"
            f"<div style='margin-top:4px;'>{q['evento_descripcion']}</div>"
            f"<div style='margin-top:6px;font-size:11px;'>{fuente}</div></div>"
        )
    else:
        st.html(
            f"<div style='border-left:3px solid {COLORS['warning']};background:#FFF8EE;"
            f"padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;'>"
            f"Sin evento verificado en el catálogo para esta fecha.</div>"
        )
    termino = TERMINO_GOOGLE.get(serie, serie)
    antes = (q["fecha"] - pd.DateOffset(months=3)).strftime("%Y-%m-%d")
    despues = (q["fecha"] + pd.DateOffset(months=1)).strftime("%Y-%m-%d")
    gnews = "https://www.google.com/search?" + urllib.parse.urlencode(
        {"q": f"{termino} price after:{antes} before:{despues}", "tbm": "nws"})
    st.html(f"<div style='margin-top:8px;font-size:12px;'>"
            f"<a href='{gnews}' target='_blank' style='color:{COLORS['secondary']};'>"
            f"Buscar noticias de ese periodo</a></div>")

if q["fecha"] >= INICIO_NOTICIAS:
    seccion_titulo("Noticias del periodo", f"±{DIAS_CONTEXTO} días · contexto, no necesariamente la causa")
    noticias = load_noticias_en_rango(q["fecha"] - pd.Timedelta(days=DIAS_CONTEXTO),
                                      q["fecha"] + pd.Timedelta(days=DIAS_CONTEXTO), CATEGORIAS_CONTEXTO)
    if noticias.empty:
        st.info("Sin noticias clasificadas en ese periodo.")
    else:
        st.dataframe(
            noticias.head(12).assign(Fecha=lambda d: d["fecha_pub"].dt.strftime("%Y-%m-%d"))[
                ["Fecha", "titulo", "variable_principal", "fuente", "url"]],
            hide_index=True, width="stretch",
            column_config={
                "titulo": "Noticia", "variable_principal": "Tema", "fuente": "Fuente",
                "url": st.column_config.LinkColumn("Liga", display_text="Abrir"),
            },
        )

# ---------------------------------------------------------------------------
# Todos los quiebres de la serie
# ---------------------------------------------------------------------------
seccion_titulo(f"Quiebres de {serie}", f"Desde {desde_anio}")
tabla = vista.assign(
    Fecha=lambda d: d["fecha"].map(_mes),
    Cambio=lambda d: d["cambio_precio_6m"].map(lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"),
    Evento=lambda d: d["evento_nombre"].fillna("—"),
)[["Fecha", "regimen", "volatilidad", "Cambio", "evidencia", "Evento"]]
tabla.columns = ["Fecha", "Tendencia", "Volatilidad", "Precio 6m después vs. 6m antes", "Evidencia", "Evento"]
st.dataframe(tabla, hide_index=True, width="stretch")

st.caption("Datos: Fastmarkets (AMM) y LME · Eventos: catálogo curado con fuente")
