"""
09_mapa_estatal.py — Mapa de calor de indicadores INEGI por entidad federativa.

A diferencia de 04_indicadores.py (indicadores nacionales), aquí la fuente es
GOLD_INDICADORES_INEGI_ESTADO: mismas claves INEGI, desagregadas por área
geográfica (01-32). El catálogo de indicadores con esta desagregación se va
ampliando en mercado/inegi/loaders.py conforme se detectan más (ver nota ahí
sobre qué SÍ y qué NO tiene desglose estatal).
"""

import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import json

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from mercado.inegi.loaders import (
    INDICADORES_ESTADO_CONFIG,
    INDICADORES_ESTADO_LABEL,
    ESTADOS_INEGI,
    load_meses_disponibles_estado,
    load_mapa_estado,
    load_serie_estado,
    load_ranking_yoy_estado,
)

_BG      = "#0F1923"
_SURFACE = "#1A2535"
_GRID    = "#2A3A52"
_TEXT    = "#94A3B8"
_ACCENT  = "#81C784"

_GEOJSON_PATH = os.path.join(_root, "assets", "mx_estados.geojson")

# Sequential de un solo tono (verde, en línea con el grupo ENEC del dashboard
# nacional) — oscuro/desaturado para valores bajos, brillante para altos, la
# variante que mejor contrasta sobre fondo oscuro.
_COLORSCALE = [
    [0.0,  "#16281F"],
    [0.25, "#245C43"],
    [0.5,  "#3D8360"],
    [0.75, "#5FA97E"],
    [1.0,  "#8CD9A0"],
]


