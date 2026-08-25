"""
charts.py - Graficos Plotly compactos estilo Power BI para TYASA BI.
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from config import COLORS, HEATMAP_COLORSCALE

_COLOR_SEQ = [
    "#1B3A5C", "#3B82F6", "#06B6D4", "#10B981", "#F59E0B",
    "#8B5CF6", "#EF4444", "#EC4899", "#14B8A6", "#F97316",
]

_FONT      = dict(family="Segoe UI, -apple-system, Inter, Arial", color="#334155", size=11)
_AX_FONT   = dict(color="#64748B", size=10)
_GRID      = "#EEF2F7"
_LINE      = "#DDE3EC"
_H = 240

_LAYOUT_BASE = dict(
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FFFFFF",
    font=_FONT,
    margin=dict(l=42, r=12, t=36, b=32),
    # Streamlit reutiliza el mismo componente Plotly entre reruns (Plotly.react
    # por debajo) cuando el gráfico no cambia de posición/key, así que esta
    # transición sí anima cambios de datos (ej. cambiar un filtro) en vez de
    # solo redibujar de golpe.
    transition=dict(duration=400, easing="cubic-in-out"),
    legend=dict(
        orientation="h", yanchor="bottom", y=-0.32,
        xanchor="center", x=0.5,
        font=dict(size=10, color="#64748B"),
        bgcolor="rgba(0,0,0,0)",
    ),
)

_XAX = dict(showgrid=False, zeroline=False, linecolor=_LINE, tickfont=_AX_FONT, title_font=_AX_FONT, ticklen=3)
_YAX = dict(showgrid=True, gridcolor=_GRID, gridwidth=1, zeroline=False, linecolor=_LINE, tickfont=_AX_FONT, title_font=_AX_FONT, ticklen=0)


def _title(text):
    return dict(text=text, font=dict(size=12, color="#1E293B", family="Segoe UI, sans-serif"), x=0, xanchor="left", pad=dict(b=4))


def linea_temporal(df, x, y, color=None, titulo="", y_label="Ton", show_area=False):
    if df.empty:
        return _empty_fig(titulo)
    if color and color in df.columns:
        fig = px.line(df, x=x, y=y, color=color, color_discrete_sequence=_COLOR_SEQ)
    else:
        if show_area:
            fig = px.area(df, x=x, y=y)
            fig.update_traces(line=dict(color=COLORS["primary"], width=2), fillcolor="rgba(27,58,92,0.07)")
        else:
            fig = px.line(df, x=x, y=y)
            fig.update_traces(line=dict(color=COLORS["primary"], width=2))
    fig.update_traces(mode="lines+markers", marker=dict(size=3.5, symbol="circle"))
    xax = dict(_XAX, title="")
    yax = dict(_YAX, title=y_label)
    fig.update_layout(**_LAYOUT_BASE, height=_H+20, title=_title(titulo), xaxis=xax, yaxis=yax, hovermode="x unified")
    return fig


def barras_horizontales(df, x, y, titulo="", x_label="Ton", max_items=12):
    if df.empty:
        return _empty_fig(titulo)
    df_plot = df.nlargest(max_items, x).sort_values(x, ascending=True)
    fig = px.bar(df_plot, x=x, y=y, orientation="h", color_discrete_sequence=[COLORS["primary"]], text=x)
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", textfont=dict(size=9, color="#64748B"), marker_line_width=0, marker_opacity=0.88)
    xax = dict(_XAX, title=x_label, showgrid=True, gridcolor=_GRID)
    yax = dict(_YAX, title="", showgrid=False, tickfont=dict(size=10, color="#334155"))
    fig.update_layout(**_LAYOUT_BASE, title=_title(titulo), xaxis=xax, yaxis=yax, showlegend=False)
    return fig


def barras_verticales(df, x, y, titulo="", x_label="", y_label="Ton", max_items=12):
    if df.empty:
        return _empty_fig(titulo)
    df_plot = df.nlargest(max_items, y)
    fig = px.bar(df_plot, x=x, y=y, color_discrete_sequence=[COLORS["primary"]], text=y)
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", textfont=dict(size=9, color="#64748B"), marker_line_width=0, marker_opacity=0.88)
    xax = dict(_XAX, title=x_label, tickangle=-45, tickfont=dict(size=9, color="#334155"))
    yax = dict(_YAX, title=y_label, showgrid=True, gridcolor=_GRID)
    fig.update_layout(**_LAYOUT_BASE, title=_title(titulo), xaxis=xax, yaxis=yax, showlegend=False)
    return fig


def donut(df, names, values, titulo="", hole=0.55):
    if df.empty:
        return _empty_fig(titulo)
    fig = px.pie(df, names=names, values=values, hole=hole, color_discrete_sequence=_COLOR_SEQ)
    fig.update_traces(
        textposition="outside",
        textinfo="percent+label",
        textfont=dict(size=10, family="Segoe UI, sans-serif"),
        hovertemplate="%{label}<br>%{value:,.1f} ton - %{percent}",
        marker=dict(line=dict(color="#FFFFFF", width=2.5)),
        pull=[0.05] + [0]*20
    )
    # Avoid duplicate legend from _LAYOUT_BASE
    layout = dict(_LAYOUT_BASE)
    layout.pop("legend", None)
    fig.update_layout(
        **layout,
        title=_title(titulo),
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="right",
            x=1.3,
            font=dict(size=9, color="#334155"),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


def barras_verticales(df, x, y, titulo="", y_label="Ton", x_label="", max_items=12):
    if df.empty:
        return _empty_fig(titulo)
    df_plot = df.nlargest(max_items, y) if y in df.columns else df.head(max_items)
    fig = px.bar(df_plot, x=x, y=y, color_discrete_sequence=[COLORS["primary"]], text=y)
    fig.update_traces(
        texttemplate="%{text:,.0f}", textposition="outside",
        textfont=dict(size=9, color="#64748B"),
        marker_line_width=0, marker_opacity=0.88,
    )
    xax = dict(_XAX, title=x_label, tickangle=-30, tickfont=dict(size=9, color="#334155"))
    yax = dict(_YAX, title=y_label)
    fig.update_layout(**_LAYOUT_BASE, title=_title(titulo), xaxis=xax, yaxis=yax, showlegend=False)
    return fig


def treemap(df, path, values, titulo=""):
    if df.empty:
        return _empty_fig(titulo)
    fig = px.treemap(df, path=path, values=values, color=values, color_continuous_scale=HEATMAP_COLORSCALE)
    fig.update_traces(textfont=dict(size=11, family="Segoe UI, sans-serif"), marker=dict(line=dict(width=2, color="#FFFFFF")), hovertemplate="%{label}<br>%{value:,.1f} ton<extra></extra>")
    fig.update_layout(**_LAYOUT_BASE, title=_title(titulo), coloraxis_showscale=False)
    return fig


def heatmap(pivot_df, titulo="", x_label="Ano", y_label="Mes", fmt=".0f"):
    if pivot_df.empty:
        return _empty_fig(titulo)
    fig = go.Figure(data=go.Heatmap(z=pivot_df.values, x=[str(c) for c in pivot_df.columns], y=pivot_df.index.tolist(), colorscale=HEATMAP_COLORSCALE, hoverongaps=False, hovertemplate=f"<b>%{{y}} - %{{x}}</b><br>%{{z:{fmt}}} ton<extra></extra>", showscale=True))
    xax = dict(_XAX, title=x_label)
    yax = dict(_YAX, title=y_label, showgrid=False)
    fig.update_layout(**_LAYOUT_BASE, title=_title(titulo), xaxis=xax, yaxis=yax, coloraxis_colorbar=dict(thickness=10, tickfont=dict(size=9, color="#64748B"), outlinewidth=0))
    return fig


def pareto(df, x, y, y_acum="PCT_ACUM", titulo="Analisis Pareto", max_items=25):
    if df.empty:
        return _empty_fig(titulo)
    df_plot = df.head(max_items).copy()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_plot[x], y=df_plot[y], name="Toneladas", marker_color=COLORS["primary"], marker_opacity=0.88, marker_line_width=0, hovertemplate="%{x}<br>%{y:,.1f} ton<extra></extra>"))
    if y_acum in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot[x], y=df_plot[y_acum], name="% Acum.", yaxis="y2", line=dict(color="#F59E0B", width=1.8, dash="dot"), mode="lines+markers", marker=dict(size=3.5, color="#F59E0B"), hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>"))
        fig.add_hline(y=80, yref="y2", line=dict(color="#EF4444", width=1, dash="dash"), annotation_text="80%", annotation_position="right", annotation_font=dict(size=9, color="#EF4444"))
    layout = {k: v for k, v in _LAYOUT_BASE.items() if k != "legend"}
    xax = dict(_XAX, tickangle=-38, tickfont=dict(size=8, color="#64748B"))
    yax = dict(_YAX, title="Ton")
    fig.update_layout(**layout, height=_H+20, title=_title(titulo), xaxis=xax, yaxis=yax, yaxis2=dict(title="% Acum.", overlaying="y", side="right", range=[0, 108], showgrid=False, ticksuffix="%", tickfont=_AX_FONT, title_font=_AX_FONT), legend=dict(orientation="h", y=-0.35, x=0.5, xanchor="center", font=dict(size=9, color="#64748B")), barmode="overlay")
    return fig


def scatter(df, x, y, size=None, color=None, hover_name=None, titulo="", x_label="", y_label=""):
    if df.empty:
        return _empty_fig(titulo)
    fig = px.scatter(df, x=x, y=y, size=size, color=color, hover_name=hover_name, color_discrete_sequence=_COLOR_SEQ, color_continuous_scale=HEATMAP_COLORSCALE)
    fig.update_layout(**_LAYOUT_BASE, title=_title(titulo), xaxis=dict(_XAX, title=x_label or x), yaxis=dict(_YAX, title=y_label or y))
    return fig


def _empty_fig(titulo=""):
    fig = go.Figure()
    fig.update_layout(**_LAYOUT_BASE, title=_title(titulo), xaxis=dict(visible=False), yaxis=dict(visible=False), annotations=[dict(text="Sin datos para el periodo seleccionado", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=11, color="#94A3B8"))])
    return fig
