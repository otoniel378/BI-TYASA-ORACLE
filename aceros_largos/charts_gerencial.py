"""
aceros_largos/charts_gerencial.py
Gráficos ejecutivos para Aceros Largos.

Principios:
- Un vistazo basta: el color dice si es bueno o malo, sin leer números
- Área rellena muestra acumulación de tendencia
- Waterfall muestra avance paso a paso
- Barras horizontales = texto legible sin rotar
- Nunca líneas simples para series de variación (confunden dirección)
"""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Optional, List

# Paleta corporativa TYASA
ROJO    = "#C62828"
NARANJA = "#E65100"
AMARILLO = "#F9A825"
VERDE   = "#2E7D32"
AZUL    = "#1B3A5C"
AZUL_CLARO = "#4A7BA7"
GRIS    = "#757575"

# Rellenos semi-transparentes
FILL_ROJO    = "rgba(198,40,40,0.15)"
FILL_NARANJA = "rgba(230,81,0,0.15)"
FILL_VERDE   = "rgba(46,125,50,0.15)"
FILL_AZUL    = "rgba(27,58,92,0.12)"


def _color_por_valor(v, malo=-5, alerta=-2):
    """Color semáforo según valor numérico."""
    if v < malo:     return ROJO
    if v < alerta:   return NARANJA
    if v < 0:        return AMARILLO
    return VERDE


def chart_barras_variacion(
    x: List[str],
    y: List[float],
    titulo: str,
    yaxis_title: str = "% Variación Anual",
    umbral_critico: float = -10,
    umbral_alerta: float = -3,
    height: int = 340,
    mostrar_labels: bool = True,
    anotacion_leyenda: str = "",
) -> go.Figure:
    """
    Barras de color automático para variaciones YoY/MoM.
    Verde si ≥ 0, amarillo si < 0, naranja si < umbral_alerta, rojo si < umbral_crítico.
    Ideal para: construcción, PIB, sectores.
    """
    colores = [
        ROJO    if v < umbral_critico else
        NARANJA if v < umbral_alerta  else
        AMARILLO if v < 0            else
        VERDE
        for v in y
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x,
        y=y,
        marker_color=colores,
        marker_line_width=0,
        text=[f"{v:+.1f}%" for v in y] if mostrar_labels else None,
        textposition="outside",
        textfont=dict(size=11, color="#333"),
        cliponaxis=False,
        hovertemplate="%{x}: <b>%{y:+.1f}%</b><extra></extra>",
    ))

    fig.add_hline(y=0, line_width=2, line_color=GRIS, opacity=0.6)

    if umbral_alerta:
        fig.add_hline(
            y=umbral_alerta,
            line_dash="dot", line_color=NARANJA, opacity=0.5,
            annotation_text="Alerta", annotation_font_color=NARANJA,
            annotation_position="bottom right"
        )
    if umbral_critico:
        fig.add_hline(
            y=umbral_critico,
            line_dash="dot", line_color=ROJO, opacity=0.5,
            annotation_text="Crítico", annotation_font_color=ROJO,
            annotation_position="top right"
        )

    anotaciones = []
    if anotacion_leyenda:
        anotaciones.append(dict(
            x=0.01, y=0.98, xref="paper", yref="paper",
            text=anotacion_leyenda, showarrow=False,
            font=dict(size=10, color=GRIS),
            align="left",
        ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14, color=AZUL)),
        height=height,
        showlegend=False,
        yaxis_title=yaxis_title,
        yaxis=dict(zeroline=False, gridcolor="#f0f0f0"),
        xaxis=dict(tickangle=-30 if len(x) > 10 else 0, tickfont=dict(size=11)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=50, b=50, l=50, r=20),
        annotations=anotaciones,
    )
    return fig


