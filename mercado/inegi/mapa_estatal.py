"""
mapa_estatal.py — Mapa de calor de indicadores INEGI por entidad federativa.
Se embebe como pestaña dentro de pages/mercado/04_indicadores.py.

A diferencia de los indicadores nacionales (INDICADORES_CONFIG), aquí la
fuente es GOLD_INDICADORES_INEGI_ESTADO: mismas claves INEGI, desagregadas
por área geográfica (01-32). El catálogo de indicadores con esta
desagregación se va ampliando en loaders.py (INDICADORES_ESTADO_CONFIG)
conforme se detectan más — ver la nota ahí sobre qué SÍ y qué NO tiene
desglose estatal.
"""

import os
import json

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from mercado.inegi.loaders import (
    INDICADORES_ESTADO_CONFIG,
    INDICADORES_ESTADO_LABEL,
    INDICADORES_ESTADO_UNIDAD,
    ESTADOS_INEGI,
    load_meses_disponibles_estado,
    load_mapa_estado,
    load_serie_estado,
)

# ── Paleta clara (consistente con config.py / assets/style.css) ─────────────
_BG      = "#FFFFFF"   # fondo de gráficas/mapa
_SURFACE = "#FFFFFF"   # fondo de tarjetas
_BORDER  = "#DDE3EC"
_GRID    = "#E2E8F0"
_TEXT    = "#334155"   # texto de ejes/etiquetas de gráficas
_MUTED   = "#64748B"   # texto secundario
_ACCENT  = "#2E7D32"   # verde (líneas / acento por defecto)
_HIGHLIGHT = "#1B3A5C" # navy — contorno del estado seleccionado

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_GEOJSON_PATH = os.path.join(_ROOT, "assets", "mx_estados.geojson")

# Sequential de un solo tono (verde) — claro para valores bajos, oscuro y
# saturado para altos, calibrado para fondo blanco.
_COLORSCALE = [
    [0.0,  "#F1F8F4"],
    [0.25, "#C8E6C9"],
    [0.5,  "#81C784"],
    [0.75, "#43A047"],
    [1.0,  "#1B5E20"],
]

_ESTADO_TODOS = "Todos los estados"