@st.cache_data(show_spinner=False)
def _load_geojson() -> dict:
    with open(_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _fmt_valor(v) -> str:
    try:
        f = float(v)
    except Exception:
        return "—"
    if abs(f) >= 1_000_000:
        return f"${f/1_000_000:,.1f}M"
    if abs(f) >= 1_000:
        return f"${f/1_000:,.0f}K"
    return f"${f:,.0f}"


def _make_mapa(df: pd.DataFrame, geojson: dict, label: str) -> go.Figure:
    vmax = df["valor"].quantile(0.90)
    fig = px.choropleth(
        df, geojson=geojson, locations="estado_iso", featureidkey="properties.id",
        color="valor", color_continuous_scale=_COLORSCALE,
        range_color=(0, max(vmax, df["valor"].min())),
        hover_name="estado_nombre",
        custom_data=["estado_nombre", "valor"],
    )
    fig.update_traces(
        marker_line_color=_BG, marker_line_width=0.8,
        hovertemplate="<b>%{customdata[0]}</b><br>" + label + ": %{customdata[1]:,.0f}<extra></extra>",
    )
    fig.update_geos(
        fitbounds="locations", visible=False,
        bgcolor=_BG, showframe=False, showcountries=False,
    )
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_BG,
        font=dict(color=_TEXT, size=11),
        margin=dict(l=0, r=0, t=10, b=0),
        height=480,
        coloraxis_colorbar=dict(
            title=dict(text="", font=dict(color=_TEXT)),
            tickfont=dict(color=_TEXT), thickness=14, len=0.65,
            outlinewidth=0, bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


def _make_ranking(df: pd.DataFrame, label: str) -> go.Figure:
    d = df.sort_values("valor", ascending=True)
    colors = [_ACCENT if v == d["valor"].max() else "#4E7A63" for v in d["valor"]]
    fig = go.Figure(go.Bar(
        x=d["valor"], y=d["estado_nombre"], orientation="h",
        marker=dict(color=colors),
        hovertemplate="<b>%{y}</b><br>" + label + ": %{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_SURFACE,
        font=dict(color=_TEXT, size=10.5),
        xaxis=dict(gridcolor=_GRID, showgrid=True, title=None),
        yaxis=dict(gridcolor=_GRID, showgrid=False, title=None, automargin=True),
        margin=dict(l=10, r=20, t=10, b=10),
        height=620, showlegend=False,
    )
    return fig


def _make_serie_estado(df_serie: pd.DataFrame, df_nacional: pd.DataFrame, label: str, color: str) -> go.Figure:
    fig = go.Figure()
    if not df_nacional.empty:
        dn = df_nacional.sort_values("fecha")
        fig.add_trace(go.Scatter(
            x=dn["fecha"], y=dn["valor"], mode="lines", name="Nacional",
            line=dict(color="#5B6B85", width=1.6, dash="dot"),
            hovertemplate="Nacional %{x|%b %Y}: %{y:,.0f}<extra></extra>",
        ))
    ds = df_serie.sort_values("fecha")
    fig.add_trace(go.Scatter(
        x=ds["fecha"], y=ds["valor"], mode="lines+markers", name=label,
        line=dict(color=color, width=2.5), marker=dict(size=5, color=color),
        hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_SURFACE,
        font=dict(color=_TEXT, size=11),
        xaxis=dict(gridcolor=_GRID, showgrid=True, title=None, tickformat="%b %Y"),
        yaxis=dict(gridcolor=_GRID, showgrid=True, title=None),
        margin=dict(l=50, r=20, t=20, b=20),
        height=320, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def _kpi_card(titulo: str, valor: str, sub: str = "", color: str = _ACCENT) -> str:
    sub_html = f'<div style="margin-top:4px;font-size:11px;color:#64748B;">{sub}</div>' if sub else ""
    return (
        f'<div style="background:{_SURFACE};border-radius:12px;padding:14px 16px;'
        f'border-left:4px solid {color};">'
        f'<div style="font-size:10px;color:#94A3B8;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.06em;">{titulo}</div>'
        f'<div style="margin-top:6px;font-size:22px;font-weight:700;color:#E2E8F0;'
        f'font-family:\'Courier New\',monospace;">{valor}</div>'
        f'{sub_html}</div>'
    )


def main():
    render()


def render():
    st.markdown(
        "<h2 style='color:#E2E8F0;margin-bottom:2px;'>Mapa de Calor · INEGI por Estado</h2>"
        "<p style='color:#64748B;margin:0;'>Monitoreo mensual de indicadores INEGI desagregados "
        "por entidad federativa</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    claves = list(INDICADORES_ESTADO_CONFIG.keys())
    col_ind, col_mes = st.columns([2.5, 1.5])
    with col_ind:
        clave = st.selectbox(
            "Indicador", options=claves,
            format_func=lambda c: INDICADORES_ESTADO_LABEL.get(c, c),
            key="mapa_estado_clave",
        )
    label = INDICADORES_ESTADO_LABEL.get(clave, clave)

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

    df_nac = load_serie_estado(clave, "00", periodos=1)
    valor_nac = float(df_nac.iloc[0]["valor"]) if not df_nac.empty else None

    # ── KPIs ─────────────────────────────────────────────────────────────────
    top_row = df_mapa.iloc[0]
    bottom_row = df_mapa.iloc[-1]
    suma_estados = df_mapa["valor"].sum()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.html(_kpi_card("Nacional", _fmt_valor(valor_nac), mes_sel))
    with c2:
        st.html(_kpi_card("Suma 32 estados", _fmt_valor(suma_estados)))
    with c3:
        st.html(_kpi_card("Estado líder", top_row["estado_nombre"], _fmt_valor(top_row["valor"]), "#66BB6A"))
    with c4:
        st.html(_kpi_card("Estado menor", bottom_row["estado_nombre"], _fmt_valor(bottom_row["valor"]), "#EF9A9A"))

    st.markdown("<div style='margin:12px 0 4px;'></div>", unsafe_allow_html=True)

    # ── Mapa + Ranking ───────────────────────────────────────────────────────
    col_mapa, col_rank = st.columns([2.4, 1.6])
    geojson = _load_geojson()
    with col_mapa:
        st.plotly_chart(_make_mapa(df_mapa, geojson, label), width="stretch", key="plt_mapa_estado")
        st.caption("Escala de color truncada al percentil 90 para mejor contraste — pasa el cursor para ver el valor exacto de cada estado.")
    with col_rank:
        st.plotly_chart(_make_ranking(df_mapa, label), width="stretch", key="plt_rank_estado")

    st.divider()

    # ── Drill-down por estado ────────────────────────────────────────────────
    st.markdown(
        "<p style='color:#94A3B8;font-size:12px;font-weight:600;text-transform:uppercase;"
        "letter-spacing:0.06em;margin:0 0 8px;'>Historial de un estado</p>",
        unsafe_allow_html=True,
    )
    nombres = df_mapa["estado_nombre"].tolist()
    estado_nombre_sel = st.selectbox("Estado", options=nombres, key="mapa_estado_drill")
    estado_cve_sel = None
    for cve, (_iso, nombre) in ESTADOS_INEGI.items():
        if nombre == estado_nombre_sel:
            estado_cve_sel = cve
            break

    if estado_cve_sel:
        df_serie_estado = load_serie_estado(clave, estado_cve_sel, periodos=60)
        df_serie_nac = load_serie_estado(clave, "00", periodos=60)
        if not df_serie_estado.empty:
            st.plotly_chart(
                _make_serie_estado(df_serie_estado, df_serie_nac, estado_nombre_sel, _ACCENT),
                width="stretch", key="plt_serie_estado",
            )
        else:
            st.info("Sin historial disponible para este estado.")

    st.caption(f"Fuente: INEGI BIE · tabla gold_indicadores_inegi_estado · {len(claves)} indicador(es) con desagregación estatal")


if __name__ == "__main__":
    main()
