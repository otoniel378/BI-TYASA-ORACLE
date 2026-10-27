"""
pages/mercado/09_quiebres_ferroaleaciones.py — Monitor de quiebres de ferroaleaciones

Normaliza las series Fastmarkets de ferroaleaciones (mercado_fastmarkets/loaders.py::
FERROALEACIONES), detecta todos sus quiebres estructurales y valida cada uno
estadísticamente (mercado_noticias/analytics/rupturas.py), y los vincula con los
eventos curados de GOLD_EVENTOS_HISTORICOS (scripts/seed_eventos_historicos.py)
para explicar qué los provocó. Para quiebres recientes agrega contexto de las
noticias clasificadas del sistema.
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
    detectar_rupturas, indexar, normalizar_mensual, rupturas_a_dataframe, vincular_eventos,
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


@st.cache_data(ttl=3600, show_spinner="Detectando quiebres...")
def _calcular(desde_anio: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    crudo = load_ferroaleaciones()
    if crudo.empty:
        return pd.DataFrame(), pd.DataFrame()
    ancho = normalizar_mensual(crudo)
    desde = pd.Timestamp(f"{desde_anio}-01-01")
    todas = []
    for serie in ancho.columns:
        todas += detectar_rupturas(ancho[serie], serie, desde=desde)
    rupturas = vincular_eventos(rupturas_a_dataframe(todas), load_eventos_todos())
    return ancho[ancho.index >= desde], rupturas


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------
seccion_titulo("Quiebres en ferroaleaciones", "Cambios de régimen en el precio y qué los provocó")

c1, c2, c3 = st.columns([3, 1, 2])
with c1:
    series_sel = st.multiselect(
        "Ferroaleaciones", [n for n, _ in FERROALEACIONES.values()],
        default=[n for n, _ in FERROALEACIONES.values()], key="qf_series",
    )
with c2:
    desde_anio = st.selectbox("Desde", [2000, 2005, 2010, 2015, 2020], index=0, key="qf_desde")
with c3:
    evid_sel = st.multiselect("Evidencia estadística", EVIDENCIAS, default=["Fuerte", "Moderada"], key="qf_evid")

precios, rupturas = _calcular(desde_anio)
if precios.empty:
    st.warning("Sin precios de ferroaleaciones en Oracle (BRONZE_FASTMARKETS_PRECIOS).")
    st.stop()

vista = rupturas[rupturas["serie"].isin(series_sel) & rupturas["evidencia"].isin(evid_sel)] if not rupturas.empty else rupturas
con_evento = vista["evento_id"].notna() if not vista.empty else pd.Series(dtype=bool)

render_kpi_row([
    {"label": "Quiebres", "value": len(vista), "help_text": "Cambios de régimen detectados con los filtros actuales"},
    {"label": "Evidencia fuerte", "value": int((vista["evidencia"] == "Fuerte").sum()) if not vista.empty else 0,
     "help_text": "El cambio de tendencia o volatilidad tiene p < 0.01"},
    {"label": "Explicados por evento", "value": int(con_evento.sum())},
    {"label": "Sin explicar", "value": int((~con_evento).sum()) if not vista.empty else 0,
     "help_text": "No hay evento verificado en el catálogo para esa fecha y ferroaleación"},
])

tab_precios, tab_detalle, tab_metodo = st.tabs(["Precios y quiebres", "Detalle por quiebre", "Método"])

# ---------------------------------------------------------------------------
# Precios y quiebres
# ---------------------------------------------------------------------------
with tab_precios:
    idx = indexar(precios[[s for s in series_sel if s in precios.columns]], pd.Timestamp(f"{desde_anio}-01-01"))
    fig = go.Figure()
    for serie in idx.columns:
        s = idx[serie].dropna()
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=serie, mode="lines",
            line=dict(color=COLOR_SERIE[serie], width=1.8),
            hovertemplate=f"{serie} · %{{x|%b %Y}}: %{{y:,.0f}}<extra></extra>",
        ))
        q = vista[vista["serie"] == serie] if not vista.empty else vista
        if q.empty:
            continue
        y = s.reindex(q["fecha"]).values
        fig.add_trace(go.Scatter(
            x=q["fecha"], y=y, mode="markers", showlegend=False,
            marker=dict(
                size=11, line=dict(width=1.5, color="white"),
                color=[COLORS["danger"] if d == "Sube" else COLORS["success"] for d in q["direccion"]],
                symbol=["star" if e else "circle" for e in q["evento_id"].notna()],
            ),
            customdata=q[["regimen", "evidencia", "evento_nombre"]].fillna("Sin evento verificado").values,
            hovertemplate=(f"<b>{serie}</b> · %{{x|%b %Y}}<br>%{{customdata[0]}}"
                           "<br>Evidencia: %{customdata[1]}<br>%{customdata[2]}<extra></extra>"),
        ))
    fig.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=50, b=40), height=480,
        xaxis=dict(showgrid=False),
        yaxis=dict(type="log", gridcolor="#E5E7EB", title=f"Índice (ene {desde_anio} = 100, escala log)"),
        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
        title=dict(text="Precio normalizado y quiebres detectados", font=dict(size=14, color=COLORS["primary"]), x=0),
    )
    st.plotly_chart(fig, width="stretch", key="qf_chart_indice")
    st.caption("Rojo: la tendencia sube · Verde: la tendencia baja · Estrella: explicado por un evento")

    if not vista.empty:
        tabla = vista.sort_values("fecha", ascending=False).assign(
            Fecha=lambda d: d["fecha"].map(_mes),
            Cambio=lambda d: d["cambio_precio_6m"].map(lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"),
            Evento=lambda d: d["evento_nombre"].fillna("—"),
        )[["Fecha", "serie", "regimen", "volatilidad", "Cambio", "evidencia", "Evento"]]
        tabla.columns = ["Fecha", "Ferroaleación", "Tendencia", "Volatilidad",
                         "Precio 6m después vs. 6m antes", "Evidencia", "Evento"]
        st.dataframe(tabla, hide_index=True, width="stretch", height=420)

# ---------------------------------------------------------------------------
# Detalle por quiebre
# ---------------------------------------------------------------------------
with tab_detalle:
    if vista.empty:
        st.info("No hay quiebres con los filtros actuales.")
    else:
        ordenado = vista.sort_values("fecha", ascending=False).reset_index(drop=True)
        etiquetas = {
            i: f"{_mes(r.fecha)} · {r.serie} · {r.regimen}" + (" · ★" if r.evento_id else "")
            for i, r in ordenado.iterrows()
        }
        i_sel = st.selectbox("Quiebre", list(etiquetas), format_func=etiquetas.get, key="qf_quiebre")
        q = ordenado.loc[i_sel]

        col_g, col_e = st.columns([3, 2])
        with col_g:
            s = precios[q["serie"]].dropna()
            ventana = s[(s.index >= q["fecha"] - pd.DateOffset(months=q["meses_pre"] + 1))
                        & (s.index <= q["fecha"] + pd.DateOffset(months=q["meses_post"]))]
            fg = go.Figure()
            fg.add_trace(go.Scatter(x=ventana.index, y=ventana.values, mode="lines",
                                    line=dict(color=COLOR_SERIE[q["serie"]], width=2),
                                    hovertemplate="%{x|%b %Y}: %{y:,.2f}<extra></extra>"))
            fg.add_vline(x=q["fecha"], line=dict(color=COLORS["danger"] if q["direccion"] == "Sube" else COLORS["success"],
                                                 dash="dash", width=1.5))
            if q["evento_inicio"] is not None and pd.notna(q["evento_inicio"]):
                fg.add_vline(x=q["evento_inicio"], line=dict(color=COLORS["neutral"], dash="dot", width=1))
            fg.update_layout(
                paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
                margin=dict(l=40, r=20, t=40, b=30), height=320, showlegend=False,
                xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB"),
                title=dict(text=DESCRIPCION_SERIE[q["serie"]], font=dict(size=12, color=COLORS["primary"]), x=0),
            )
            st.plotly_chart(fg, width="stretch", key="qf_chart_detalle")
            st.caption("Línea discontinua: quiebre · Punteada: inicio del evento")

        with col_e:
            p_chow = f"{q['p_chow']:.4f}" if pd.notna(q["p_chow"]) else "no aplica (tramo corto)"
            st.html(
                f"<div style='font-size:13px;line-height:1.6;color:{COLORS['text']};'>"
                f"<div style='font-weight:700;color:{COLORS['primary']};margin-bottom:6px;'>"
                f"{q['serie']} · {_mes(q['fecha'])} · Evidencia {q['evidencia'].lower()}</div>"
                f"<div><b>Tendencia:</b> {q['tendencia_pre_anual']:+.0f}% → {q['tendencia_post_anual']:+.0f}% anual "
                f"<span style='color:{COLORS['text_light']};'>(p = {q['p_tendencia']:.4f})</span></div>"
                f"<div><b>Volatilidad:</b> {q['vol_pre_anual']:.0f}% → {q['vol_post_anual']:.0f}% anual "
                f"<span style='color:{COLORS['text_light']};'>(p = {q['p_volatilidad']:.4f})</span></div>"
                f"<div><b>Cambio estructural (Chow):</b> p = {p_chow}</div>"
                f"<div><b>Régimen anterior / nuevo:</b> {q['meses_pre']} / {q['meses_post']} meses</div>"
                f"</div>"
            )
            if q["evento_id"]:
                url = _url_en(q["evento_fuente"])
                fuente = (f"<a href='{url}' target='_blank' style='color:{COLORS['secondary']};'>Fuente</a>"
                          if url else (q["evento_fuente"] or ""))
                st.html(
                    f"<div style='margin-top:10px;border-left:3px solid {COLORS['primary']};background:#F3F6FA;"
                    f"padding:8px 12px;border-radius:0 6px 6px 0;font-size:13px;'>"
                    f"<div style='font-weight:700;color:{COLORS['primary']};'>{q['evento_nombre']}</div>"
                    f"<div style='margin-top:4px;'>{q['evento_descripcion']}</div>"
                    f"<div style='margin-top:4px;font-size:11px;'>{fuente}</div></div>"
                )
            else:
                st.html(
                    f"<div style='margin-top:10px;border-left:3px solid {COLORS['warning']};background:#FFF8EE;"
                    f"padding:8px 12px;border-radius:0 6px 6px 0;font-size:13px;'>"
                    f"Sin evento verificado en el catálogo para esta fecha.</div>"
                )
            termino = TERMINO_GOOGLE.get(q["serie"], q["serie"])
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
        else:
            st.caption("Las noticias del sistema empiezan en nov 2024; para fechas anteriores se usa el catálogo de eventos.")

# ---------------------------------------------------------------------------
# Método
# ---------------------------------------------------------------------------
with tab_metodo:
    st.markdown(
        """