def chart_area_tendencia(
    x: List[str],
    y: List[float],
    titulo: str,
    yaxis_title: str,
    color_positivo: bool = True,
    height: int = 280,
    mostrar_promedio: bool = True,
    unidad: str = "",
) -> Optional[go.Figure]:
    """
    Área rellena con gradiente.
    De un vistazo se ve si la tendencia sube o baja y cuánto.
    Ideal para: inflación, TIIE, USD/MXN (series que no cruzan cero frecuentemente).
    """
    if not x or not y:
        return None

    # Determinar color según tendencia reciente
    reciente = y[-3:] if len(y) >= 3 else y
    tendencia_baja = reciente[-1] < reciente[0] if len(reciente) > 1 else False

    # Para inflación/tasa: bajar es bueno, verde cuando baja
    if color_positivo:
        color_linea = VERDE if tendencia_baja else ROJO
        fill_color  = FILL_VERDE if tendencia_baja else FILL_ROJO
    else:
        # Para USD: depende del contexto, usamos azul neutro
        color_linea = AZUL_CLARO
        fill_color  = FILL_AZUL

    fig = go.Figure()

    # Área rellena
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="lines",
        line=dict(color=color_linea, width=2.5),
        fill="tozeroy",
        fillcolor=fill_color,
        name=titulo,
        hovertemplate="%{x}: <b>%{y:.2f}" + unidad + "</b><extra></extra>",
    ))

    # Puntos en el último valor para destacarlo
    fig.add_trace(go.Scatter(
        x=[x[-1]], y=[y[-1]],
        mode="markers+text",
        marker=dict(color=color_linea, size=10, line=dict(color="#fff", width=2)),
        text=[f"<b>{y[-1]:.2f}{unidad}</b>"],
        textposition="top center",
        textfont=dict(size=12, color=color_linea),
        showlegend=False,
        hoverinfo="skip",
    ))

    if mostrar_promedio and len(y) > 3:
        prom = sum(y) / len(y)
        fig.add_hline(
            y=prom, line_dash="dot", line_color=GRIS, opacity=0.6,
            annotation_text=f"Promedio: {prom:.2f}{unidad}",
            annotation_font_color=GRIS,
            annotation_position="bottom right"
        )

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=13, color=AZUL)),
        height=height,
        showlegend=False,
        yaxis_title=yaxis_title,
        yaxis=dict(gridcolor="#f0f0f0", zeroline=False),
        xaxis=dict(tickangle=-30 if len(x) > 10 else 0, tickfont=dict(size=10)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=45, b=45, l=50, r=20),
    )
    return fig


def chart_area_doble_eje(
    x: List[str],
    y1: List[float],
    y2: List[float],
    nombre1: str,
    nombre2: str,
    titulo: str,
    y1_title: str,
    y2_title: str,
    height: int = 340,
) -> go.Figure:
    """
    Dos áreas con ejes Y independientes.
    Ideal para: construcción vs demanda interna.
    """
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=x, y=y1,
        name=nombre1,
        marker_color=[ROJO if v < -5 else NARANJA if v < 0 else VERDE for v in y1],
        marker_line_width=0,
        opacity=0.85,
        yaxis="y1",
        hovertemplate="%{x}: <b>%{y:+.1f}%</b><extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=x, y=y2,
        name=nombre2,
        mode="lines+markers",
        line=dict(color=AZUL, width=3),
        marker=dict(size=8, color=AZUL, line=dict(color="#fff", width=2)),
        yaxis="y2",
        hovertemplate="%{x}: <b>%{y:,.0f} ton</b><extra></extra>",
    ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14, color=AZUL)),
        height=height,
        legend=dict(orientation="h", y=1.08, x=0),
        yaxis=dict(
            title=y1_title,
            gridcolor="#f0f0f0",
            zeroline=True, zerolinecolor=GRIS, zerolinewidth=1.5,
        ),
        yaxis2=dict(
            title=y2_title,
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=55, b=45, l=55, r=55),
    )
    return fig


def chart_barras_apiladas_comercio(
    x: List[str],
    importaciones: List[float],
    exportaciones: List[float],
    titulo: str,
    height: int = 360,
) -> go.Figure:
    """
    Barras apiladas importación (rojo) vs exportación (verde).
    La diferencia entre alturas = balanza. De un vistazo se ve cuál domina.
    """
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=x, y=importaciones,
        name="Importaciones",
        marker_color=ROJO,
        marker_line_width=0,
        opacity=0.85,
        hovertemplate="%{x}: <b>%{y:,.0f} ton</b><extra>Importaciones</extra>",
    ))

    fig.add_trace(go.Bar(
        x=x, y=exportaciones,
        name="Exportaciones",
        marker_color=VERDE,
        marker_line_width=0,
        opacity=0.85,
        hovertemplate="%{x}: <b>%{y:,.0f} ton</b><extra>Exportaciones</extra>",
    ))

    # Línea de balanza
    balanza = [e - i for e, i in zip(exportaciones, importaciones)]
    fig.add_trace(go.Scatter(
        x=x, y=balanza,
        name="Balanza",
        mode="lines+markers",
        line=dict(color=AZUL, width=2.5, dash="dot"),
        marker=dict(size=6, color=AZUL),
        hovertemplate="%{x}: balanza <b>%{y:+,.0f} ton</b><extra>Balanza</extra>",
    ))

    fig.add_hline(y=0, line_width=2, line_color=GRIS, opacity=0.5)

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14, color=AZUL)),
        height=height,
        barmode="group",
        legend=dict(orientation="h", y=1.08, x=0),
        yaxis=dict(title="Toneladas", gridcolor="#f0f0f0"),
        xaxis=dict(tickangle=-30 if len(x) > 10 else 0, tickfont=dict(size=10)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=55, b=50, l=55, r=20),
    )
    return fig