@st.cache_data(show_spinner=False)
def _load_geojson() -> dict:
    with open(_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _fmt_pesos(v) -> str:
    """Formatea un valor ya convertido a pesos reales (no crudo de la API).
    Se mantiene todo en 'millones de pesos' (convención de reportes MX) salvo
    montos billonarios, donde se escala a 'billones' para no mostrar 7+ dígitos."""
    try:
        f = float(v)
    except Exception:
        return "—"
    signo = "-" if f < 0 else ""
    f = abs(f)
    if f >= 1_000_000_000_000:
        return f"{signo}${f/1_000_000_000_000:,.2f} billones MXN"
    if f >= 1_000_000:
        return f"{signo}${f/1_000_000:,.0f} M MXN"
    if f >= 1_000:
        return f"{signo}${f/1_000:,.0f} K MXN"
    return f"{signo}${f:,.0f} MXN"


def _fmt_personas(v) -> str:
    try:
        f = float(v)
    except Exception:
        return "—"
    return f"{f:,.0f} personas"


def _fmt_valor(v, unidad: str) -> str:
    return _fmt_pesos(v) if unidad == "mxn" else _fmt_personas(v)


def _make_mapa(df: pd.DataFrame, geojson: dict, label: str, unidad: str, estado_iso_sel: str | None) -> go.Figure:
    vmax = df["valor"].quantile(0.90)
    val_fmt = "$%{customdata[1]:,.0f} MXN" if unidad == "mxn" else "%{customdata[1]:,.0f} personas"
    fig = px.choropleth(
        df, geojson=geojson, locations="estado_iso", featureidkey="properties.id",
        color="valor", color_continuous_scale=_COLORSCALE,
        range_color=(0, max(vmax, df["valor"].min())),
        hover_name="estado_nombre",
        custom_data=["estado_nombre", "valor"],
    )
    fig.update_traces(
        marker_line_color="#FFFFFF", marker_line_width=0.8,
        hovertemplate="<b>%{customdata[0]}</b><br>" + label + ": " + val_fmt + "<extra></extra>",
    )
    if estado_iso_sel:
        # Contorno resaltado sobre el estado seleccionado — relleno transparente
        # (no tapa el color real) y borde grueso navy, con transición animada.
        fig.add_trace(go.Choropleth(
            geojson=geojson, locations=[estado_iso_sel], z=[1],
            featureidkey="properties.id",
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            showscale=False, marker_line_color=_HIGHLIGHT, marker_line_width=4,
            hoverinfo="skip",
        ))
    fig.update_geos(
        fitbounds="locations", visible=False,
        bgcolor=_BG, showframe=False, showcountries=False,
    )
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_BG,
        font=dict(color=_TEXT, size=11),
        margin=dict(l=0, r=0, t=10, b=0),
        height=480, showlegend=False,
        transition=dict(duration=450, easing="cubic-in-out"),
        coloraxis_colorbar=dict(
            title=dict(text="", font=dict(color=_TEXT)),
            tickfont=dict(color=_TEXT), thickness=14, len=0.65,
            outlinewidth=0, bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


def _make_ranking(df: pd.DataFrame, label: str, unidad: str, estado_sel: str | None) -> go.Figure:
    d = df.sort_values("valor", ascending=True)
    colors = ["#9CC7A1"] * len(d)
    for i, nombre in enumerate(d["estado_nombre"]):
        if estado_sel and nombre == estado_sel:
            colors[i] = _HIGHLIGHT
        elif d["valor"].iloc[i] == d["valor"].max():
            colors[i] = _ACCENT
    val_fmt = "$%{x:,.0f} MXN" if unidad == "mxn" else "%{x:,.0f} personas"
    tick_fmt = "$,.2s" if unidad == "mxn" else ",.2s"
    fig = go.Figure(go.Bar(
        x=d["valor"], y=d["estado_nombre"], orientation="h",
        marker=dict(color=colors),
        hovertemplate="<b>%{y}</b><br>" + label + ": " + val_fmt + "<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_SURFACE,
        font=dict(color=_TEXT, size=10.5),
        xaxis=dict(gridcolor=_GRID, showgrid=True, title=None, tickformat=tick_fmt),
        yaxis=dict(gridcolor=_GRID, showgrid=False, title=None, automargin=True),
        margin=dict(l=10, r=20, t=10, b=10),
        height=620, showlegend=False,
        transition=dict(duration=450, easing="cubic-in-out"),
    )
    return fig


def _make_serie_estado(df_serie: pd.DataFrame, df_nacional: pd.DataFrame, label: str, color: str, unidad: str) -> go.Figure:
    val_fmt = "$%{y:,.0f} MXN" if unidad == "mxn" else "%{y:,.0f} personas"
    val_fmt_nac = val_fmt
    tick_fmt = "$,.2s" if unidad == "mxn" else ",.2s"
    fig = go.Figure()
    if not df_nacional.empty:
        dn = df_nacional.sort_values("fecha")
        fig.add_trace(go.Scatter(
            x=dn["fecha"], y=dn["valor"], mode="lines", name="Nacional",
            line=dict(color="#94A3B8", width=1.6, dash="dot"),
            hovertemplate="Nacional %{x|%b %Y}: " + val_fmt_nac + "<extra></extra>",
        ))
    ds = df_serie.sort_values("fecha")
    fig.add_trace(go.Scatter(
        x=ds["fecha"], y=ds["valor"], mode="lines+markers", name=label,
        line=dict(color=color, width=2.5), marker=dict(size=5, color=color),
        hovertemplate="%{x|%b %Y}: " + val_fmt + "<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_SURFACE,
        font=dict(color=_TEXT, size=11),
        xaxis=dict(gridcolor=_GRID, showgrid=True, title=None, tickformat="%b %Y"),
        yaxis=dict(gridcolor=_GRID, showgrid=True, title=None, tickformat=tick_fmt),
        margin=dict(l=50, r=20, t=20, b=20),
        height=320, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def _kpi_card(titulo: str, valor: str, sub: str = "", color: str = _ACCENT) -> str:
    sub_html = f'<div style="margin-top:4px;font-size:11px;color:{_MUTED};">{sub}</div>' if sub else ""
    return (
        f'<div style="background:{_SURFACE};border:1px solid {_BORDER};border-radius:8px;'
        f'padding:14px 16px;border-left:4px solid {color};box-shadow:0 1px 3px rgba(15,23,42,0.05);">'
        f'<div style="font-size:10px;color:{_MUTED};font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.06em;">{titulo}</div>'
        f'<div style="margin-top:6px;font-size:19px;font-weight:700;color:#0F172A;'
        f'font-family:\'Courier New\',monospace;">{valor}</div>'
        f'{sub_html}</div>'
    )


def render() -> None:
    st.markdown(
        f"<p style='color:{_MUTED};font-size:12.5px;margin:4px 0 14px;line-height:1.5;'>"
        "Monitoreo mensual de indicadores INEGI desagregados por entidad federativa.</p>",
        unsafe_allow_html=True,
    )

    claves = list(INDICADORES_ESTADO_CONFIG.keys())
    col_ind, col_mes, col_estado = st.columns([2.3, 1.2, 1.8])
    with col_ind:
        clave = st.selectbox(
            "Indicador", options=claves,
            format_func=lambda c: INDICADORES_ESTADO_LABEL.get(c, c),
            key="mapa_estado_clave",
        )
    label = INDICADORES_ESTADO_LABEL.get(clave, clave)
    unidad = INDICADORES_ESTADO_UNIDAD.get(clave, "mxn")

    with st.spinner("Cargando meses disponibles..."):
        meses = load_meses_disponibles_estado(clave)
    if not meses:
        st.info(
            "Sin datos en `GOLD_INDICADORES_INEGI_ESTADO`. Ejecuta "
            "`scripts/update_inegi_estado_data.py` para cargar datos."
        )
        return

    with col_mes:
        mes_sel = st.selectbox("Mes", options=meses, index=0, key="mapa_estado_mes")

    df_mapa = load_mapa_estado(clave, mes_sel)
    if df_mapa.empty:
        st.warning(f"Sin datos por estado para {mes_sel}.")
        return

    nombres_estados = df_mapa.sort_values("estado_nombre")["estado_nombre"].tolist()
    with col_estado:
        estado_sel = st.selectbox(
            "Estado", options=[_ESTADO_TODOS] + nombres_estados, key="mapa_estado_filtro",
        )
    estado_activo = None if estado_sel == _ESTADO_TODOS else estado_sel
    estado_cve_sel = estado_iso_sel = None
    if estado_activo:
        for cve, (iso, nombre) in ESTADOS_INEGI.items():
            if nombre == estado_activo:
                estado_cve_sel, estado_iso_sel = cve, iso
                break

    df_nac = load_serie_estado(clave, "00", periodos=1)
    valor_nac = float(df_nac.iloc[0]["valor"]) if not df_nac.empty else None

    # ── KPIs ─────────────────────────────────────────────────────────────────
    top_row = df_mapa.iloc[0]
    bottom_row = df_mapa.iloc[-1]
    suma_estados = df_mapa["valor"].sum()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.html(_kpi_card("Nacional", _fmt_valor(valor_nac, unidad), mes_sel))
    with c2:
        st.html(_kpi_card("Suma 32 estados", _fmt_valor(suma_estados, unidad)))
    with c3:
        if estado_activo:
            fila_sel = df_mapa[df_mapa["estado_nombre"] == estado_activo].iloc[0]
            st.html(_kpi_card(f"{estado_activo}", _fmt_valor(fila_sel["valor"], unidad), "Estado seleccionado", _HIGHLIGHT))
        else:
            st.html(_kpi_card("Estado líder", top_row["estado_nombre"], _fmt_valor(top_row["valor"], unidad), _ACCENT))
    with c4:
        st.html(_kpi_card("Estado menor", bottom_row["estado_nombre"], _fmt_valor(bottom_row["valor"], unidad), "#C62828"))

    st.markdown("<div style='margin:12px 0 4px;'></div>", unsafe_allow_html=True)

    # ── Mapa + Ranking ───────────────────────────────────────────────────────
    col_mapa, col_rank = st.columns([2.4, 1.6])
    geojson = _load_geojson()
    with col_mapa:
        st.plotly_chart(
            _make_mapa(df_mapa, geojson, label, unidad, estado_iso_sel),
            width="stretch", key="plt_mapa_estado",
        )
        st.caption("Escala de color truncada al percentil 90 para mejor contraste — pasa el cursor para ver el valor exacto de cada estado. Usa el filtro \"Estado\" arriba para resaltarlo en el mapa.")
    with col_rank:
        st.plotly_chart(
            _make_ranking(df_mapa, label, unidad, estado_activo),
            width="stretch", key="plt_rank_estado",
        )

    st.divider()

    # ── Historial del estado seleccionado (o de todo el país) ───────────────
    titulo_historial = f"Historial — {estado_activo}" if estado_activo else "Historial nacional"
    st.markdown(
        f"<p style='color:{_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;"
        f"letter-spacing:0.06em;margin:0 0 8px;'>{titulo_historial}</p>",
        unsafe_allow_html=True,
    )

    cve_serie = estado_cve_sel or "00"
    nombre_serie = estado_activo or "Nacional"
    df_serie_estado = load_serie_estado(clave, cve_serie, periodos=60)
    df_serie_nac = load_serie_estado(clave, "00", periodos=60) if estado_activo else pd.DataFrame()
    if not df_serie_estado.empty:
        st.plotly_chart(
            _make_serie_estado(df_serie_estado, df_serie_nac, nombre_serie, _HIGHLIGHT if estado_activo else _ACCENT, unidad),
            width="stretch", key="plt_serie_estado",
        )
    else:
        st.info("Sin historial disponible.")

    st.caption(f"Fuente: INEGI BIE · tabla gold_indicadores_inegi_estado · {len(claves)} indicador(es) con desagregación estatal")