**Normalización.** Precio vigente al cierre de cada mes. Fastmarkets solo cambia el precio cuando hay
nueva cotización, así que se arrastra la última; no se interpola. Para comparar, cada serie se lleva a
índice 100 en el año elegido.

**Detección.** Se divide la historia de cada ferroaleación en regímenes de tendencia y volatilidad
parecidas. El número de quiebres lo decide el criterio BIC, que castiga agregar quiebres sin necesidad.
Cada régimen dura al menos 6 meses.

**Validación.** Cada quiebre se prueba contra el régimen anterior:
- *Tendencia* (prueba t de Welch): ¿cambió el ritmo al que sube o baja el precio?
- *Volatilidad* (prueba de Levene): ¿cambió qué tanto se mueve?
- *Cambio estructural* (prueba de Chow): ¿cambió la relación del precio con el tiempo?

Evidencia **fuerte**: p < 0.01 en tendencia o volatilidad. **Moderada**: p < 0.05. **Débil**: el modelo
lo marca, pero las pruebas no lo confirman.

**Explicación.** Un quiebre se liga a un evento verificado si menciona esa ferroaleación y la fecha cae
entre 2 meses antes y 4 meses después del evento. Sin evento, queda "sin explicar".
"""
    )

st.caption("Datos: Fastmarkets (AMM), precios en almacén EE.UU. · Eventos: catálogo curado con fuente")
