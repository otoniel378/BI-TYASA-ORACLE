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


def linea_temporal(df, x, y, color=None, titulo="", y_label="Ton", show_area=False, height=None):
    if df.empty:
        return _empty_fig(titulo)
    es_multi_serie = bool(color and color in df.columns)
    if es_multi_serie:
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
    layout = dict(_LAYOUT_BASE)
    if es_multi_serie:
        # Con leyenda de varias series el renglón de abajo necesita más aire, si
        # no el texto de la leyenda se encima con las etiquetas del eje X.
        layout["margin"] = dict(_LAYOUT_BASE["margin"], b=80)
        layout["legend"] = dict(_LAYOUT_BASE["legend"], y=-0.32)
    fig.update_layout(
        **layout, height=height or (_H + (130 if es_multi_serie else 20)),
        title=_title(titulo), xaxis=xax, yaxis=yax, hovermode="x unified",
    )
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


# Paleta categórica para composiciones apiladas — validada (separación entre
# vecinos con y sin daltonismo) sobre fondo blanco. "Otros" va siempre en gris.
_CAT_ESTRUCTURA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
_TEXTO_OSCURO_EN = {"#1baf7a", "#eda100", "#e87ba4", "#B8BCC4"}
_OTROS = "#B8BCC4"
# Par divergente (sube / baja) — neutro a propósito: que suban las importaciones
# no es "bueno" ni "malo" por sí solo, así que no se usa verde/rojo.
_SUBE, _BAJA = "#2a78d6", "#eb6834"


def estructura_100(df, fila, categoria, valor, titulo="", orden_filas=None, height=240):
    """Barras horizontales 100% apiladas: una barra por <fila> (ej. periodo) con
    la composición por <categoria>. El color sigue a la categoría, no a su
    posición, así que la misma categoría tiene el mismo color en cada barra.
    Más de 6 categorías se juntan en "Otros"."""
    if df.empty:
        return _empty_fig(titulo)
    d = df.copy()
    cats = [c for c in d[categoria].drop_duplicates() if c != "Otros"]
    if len(cats) > len(_CAT_ESTRUCTURA):
        d.loc[d[categoria].isin(cats[len(_CAT_ESTRUCTURA):]), categoria] = "Otros"
        cats = cats[:len(_CAT_ESTRUCTURA)]
    d = d.groupby([fila, categoria], as_index=False)[valor].sum()
    d["pct"] = d[valor] / d.groupby(fila)[valor].transform("sum") * 100
    if "Otros" in set(d[categoria]):
        cats.append("Otros")
    filas = orden_filas or list(d[fila].drop_duplicates())

    fig = go.Figure()
    for i, cat in enumerate(cats):
        color = _OTROS if cat == "Otros" else _CAT_ESTRUCTURA[i]
        sub = d[d[categoria] == cat].set_index(fila).reindex(filas)
        pct = sub["pct"].fillna(0)
        fig.add_trace(go.Bar(
            y=filas, x=pct, name=cat, orientation="h",
            marker=dict(color=color, line=dict(color="#FFFFFF", width=2)),
            text=[f"{p:.0f}%" if p >= 6 else "" for p in pct],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(size=10, color="#1F2937" if color in _TEXTO_OSCURO_EN else "#FFFFFF"),
            customdata=sub[valor].fillna(0),
            hovertemplate=f"<b>{cat}</b><br>%{{y}}: %{{x:.1f}}% · %{{customdata:,.0f}} t<extra></extra>",
        ))
    layout = dict(_LAYOUT_BASE)
    layout["legend"] = dict(_LAYOUT_BASE["legend"], y=-0.25, traceorder="normal")
    layout["margin"] = dict(_LAYOUT_BASE["margin"], l=64, b=60)
    fig.update_layout(
        **layout, height=height, title=_title(titulo), barmode="stack",
        xaxis=dict(_XAX, range=[0, 100], ticksuffix="%", showgrid=False),
        yaxis=dict(_YAX, title="", showgrid=False, autorange="reversed", type="category",
                   tickfont=dict(size=11, color="#334155")),
    )
    return fig


