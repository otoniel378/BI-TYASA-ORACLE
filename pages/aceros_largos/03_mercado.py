"""
pages/aceros_largos/03_mercado.py — Mercado y Costos
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from aceros_largos.loaders import load_market_data, get_last_update, get_data_sources

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
st.title("Aceros Largos — Mercado y Costos")
st.markdown("Monitoreo de variables clave: tipo de cambio, precios de materias primas y costos operativos")

# ---------------------------------------------------------------------------
# DATOS
# ---------------------------------------------------------------------------
with st.spinner("Cargando datos de mercado..."):
    data = load_market_data()

# ---------------------------------------------------------------------------
# INDICADORES PRINCIPALES
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    # USD/MXN
    usd_mxn = data["usd_mxn"]
    trend_color = "#C62828" if usd_mxn["trend_type"] == "up" else "#2E7D32"  # Up = malo para importaciones
    
    st.html(f"""
    <div style="background: linear-gradient(135deg, rgba(27, 58, 92, 0.1) 0%, rgba(75, 123, 167, 0.05) 100%);
                border: 1px solid rgba(75, 123, 167, 0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="font-size: 12px; color: #666; margin-bottom: 5px;">{usd_mxn["label"]}</div>
                <div style="font-size: 32px; font-weight: bold; color: #1B3A5C; margin-bottom: 5px;">{usd_mxn["value"]}</div>
                <div style="font-size: 11px; color: {trend_color};">{usd_mxn["trend"]}</div>
                <div style="font-size: 10px; color: #999; margin-top: 3px;">{usd_mxn["unit"]}</div>
            </div>
        </div>
    </div>
    """)

with col2:
    # CHATARRA
    scrap = data["scrap_price"]
    trend_color = "#2E7D32" if scrap["trend_type"] == "down" else "#C62828"  # Down = bueno para costos
    
    st.html(f"""
    <div style="background: linear-gradient(135deg, rgba(27, 58, 92, 0.1) 0%, rgba(75, 123, 167, 0.05) 100%);
                border: 1px solid rgba(75, 123, 167, 0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="font-size: 12px; color: #666; margin-bottom: 5px;">{scrap["label"]}</div>
                <div style="font-size: 32px; font-weight: bold; color: #1B3A5C; margin-bottom: 5px;">{scrap["value"]}</div>
                <div style="font-size: 11px; color: {trend_color};">{scrap["trend"]}</div>
                <div style="font-size: 10px; color: #999; margin-top: 3px;">{scrap["unit"]}</div>
            </div>
        </div>
    </div>
    """)

# ---------------------------------------------------------------------------
# GRÁFICOS DE TENDENCIAS
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Evolución USD/MXN (Simulada)")
    
    # Generar datos simulados para los últimos 30 días
    dates = [datetime.now() - timedelta(days=i) for i in range(30, 0, -1)]
    base_rate = 17.82
    rates = [base_rate + (i * 0.02 - 0.3) for i in range(30)]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates,
        y=rates,
        mode='lines',
        line=dict(color='#4A7BA7', width=2),
        fill='tonexty',
        fillcolor='rgba(75, 123, 167, 0.1)',
        name='USD/MXN',
        hovertemplate='<b>%{x}</b><br>Tipo de Cambio: $%{y:.2f}<extra></extra>'
    ))
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Arial", size=12),
        xaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)'),
        yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)', title="Pesos por Dólar"),
        height=300,
        margin=dict(l=20, r=20, t=20, b=20),
        showlegend=False
    )
    
    st.plotly_chart(fig, width="stretch")

with col2:
    st.subheader("Precio Chatarra (Simulado)")
    
    # Generar datos simulados para precio de chatarra
    scrap_dates = [datetime.now() - timedelta(days=i) for i in range(30, 0, -1)]
    base_scrap = 3380
    scrap_prices = [base_scrap + (i * 15 - 225) for i in range(30)]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=scrap_dates,
        y=scrap_prices,
        mode='lines',
        line=dict(color='#C62828', width=2),
        fill='tonexty',
        fillcolor='rgba(198, 40, 40, 0.1)',
        name='Precio Chatarra',
        hovertemplate='<b>%{x}</b><br>Precio: $%{y:,.0f} MXN/ton<extra></extra>'
    ))
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Arial", size=12),
        xaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)'),
        yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)', title="MXN por Tonelada"),
        height=300,
        margin=dict(l=20, r=20, t=20, b=20),
        showlegend=False
    )
    
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# MATRIZ DE IMPACTOS
# ---------------------------------------------------------------------------
st.subheader("Matriz de Impactos de Precios")

impact_data = [
    {"Variable": "USD/MXN (+1.64%)", "Costos": "Neutro", "Ventas": "Positivo", "Margen": "Positivo", "Comentario": "Mejora competitividad exportadora"},
    {"Variable": "Chatarra (-2.1%)", "Costos": "Muy Positivo", "Ventas": "Neutro", "Margen": "Muy Positivo", "Comentario": "Reduce 60% del costo directo"},
    {"Variable": "Energía (Stable)", "Costos": "Neutro", "Ventas": "Neutro", "Margen": "Neutro", "Comentario": "Sin variaciones significativas"},
    {"Variable": "Construcción (-15.6%)", "Costos": "Neutro", "Ventas": "Muy Negativo", "Margen": "Muy Negativo", "Comentario": "Principal mercado contraído"},
]

# Crear tabla con colores
for item in impact_data:
    cols = st.columns([2, 1, 1, 1, 2])
    
    with cols[0]:
        st.write(f"**{item['Variable']}**")
    
    with cols[1]:
        color = {"Muy Positivo": "#2E7D32", "Positivo": "#66BB6A", "Neutro": "#757575", 
                "Negativo": "#EF5350", "Muy Negativo": "#C62828"}.get(item["Costos"], "#757575")
        st.html(f'<span style="color: {color}; font-weight: bold;">{item["Costos"]}</span>')
    
    with cols[2]:
        color = {"Muy Positivo": "#2E7D32", "Positivo": "#66BB6A", "Neutro": "#757575", 
                "Negativo": "#EF5350", "Muy Negativo": "#C62828"}.get(item["Ventas"], "#757575")
        st.html(f'<span style="color: {color}; font-weight: bold;">{item["Ventas"]}</span>')
    
    with cols[3]:
        color = {"Muy Positivo": "#2E7D32", "Positivo": "#66BB6A", "Neutro": "#757575", 
                "Negativo": "#EF5350", "Muy Negativo": "#C62828"}.get(item["Margen"], "#757575")
        st.html(f'<span style="color: {color}; font-weight: bold;">{item["Margen"]}</span>')
    
    with cols[4]:
        st.write(item["Comentario"])

# ---------------------------------------------------------------------------
# CALCULADORA DE SENSIBILIDAD
# ---------------------------------------------------------------------------
st.subheader("Calculadora de Sensibilidad")
st.markdown("Simula el impacto de cambios en variables clave sobre márgenes")

col1, col2, col3 = st.columns(3)

with col1:
    usd_change = st.slider("Cambio USD/MXN (%)", -10.0, 10.0, 1.64, 0.1)
    
with col2:
    scrap_change = st.slider("Cambio Precio Chatarra (%)", -15.0, 15.0, -2.1, 0.1)
    
with col3:
    volume_change = st.slider("Cambio Volumen Ventas (%)", -30.0, 30.0, -12.9, 0.1)

# Cálculo simplificado de impacto
base_margin = 14.2
margin_impact = (usd_change * 0.3) + (scrap_change * -0.8) + (volume_change * 0.2)
new_margin = base_margin + margin_impact

impact_color = "#2E7D32" if margin_impact > 0 else "#C62828"

st.markdown("### Resultado de Sensibilidad")
st.html(f"""
<div style="background: linear-gradient(135deg, rgba(27, 58, 92, 0.1) 0%, rgba(75, 123, 167, 0.05) 100%);
            border: 1px solid rgba(75, 123, 167, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
    <div style="font-size: 14px; color: #666; margin-bottom: 10px;">Margen Operativo Proyectado</div>
    <div style="font-size: 36px; font-weight: bold; color: #1B3A5C;">{new_margin:.1f}%</div>
    <div style="font-size: 14px; color: {impact_color}; margin-top: 10px;">
        {margin_impact:+.1f}pp vs base ({base_margin}%)
    </div>
</div>
""")

# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
st.divider()

col1, col2 = st.columns([1, 1])
with col1:
    st.html("""
    <div style="display: flex; align-items: center; gap: 8px;">
        <span style="display: inline-flex; width: 8px; height: 8px; background-color: #4A7BA7;
                     border-radius: 50%;"></span>
        <span style="font-size: 10px; color: #666; font-weight: bold; text-transform: uppercase;
                     letter-spacing: 1px;">Mercados en Tiempo Real · Bloomberg &amp; Platts</span>
    </div>
    """)

with col2:
    sources = " · ".join(get_data_sources())
    st.html(f"""
    <div style="text-align: right; font-size: 10px; color: #999;">
        Última actualización: {get_last_update()}<br>
        {sources}
    </div>
    """)