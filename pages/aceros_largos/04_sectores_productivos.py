"""
pages/aceros_largos/04_sectores_productivos.py — Sectores Productivos Aceros Largos
Vista gerencial: qué subsector de construcción jala la demanda, qué tan fuerte y qué hacer.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from aceros_largos.charts_gerencial import (
    chart_barras_variacion,
    chart_waterfall,
    chart_barras_horizontales,
)

try:
    from aceros_largos.loaders import load_sectoral_analysis, get_last_update
    from aceros_largos.loaders_new_data import (
        load_inegi_construccion_segmented,
        get_latest_value,
        _choose_preferred_series,
    )
    DATOS_REALES = True
except ImportError as e:
    DATOS_REALES = False
    st.error(f"No se pudieron cargar los loaders reales. Error: {e}")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

SECTOR_DESCRIPTIONS = {
    "23 Construcción total": {
        "producto": "Varilla, alambrón, perfiles",
        "relevancia": "Alta — refleja toda la actividad constructora",
        "lee_mas": "Si este número baja, TODA la demanda de largos se ve afectada. Es el KPI más crítico."
    },
    "236 Edificación": {
        "producto": "Principalmente varilla corrugada y alambrón",
        "relevancia": "Alta — vivienda y edificios comerciales",
        "lee_mas": "Edificación sube, lo que activa a las desarrolladoras y genera demanda directa de varilla."
    },
    "237 Obras de ingeniería civil": {
        "producto": "Perfiles estructurales, varilla para infraestructura",
        "relevancia": "Alta — carreteras, puentes, presas, energía",
        "lee_mas": "Depende de gasto público federal. Si el gobierno gasta, este sector aguanta aunque el privado caiga."
    },
    "238 Trabajos especializados": {
        "producto": "Varilla y herrería especializada",
        "relevancia": "Media — ejecución y terminación de obra",
        "lee_mas": "Señal de que la obra iniciada avanza. Sube cuando el 236 y 237 ya están activos."
    },
}


def _color_semaforo(valor):
    if valor is None:
        return "#999", "Sin datos"
    if valor < -10:
        return "#C62828", "Crítico"
    if valor < -3:
        return "#E65100", "Alerta"
    if valor < 0:
        return "#F9A825", "Precaución"
    return "#2E7D32", "Favorable"


def _interpretacion_sector(nombre, valor, tendencia):
    """Retorna texto gerencial según el estado del sector."""
    if valor is None:
        return "Sin datos", "Verificar conexión BigQuery.", "N/D", "#999"

    color, _ = _color_semaforo(valor)

    if valor < -10:
        situacion = f"Caída severa: **{abs(valor):.1f}%** anual."
        if "Edificación" in nombre:
            impacto = "Desarrolladoras pausando obras. Demanda de varilla en caída directa."
            accion = "Revisar cartera de clientes en vivienda. Evaluar si hay proyectos con crédito comprometido."
        elif "ingeniería" in nombre or "civil" in nombre:
            impacto = "Obra pública detenida o en retraso. Proyectos de infraestructura sin arrancar."
            accion = "Monitorear licitaciones nuevas de SCT, SENER, IMSS. Evaluar si hay proyectos privados sustitutos."
        elif "especializado" in nombre:
            impacto = "Las obras que estaban avanzando se detuvieron. Señal de contracción general."
            accion = "Revisar si el freno es por falta de financiamiento o problemas de ejecución."
        else:
            impacto = "Todo el sector construcción contrayéndose. Impacto en toda la línea de productos largos."
            accion = "Posición defensiva. No adelantar compras. Priorizar clientes con obra activa confirmada."
    elif valor < -3:
        situacion = f"Debilitamiento moderado: **{abs(valor):.1f}%** anual."
        impacto = "Demanda bajo presión pero sin colapso. Clientes postponen pedidos."
        accion = "Segmentar cartera. Mantener seguimiento semanal con clientes clave. No bajar precio indiscriminadamente."
    elif valor < 0:
        situacion = f"Leve caída de **{abs(valor):.1f}%** — mercado lateral."
        impacto = "Sin crecimiento en demanda. Sin señales fuertes ni positivas ni negativas."
        accion = "Mantener posición. Buscar oportunidades en nichos específicos (vivienda social, obra pública local)."
    elif valor < 5:
        situacion = f"Crecimiento moderado: **{valor:.1f}%** anual."
        impacto = "Demanda con leve impulso positivo. Clientes más activos en pedidos."
        accion = "Asegurar disponibilidad de producto. Contactar nuevos proyectos en pipeline."
    else:
        situacion = f"Expansión sólida: **{valor:.1f}%** anual."
        impacto = "Demanda activa. Oportunidad de capturar volumen y mejorar mezcla."
        accion = "Preparar disponibilidad. Evaluar capacidad de respuesta antes de prometer plazos."

    return situacion, impacto, accion, color


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

st.title("Sectores Productivos — Aceros Largos")
st.markdown(
    "¿Qué subsector de la construcción está jalando o frenando la demanda? "
    "**Cada sector traducido a impacto en producto, volumen y acción comercial.**"
)

with st.sidebar:
    st.header("Configuración")
    periodo_meses = st.selectbox(
        "Período de análisis",
        options=[6, 12, 24],
        index=1,
        format_func=lambda x: f"Últimos {x} meses"
    )
    umbral_critico = st.slider("Umbral crítico (%)", -30, -5, -10)
    umbral_alerta  = st.slider("Umbral alerta (%)",  -15,  0,  -3)

# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600)
def cargar_sectores(periodo_meses):
    try:
        construccion_df = load_inegi_construccion_segmented(periodo_meses)
        sectores = {}
        if not construccion_df.empty:
            for segmento, impacto in [
                ("23 Construcción total",        "Alto"),
                ("236 Edificación",              "Alto"),
                ("237 Obras de ingeniería civil","Alto"),
                ("238 Trabajos especializados",  "Medio"),
            ]:
                seg_df = construccion_df[construccion_df["segmento"] == segmento].copy()
                if seg_df.empty:
                    continue

                # La tabla trae varias series mezcladas: índice base, variación mensual,
                # variación anual, etc. Para un gerente usamos SIEMPRE variación anual.
                # Esto evita lecturas ficticias como 170% o tendencias de miles de pp.
                seg_df = _choose_preferred_series(
                    seg_df,
                    preferred_patterns=[
                        r"variaci[oó]n porcentual anual",
                        r"variaci[oó]n porcentual respecto al mismo mes",
                    ],
                ).sort_values("fecha", ascending=False)

                latest_val  = get_latest_value(seg_df)
                latest_numeric = pd.to_numeric(latest_val, errors="coerce")
                previous_val = pd.to_numeric(seg_df.iloc[1]["valor"], errors="coerce") if len(seg_df) > 1 else None
                trend_pct = (
                    float(latest_numeric - previous_val)
                    if previous_val is not None and pd.notna(previous_val) and pd.notna(latest_numeric)
                    else 0.0
                )
                serie_data  = seg_df.sort_values("fecha").tail(24).copy()
                serie_data["mes"] = serie_data["fecha"].dt.strftime("%b %Y")
                sectores[segmento] = {
                    "nombre": segmento,
                    "valor_actual": float(latest_val) if latest_val is not None else None,
                    "tendencia_pct": float(trend_pct) if trend_pct else 0.0,
                    "impacto_acero": impacto,
                    "serie_reciente": serie_data[["mes", "fecha", "valor"]].to_dict("records"),
                }
        return sectores
    except Exception as e:
        st.warning(f"Error cargando sectores: {e}")
        return {}


if DATOS_REALES:
    with st.spinner("Cargando datos sectoriales INEGI…"):
        sectoral_data = cargar_sectores(periodo_meses)
        if not sectoral_data:
            try:
                sectoral_data = load_sectoral_analysis() or {}
            except Exception:
                sectoral_data = {}
    if sectoral_data:
        st.success(f"Datos reales cargados: {len(sectoral_data)} subsectores")
    else:
        st.warning("Sin datos reales. Verificar conexión BigQuery.")
else:
    sectoral_data = {}

if not sectoral_data:
    st.info("No hay datos sectoriales disponibles. No se muestran datos simulados.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 1: SEMÁFORO DE SECTORES
# ---------------------------------------------------------------------------

st.subheader("¿Cómo está cada subsector?")
st.caption("De mayor a menor impacto en la demanda de Aceros Largos.")

cols = st.columns(len(sectoral_data))
for i, (seg_key, seg_info) in enumerate(sectoral_data.items()):
    with cols[i]:
        v = seg_info.get("valor_actual")
        t = seg_info.get("tendencia_pct", 0)
        color, etiqueta = _color_semaforo(v)

        val_str   = f"{v:.1f}%" if v is not None else "N/D"
        delta_str = f"{t:+.1f} pp" if t else None

        st.metric(
            label=seg_key.split(" ", 1)[-1] if " " in seg_key else seg_key,
            value=val_str,
            delta=delta_str,
        )
        st.html(
            f"<div style='text-align:center; font-size:13px; font-weight:700; color:{color}; margin-top:-4px;'>{etiqueta}</div>"
        )
        desc = SECTOR_DESCRIPTIONS.get(seg_key, {})
        st.caption(desc.get("relevancia", ""))

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 2: ANÁLISIS DETALLADO POR SECTOR
# ---------------------------------------------------------------------------

st.subheader("Detalle gerencial por subsector")

for seg_key, seg_info in sectoral_data.items():
    v = seg_info.get("valor_actual")
    t = seg_info.get("tendencia_pct", 0)
    sit, imp, acc, color = _interpretacion_sector(seg_key, v, t)

    desc = SECTOR_DESCRIPTIONS.get(seg_key, {})
    with st.expander(
        f"{seg_key}  •  {'Crítico' if v and v < umbral_critico else 'Alerta' if v and v < umbral_alerta else 'Favorable' if v and v >= 0 else 'Sin datos'}  {v:.1f}% YoY" if v else f"{seg_key}  •  Sin datos",
        expanded=(seg_key == "23 Construcción total")
    ):
        col_info, col_graf = st.columns([1, 2])

        with col_info:
            st.html(f"""
            <div style="
                border-left: 5px solid {color};
                padding: 12px 14px;
                background: #fafafa;
                border-radius: 0 6px 6px 0;
                font-size: 13px;
            ">
                <div style="font-weight:700; font-size:14px; color:#1B3A5C; margin-bottom:8px;">{seg_key}</div>
                <p><strong>Producto principal:</strong><br>{desc.get("producto", "N/D")}</p>
                <p><strong>Situación:</strong><br>{sit}</p>
                <p><strong>Impacto en Aceros Largos:</strong><br>{imp}</p>
                <p style="font-weight:700; color:#1B3A5C;"><strong>▶ Acción sugerida:</strong><br>{acc}</p>
                <p style="color:#777; font-size:11px; margin-top:8px;">{desc.get("lee_mas", "")}</p>
            </div>
            """)

            if t < -3:
                st.warning(f"Tendencia empeorando: {t:+.1f} pp este mes.")
            elif t > 3:
                st.success(f"Tendencia mejorando: {t:+.1f} pp este mes.")

        with col_graf:
            serie = seg_info.get("serie_reciente", [])
            if serie:
                df_s = pd.DataFrame(serie)
                df_s["valor"] = pd.to_numeric(df_s["valor"], errors="coerce")
                if "fecha" in df_s.columns:
                    df_s = df_s.dropna(subset=["valor"]).sort_values("fecha")
                x_vals = df_s["mes"].tolist() if "mes" in df_s.columns else list(range(len(df_s)))
                y_vals = df_s["valor"].tolist()

                tab_bar, tab_wf = st.tabs(["Por mes", "Cascada"])

                with tab_bar:
                    fig_sec = chart_barras_variacion(
                        x=x_vals, y=y_vals,
                        titulo=f"{seg_key.split(' ',1)[-1]} — variación % mensual",
                        umbral_critico=umbral_critico,
                        umbral_alerta=umbral_alerta,
                        height=300,
                    )
                    st.plotly_chart(fig_sec, width="stretch")

                with tab_wf:
                    fig_wf = chart_waterfall(
                        etiquetas=x_vals[-12:],
                        valores=y_vals[-12:],
                        titulo="Cascada de tendencia — cómo se acumula",
                        height=300,
                    )
                    st.plotly_chart(fig_wf, width="stretch")
            else:
                st.info("Sin serie histórica para este sector.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 3: COMPARATIVO ENTRE SECTORES
# ---------------------------------------------------------------------------

st.subheader("¿Qué subsector está mejor y cuál peor?")
st.caption("Comparación directa para priorizar atención comercial.")

nombres, valores, colores_bar = [], [], []
for seg_key, seg_info in sectoral_data.items():
    v = seg_info.get("valor_actual")
    if v is None:
        continue
    etiqueta = seg_key.replace("23 ", "").replace("236 ", "").replace("237 ", "").replace("238 ", "")
    nombres.append(etiqueta)
    valores.append(v)
    c, _ = _color_semaforo(v)
    colores_bar.append(c)

if nombres:
    # Barras horizontales: texto de sector legible sin rotar
    fig_comp = chart_barras_horizontales(
        valores=valores,
        etiquetas=nombres,
        titulo="Comparativo de subsectores — % YoY (leer de arriba hacia abajo)",
        color_base="#2E7D32",
        color_negativo="#C62828",
        unidad="%",
        height=max(280, len(nombres) * 60),
    )
    # Sobreescribir texto para mostrar %
    fig_comp.update_traces(
        text=[f"{v:+.1f}%" for v in sorted(valores)],
        textfont=dict(size=12),
    )
    st.plotly_chart(fig_comp, width="stretch")

    # Lectura automática
    mejor = max(zip(nombres, valores), key=lambda x: x[1])
    peor  = min(zip(nombres, valores), key=lambda x: x[1])

    col_b, col_p = st.columns(2)
    with col_b:
        c_m, _ = _color_semaforo(mejor[1])
        st.html(f"""
        <div style="background:#E8F5E9; border:1px solid #2E7D32; border-radius:8px; padding:12px;">
            <strong>Mejor señal: {mejor[0]}</strong><br>
            <span style="font-size:22px; color:#2E7D32;">{mejor[1]:+.1f}%</span><br>
            <span style="font-size:12px; color:#555;">Priorizar atención en este subsector si quieres capturar volumen.</span>
        </div>
        """)

    with col_p:
        c_p, _ = _color_semaforo(peor[1])
        st.html(f"""
        <div style="background:#FFEBEE; border:1px solid #C62828; border-radius:8px; padding:12px;">
            <strong>Señal más débil: {peor[0]}</strong><br>
            <span style="font-size:22px; color:#C62828;">{peor[1]:+.1f}%</span><br>
            <span style="font-size:12px; color:#555;">Clientes de este subsector están bajo mayor presión. Revisar cartera.</span>
        </div>
        """)

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 4: PROYECCIÓN Y RECOMENDACIÓN ESTRATÉGICA
# ---------------------------------------------------------------------------

st.subheader("¿Qué esperar los próximos 3 meses?")

construccion_total = sectoral_data.get("23 Construcción total", {})
v_total = construccion_total.get("valor_actual")
t_total = construccion_total.get("tendencia_pct", 0)

col_proj, col_rec = st.columns(2)

with col_proj:
    st.markdown("**Visión de corto plazo basada en datos reales**")
    if v_total is not None:
        if v_total < -10:
            vision = "Visión negativa"
            resumen = "La construcción está en contracción severa."
            porque = "El dato actual está por debajo de -10%, nivel que históricamente implica menor inicio y avance de obra."
            impacto = "Demanda probable de varilla y alambrón bajo presión. Riesgo de sobreinventario si se compra de más."
            bg = "#FFEBEE"
            border = "#C62828"
        elif v_total < -3:
            vision = "Visión cautelosa"
            resumen = "La construcción sigue débil, aunque no está en caída extrema."
            porque = "El indicador permanece en terreno negativo; el sector todavía no confirma recuperación."
            impacto = "Demanda lateral o ligeramente a la baja. Conviene cuidar margen y cartera antes que perseguir volumen."
            bg = "#FFF3E0"
            border = "#E65100"
        elif v_total < 0:
            vision = "Visión neutral con riesgo"
            resumen = "La construcción está cerca de estabilizarse, pero aún no crece."
            porque = "El dato está apenas debajo de cero; falta confirmación de varios meses positivos."
            impacto = "No hay señal suficiente para aumentar inventario agresivamente. Mantener flexibilidad."
            bg = "#FFFDE7"
            border = "#F9A825"
        else:
            vision = "Visión positiva"
            resumen = "La construcción está en terreno positivo."
            porque = "El indicador muestra crecimiento anual; eso suele anticipar más pedidos de productos largos."
            impacto = "Mayor probabilidad de recuperación de demanda, especialmente en varilla, alambrón y perfiles."
            bg = "#E8F5E9"
            border = "#2E7D32"

        tendencia_txt = (
            "mejorando" if t_total > 1 else
            "empeorando" if t_total < -1 else
            "estable"
        )
        st.html(f"""
        <div style="background:{bg}; border:1px solid {border}; border-left:5px solid {border}; border-radius:8px; padding:16px;">
            <div style="font-size:18px; font-weight:800; color:#1B3A5C; margin-bottom:8px;">{vision}</div>
            <p style="margin:0 0 8px 0; font-size:14px;"><strong>{resumen}</strong></p>
            <p style="margin:0 0 8px 0; font-size:13px;"><strong>Por qué:</strong> {porque}</p>
            <p style="margin:0 0 8px 0; font-size:13px;"><strong>Tendencia reciente:</strong> {tendencia_txt} ({t_total:+.1f} pp vs dato anterior).</p>
            <div style="font-size:13px; color:#1B3A5C; font-weight:700;">
                Impacto esperado: {impacto}
            </div>
        </div>
        """)
        st.caption("No se muestra predicción numérica porque no hay modelo estadístico validado; se muestra una lectura ejecutiva de corto plazo con datos reales.")
    else:
        st.info("Sin datos suficientes para generar visión de corto plazo.")

with col_rec:
    st.markdown("**Recomendación estratégica**")
    if v_total is not None:
        if v_total < -10:
            st.html("""
            <div style="background:#FFEBEE; border:1px solid #C62828; border-radius:8px; padding:14px;">
                <strong>Estrategia Defensiva</strong>
                <ul style="margin:8px 0 0 0; padding-left:18px; font-size:13px;">
                    <li>Priorizar proyectos con crédito confirmado</li>
                    <li>No sobrecomprar inventario de varilla/alambrón</li>
                    <li>Buscar volumen en exportación o infraestructura pública</li>
                    <li>Revisar límites de crédito con clientes constructoras</li>
                </ul>
            </div>
            """)
        elif v_total < -3:
            st.html("""
            <div style="background:#FFF3E0; border:1px solid #E65100; border-radius:8px; padding:14px;">
                <strong>Estrategia Conservadora</strong>
                <ul style="margin:8px 0 0 0; padding-left:18px; font-size:13px;">
                    <li>Monitoreo semanal de permisos de edificación</li>
                    <li>Mantener inventario operativo sin adelantar compras</li>
                    <li>Optimizar mezcla para márgenes, no sólo volumen</li>
                    <li>Preparar propuestas para cuando la tasa baje</li>
                </ul>
            </div>
            """)
        else:
            st.html("""
            <div style="background:#E8F5E9; border:1px solid #2E7D32; border-radius:8px; padding:14px;">
                <strong>Estrategia de Crecimiento</strong>
                <ul style="margin:8px 0 0 0; padding-left:18px; font-size:13px;">
                    <li>Asegurar disponibilidad antes del repunte</li>
                    <li>Activar clientes dormidos con propuesta proactiva</li>
                    <li>Capturar market share con entrega ágil</li>
                    <li>Coordinar compras/producción para no quedar corto</li>
                </ul>
            </div>
            """)
    else:
        st.info("Sin datos para generar recomendación.")

st.divider()
st.caption(f"Datos: INEGI — Encuesta Nacional de Empresas Constructoras · Actualizado: {get_last_update() if DATOS_REALES else 'N/D'}")