def chart_barras_horizontales(
    valores: List[float],
    etiquetas: List[str],
    titulo: str,
    color_base: str = AZUL,
    color_negativo: Optional[str] = None,
    unidad: str = " ton",
    height: int = 300,
) -> go.Figure:
    """
    Barras horizontales con etiquetas grandes.
    Ideal para: top países, top productos. Texto siempre legible.
    """
    colores = []
    for v in valores:
        if color_negativo and v < 0:
            colores.append(color_negativo)
        else:
            colores.append(color_base)

    # Ordenar de mayor a menor para lectura natural
    pares = sorted(zip(valores, etiquetas, colores), key=lambda x: x[0])
    valores_s  = [p[0] for p in pares]
    etiquetas_s = [p[1] for p in pares]
    colores_s  = [p[2] for p in pares]

    fig = go.Figure(go.Bar(
        x=valores_s,
        y=etiquetas_s,
        orientation="h",
        marker_color=colores_s,
        marker_line_width=0,
        text=[f"{abs(v)/1000:,.1f}K{unidad}" if abs(v) >= 1000 else f"{v:,.0f}{unidad}" for v in valores_s],
        textposition="outside",
        textfont=dict(size=11),
        cliponaxis=False,
        hovertemplate="%{y}: <b>%{x:,.0f}" + unidad + "</b><extra></extra>",
    ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=13, color=AZUL)),
        height=max(height, len(etiquetas) * 42 + 80),
        showlegend=False,
        xaxis=dict(title="Toneladas", gridcolor="#f0f0f0", zeroline=False),
        yaxis=dict(tickfont=dict(size=12)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=45, b=30, l=20, r=80),
    )
    return fig


def chart_waterfall(
    etiquetas: List[str],
    valores: List[float],
    titulo: str,
    yaxis_title: str = "% YoY",
    height: int = 320,
) -> go.Figure:
    """
    Waterfall (cascada).
    Muestra cómo cada mes se suma o resta al acumulado.
    Ideal para entender si la tendencia empeora o mejora progresivamente.
    """
    medidas = ["relative"] * len(valores)
    colores  = [VERDE if v >= 0 else ROJO for v in valores]

    fig = go.Figure(go.Waterfall(
        x=etiquetas,
        y=valores,
        measure=medidas,
        connector=dict(line=dict(color=GRIS, width=1, dash="dot")),
        increasing=dict(marker_color=VERDE),
        decreasing=dict(marker_color=ROJO),
        text=[f"{v:+.1f}%" for v in valores],
        textposition="outside",
        textfont=dict(size=10),
        hovertemplate="%{x}: <b>%{y:+.1f}%</b><extra></extra>",
    ))

    fig.add_hline(y=0, line_width=1.5, line_color=GRIS, opacity=0.5)

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=13, color=AZUL)),
        height=height,
        showlegend=False,
        yaxis_title=yaxis_title,
        yaxis=dict(gridcolor="#f0f0f0"),
        xaxis=dict(tickangle=-30 if len(etiquetas) > 10 else 0, tickfont=dict(size=10)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=45, b=50, l=50, r=20),
    )
    return fig


def chart_gauge_simple(valor: float, titulo: str, rango_min: float, rango_max: float,
                        umbral_rojo: float, umbral_amarillo: float, unidad: str = "%") -> go.Figure:
    """
    Gauge (velocímetro) para un KPI puntual.
    Verde/Amarillo/Rojo según umbrales. Lectura instantánea.
    """
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=valor,
        number=dict(suffix=unidad, font=dict(size=28, color=AZUL)),
        title=dict(text=titulo, font=dict(size=13, color=AZUL)),
        gauge=dict(
            axis=dict(range=[rango_min, rango_max], tickwidth=1),
            bar=dict(color=AZUL),
            steps=[
                dict(range=[rango_min, umbral_rojo],    color=FILL_ROJO),
                dict(range=[umbral_rojo, umbral_amarillo], color=FILL_NARANJA),
                dict(range=[umbral_amarillo, rango_max], color=FILL_VERDE),
            ],
            threshold=dict(
                line=dict(color=ROJO, width=3),
                thickness=0.75,
                value=umbral_rojo
            )
        )
    ))
    fig.update_layout(
        height=200,
        margin=dict(t=40, b=10, l=30, r=30),
        paper_bgcolor="#ffffff",
    )
    return fig