def barras_con_tendencia(df, x, y_barras, y_linea, titulo="", y_label="", nombre_barras="Mensual",
                         nombre_linea="Tendencia", hover_extra=None, sufijo="", height=None):
    """Barras tenues para el dato mensual (que puede brincar mucho) + una línea
    para la tendencia suavizada (ej. 12 meses móviles), en el MISMO eje y la
    misma unidad. <hover_extra>: columna con texto ya formateado para el tooltip."""
    if df.empty:
        return _empty_fig(titulo)
    extra = df[hover_extra] if hover_extra else [""] * len(df)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df[x], y=df[y_barras], name=nombre_barras,
        marker=dict(color="rgba(74,123,167,0.35)", line=dict(width=0)),
        customdata=extra,
        hovertemplate=f"{nombre_barras}: <b>%{{y:.1f}}{sufijo}</b> %{{customdata}}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df[x], y=df[y_linea], name=nombre_linea, mode="lines",
        line=dict(color=COLORS["primary"], width=2.5),
        hovertemplate=f"{nombre_linea}: <b>%{{y:.1f}}{sufijo}</b><extra></extra>",
    ))
    ultimo = df.dropna(subset=[y_linea]).iloc[-1] if df[y_linea].notna().any() else None
    if ultimo is not None:
        fig.add_annotation(
            x=ultimo[x], y=ultimo[y_linea], text=f"<b>{ultimo[y_linea]:.1f}{sufijo}</b>",
            showarrow=False, xanchor="left", xshift=6, font=dict(size=11, color=COLORS["primary"]),
        )
    layout = dict(_LAYOUT_BASE)
    layout["margin"] = dict(_LAYOUT_BASE["margin"], r=44, b=70)
    fig.update_layout(
        **layout, height=height or 380, title=_title(titulo), hovermode="x unified", bargap=0.25,
        xaxis=dict(_XAX, title=""),
        yaxis=dict(_YAX, title=y_label, ticksuffix=sufijo, rangemode="tozero"),
    )
    return fig


def barras_divergentes(df, x, y, titulo="", x_label="Ton", resaltar=None, height=None):
    """Barras horizontales que crecen a la derecha si <x> es positivo y a la
    izquierda si es negativo (ganadores/perdedores). Si <df> trae columnas
    "anterior" y "actual", se muestran en el tooltip. <resaltar>: texto que, si
    aparece en la etiqueta, la pone en negritas (ej. la propia TYASA)."""
    if df.empty:
        return _empty_fig(titulo)
    d = df.sort_values(x, ascending=True)
    colores = [_SUBE if v > 0 else _BAJA for v in d[x]]
    textos = [f"{'▲' if v > 0 else '▼'} {abs(v):,.0f}" for v in d[x]]
    tiene_detalle = {"anterior", "actual"} <= set(d.columns)
    fig = go.Figure(go.Bar(
        y=d[y], x=d[x], orientation="h",
        marker=dict(color=colores, line=dict(width=0)),
        text=textos, textposition="outside", textfont=dict(size=10, color="#475569"),
        cliponaxis=False,
        customdata=d[["anterior", "actual"]].to_numpy() if tiene_detalle else None,
        hovertemplate=(
            "<b>%{y}</b><br>Cambio: %{x:+,.0f} t<br>Antes %{customdata[0]:,.0f} t → ahora %{customdata[1]:,.0f} t<extra></extra>"
            if tiene_detalle else "<b>%{y}</b><br>Cambio: %{x:+,.0f} t<extra></extra>"
        ),
    ))
    etiquetas = list(d[y])
    ticktext = [f"<b>{e}</b>" if resaltar and resaltar in e else e for e in etiquetas]
    rango = d[x].abs().max() * 1.25 or 1
    layout = dict(_LAYOUT_BASE)
    layout["margin"] = dict(_LAYOUT_BASE["margin"], l=12, r=24)
    fig.update_layout(
        **layout, height=height or max(260, 26 * len(d) + 90), title=_title(titulo), showlegend=False,
        xaxis=dict(_XAX, title=x_label, range=[-rango, rango], zeroline=True, zerolinecolor="#94A3B8",
                   zerolinewidth=1, showgrid=True, gridcolor=_GRID),
        yaxis=dict(_YAX, title="", showgrid=False, tickmode="array", tickvals=etiquetas, ticktext=ticktext,
                   tickfont=dict(size=10, color="#334155"), automargin=True, type="category"),
    )
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
