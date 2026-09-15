"""
pages/aceros_largos/01_resumen.py — Dashboard Ejecutivo Aceros Largos
Vista gerencial: qué está pasando, cómo nos afecta, qué hacer.
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from aceros_largos.loaders_new_data import load_internal_demand_aceros_largos
from aceros_largos.charts_gerencial import (
    chart_barras_variacion,
    chart_area_tendencia,
    chart_waterfall,
)

try:
    from aceros_largos.loaders import (
        load_macroeconomic_indicators,
        load_steel_market_data,
        get_last_update,
        get_data_sources,
    )
    DATOS_REALES = True
except Exception:
    DATOS_REALES = False

# ---------------------------------------------------------------------------
# HELPERS DE INTERPRETACIÓN
# ---------------------------------------------------------------------------

def _semaforo(valor, umbrales_mal, umbrales_ok, inverso=False):
    """Devuelve (color_hex, etiqueta) según umbrales."""
    if inverso:
        if valor > umbrales_mal:
            return "#C62828", "Crítico"
        if valor > umbrales_ok:
            return "#E65100", "Alerta"
        return "#2E7D32", "Favorable"
    else:
        if valor < umbrales_mal:
            return "#C62828", "Crítico"
        if valor < umbrales_ok:
            return "#E65100", "Alerta"
        return "#2E7D32", "Favorable"


def _bloque_gerencial(titulo, situacion, impacto, escenario, accion, color):
    """Render de un bloque de inteligencia gerencial."""
    st.html(f"""
    <div style="
        border-left: 5px solid {color};
        background: linear-gradient(to right, #f8f9fa, #ffffff);
        border-radius: 0 8px 8px 0;
        padding: 18px 20px;
        margin-bottom: 14px;
    ">
        <div style="font-size:16px; font-weight:700; color:#1B3A5C; margin-bottom:8px;">{titulo}</div>
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <tr>
                <td style="padding:4px 8px 4px 0; color:#555; width:130px; vertical-align:top;"><strong>Situación</strong></td>
                <td style="padding:4px 0; color:#222;">{situacion}</td>
            </tr>
            <tr>
                <td style="padding:4px 8px 4px 0; color:#555; vertical-align:top;"><strong>Impacto en largos</strong></td>
                <td style="padding:4px 0; color:#222;">{impacto}</td>
            </tr>
            <tr>
                <td style="padding:4px 8px 4px 0; color:#555; vertical-align:top;"><strong>Si sigue la tendencia</strong></td>
                <td style="padding:4px 0; color:#222;">{escenario}</td>
            </tr>
            <tr>
                <td style="padding:4px 8px 4px 0; color:#555; vertical-align:top;"><strong>Acción sugerida</strong></td>
                <td style="padding:4px 0; color:#222; font-weight:600;">{accion}</td>
            </tr>
        </table>
    </div>
    """)


# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------

macro_data = {}
steel_data = {}
demanda_df = pd.DataFrame()

if DATOS_REALES:
    try:
        macro_data = load_macroeconomic_indicators()
    except Exception:
        macro_data = {}
    try:
        steel_data = load_steel_market_data()
    except Exception:
        steel_data = {}

try:
    demanda_df = load_internal_demand_aceros_largos(12)
except Exception:
    demanda_df = pd.DataFrame()

# Extraer valores clave
construccion_info  = macro_data.get("construccion", {}) if isinstance(macro_data.get("construccion"), dict) else {}
inflacion_info     = macro_data.get("inflacion",    {}) if isinstance(macro_data.get("inflacion"),    dict) else {}
pib_info           = macro_data.get("pib",          {}) if isinstance(macro_data.get("pib"),          dict) else {}
usd_info           = macro_data.get("usd_mxn",      {}) if isinstance(macro_data.get("usd_mxn"),      dict) else {}
comercio_info      = steel_data.get("comercio_exterior", {}) if isinstance(steel_data, dict) else {}

v_construccion = construccion_info.get("valor_actual") or 0
t_construccion = construccion_info.get("tendencia")    or 0
v_inflacion    = inflacion_info.get("valor_actual")    or 0
t_inflacion    = inflacion_info.get("tendencia")       or 0
v_pib          = pib_info.get("valor_actual")          or 0
v_usd          = usd_info.get("valor_actual")          or 0
balanza        = comercio_info.get("balanza_comercial_ton") or comercio_info.get("balanza_comercial") or 0

has_demand = not demanda_df.empty and "peso_ton" in demanda_df.columns

# ---------------------------------------------------------------------------
# ENCABEZADO
# ---------------------------------------------------------------------------

st.title("Dashboard Ejecutivo — Aceros Largos")
st.markdown(
    "Resumen de las señales externas más importantes y su impacto directo en el negocio de aceros largos. "
    "**Sin tecnicismos. Directo a decisiones.**"
)

if not DATOS_REALES:
    st.warning("Sin conexión a BigQuery. Mostrando estructura sin valores.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 1: ¿QUÉ ESTÁ PASANDO HOY?
# ---------------------------------------------------------------------------

st.subheader("¿Qué está pasando hoy?")
st.caption("Los cuatro indicadores que determinan si el negocio crece o se contrae.")

c1, c2, c3, c4 = st.columns(4)

with c1:
    col_sem, etiqueta = _semaforo(v_construccion, -10, -3)
    val_str = f"{v_construccion:.1f}% YoY" if v_construccion else "N/D"
    delta_str = f"{t_construccion:+.1f} pp" if t_construccion else None
    st.metric("Construcción", val_str, delta_str,
              help="Variación anual de la actividad constructora. Principal driver de demanda de varilla y alambrón.")
    st.html(f"<div style='color:{col_sem}; font-size:13px; font-weight:700; text-align:center'>{etiqueta}</div>")

with c2:
    col_sem, etiqueta = _semaforo(v_inflacion, 6, 4, inverso=True)
    val_str = f"{v_inflacion:.2f}%" if v_inflacion else "N/D"
    delta_str = f"{t_inflacion:+.2f} pp" if t_inflacion else None
    st.metric("Inflación", val_str, delta_str, delta_color="inverse",
              help="INPC general. Si sube la inflación, suben los costos de producción y logística.")
    st.html(f"<div style='color:{col_sem}; font-size:13px; font-weight:700; text-align:center'>{etiqueta}</div>")

with c3:
    col_sem, etiqueta = _semaforo(v_pib, 0, 2)
    val_str = f"{v_pib:.1f}% YoY" if v_pib else "N/D"
    st.metric("PIB", val_str,
              help="Crecimiento económico general. Una economía sana implica mayor inversión en infraestructura y vivienda.")
    st.html(f"<div style='color:{col_sem}; font-size:13px; font-weight:700; text-align:center'>{etiqueta}</div>")

with c4:
    bal_k = balanza / 1000 if balanza else 0
    col_sem = "#C62828" if balanza < 0 else "#2E7D32"
    val_str = f"{bal_k:+,.0f}K ton" if balanza else "N/D"
    estado  = "Déficit" if balanza < 0 else "Superávit"
    st.metric("Balanza Acero Largos", val_str, estado,
              delta_color="inverse" if balanza < 0 else "normal",
              help="Exportaciones menos importaciones de aceros largos. Déficit significa más acero importado presionando precios locales.")
    st.html(f"<div style='color:{col_sem}; font-size:13px; font-weight:700; text-align:center'>{estado}</div>")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 2: INTELIGENCIA GERENCIAL — 1 BLOQUE POR SEÑAL
# ---------------------------------------------------------------------------

st.subheader("¿Cómo nos afecta cada señal?")
st.caption("Cada indicador traducido a impacto real en Aceros Largos y acción concreta.")

# -- CONSTRUCCIÓN --
if v_construccion:
    if v_construccion <= -10:
        sit = f"La construcción cae **{abs(v_construccion):.1f}%** anual — nivel de contracción severa."
        imp = "Demanda potencial de varilla y alambrón en caída directa. Proyectos en pausa o cancelados."
        esc = "Si la tendencia continúa otro trimestre: presión adicional sobre volumen y precio. Riesgo de sobrestock."
        acc = "Priorizar clientes con proyectos activos comprometidos. Revisar inventario de varilla antes de comprar materia prima. Explorar exportación."
        color = "#C62828"
    elif v_construccion <= -3:
        sit = f"La construcción cae **{abs(v_construccion):.1f}%** — debilitamiento moderado pero sostenido."
        imp = "Presión leve-moderada en volumen. Clientes del sector privado postergan pedidos."
        esc = "Sin recuperación de inversión pública o crédito hipotecario, puede profundizarse en 2-3 meses."
        acc = "Monitorear cartera de proyectos por zona. Segmentar clientes según exposición a obra privada vs. pública."
        color = "#E65100"
    elif v_construccion >= 3:
        sit = f"La construcción crece **{v_construccion:.1f}%** — señal positiva para la demanda."
        imp = "Aumento potencial de pedidos de varilla, alambrón y perfiles. Oportunidad de captura de volumen."
        esc = "Si el crecimiento es sostenido, podría presionar capacidad disponible en 1-2 meses."
        acc = "Asegurar disponibilidad comercial. Adelantar compras de palanquilla si hay holgura financiera."
        color = "#2E7D32"
    else:
        sit = f"Construcción en **{v_construccion:.1f}%** — zona neutral, sin señales fuertes."
        imp = "Demanda estable. Sin presión inmediata al alza ni a la baja."
        esc = "Monitorear permisos de edificación y obra pública como indicadores adelantados."
        acc = "Mantener inventarios operativos. No adelantar compras especulativas."
        color = "#1565C0"

    _bloque_gerencial("Construcción", sit, imp, esc, acc, color)

# -- INFLACIÓN --
if v_inflacion:
    if v_inflacion > 6:
        sit = f"Inflación en **{v_inflacion:.2f}%** — por encima del objetivo Banxico. Alta presión de costos."
        imp = "Energía, logística y materias auxiliares más caras. Márgenes comprimidos si precios no se ajustan."
        esc = "Banxico mantiene tasa alta, lo que encarece el crédito y reduce el financiamiento para proyectos de construcción."
        acc = "Revisar listas de precio. Confirmar cláusulas de ajuste en contratos de largo plazo."
        color = "#C62828"
    elif v_inflacion > 4:
        sit = f"Inflación en **{v_inflacion:.2f}%** — elevada pero en tendencia descendente."
        imp = "Costos controlados, pero siguen por encima de lo neutral. Margen bajo presión leve."
        esc = "Si baja a <4%, Banxico podría recortar tasa, lo que abarata el crédito y estimula la construcción."
        acc = "Vigilar evolución mensual. Preparar escenario de ajuste de precios si inflación sube 0.5 pp."
        color = "#E65100"
    else:
        sit = f"Inflación en **{v_inflacion:.2f}%** — controlada, cercana al objetivo."
        imp = "Costos de producción estables. Potencial para recorte de tasa y mayor crédito hipotecario."
        esc = "Ambiente favorable para reactivación de obra si se suman otros factores."
        acc = "Sostener precios actuales. Preparar propuesta de financiamiento a desarrolladores."
        color = "#2E7D32"

    _bloque_gerencial("Inflación (INPC)", sit, imp, esc, acc, color)

# -- PIB --
if v_pib:
    if v_pib < 0:
        sit = f"El PIB cae **{abs(v_pib):.1f}%** — la economía en contracción."
        imp = "Caída generalizada de inversión pública y privada. Demanda de acero estructuralmente débil."
        esc = "Recesión prolongada impacta empleo, consumo y cartera de clientes."
        acc = "Posición defensiva: control de crédito, reducción de plazos, foco en clientes pagadores."
        color = "#C62828"
    elif v_pib < 2:
        sit = f"El PIB crece **{v_pib:.1f}%** — crecimiento bajo, sin impulso fuerte."
        imp = "Inversión insuficiente para activar la construcción a nivel que genere demanda relevante de acero."
        esc = "Sin estímulo fiscal o crédito, la demanda de largos se mantiene plana o a la baja."
        acc = "Diversificar hacia sectores menos dependientes del ciclo económico."
        color = "#E65100"
    else:
        sit = f"El PIB crece **{v_pib:.1f}%** — expansión moderada a sana."
        imp = "Mayor actividad económica general implica más proyectos de infraestructura y vivienda."
        esc = "Si el crecimiento se mantiene, se traduce en mayor demanda de aceros largos en 2-3 trimestres."
        acc = "Monitorear licitaciones de obra pública. Contactar desarrolladoras activas."
        color = "#2E7D32"

    _bloque_gerencial("PIB Nacional", sit, imp, esc, acc, color)

# -- COMERCIO EXTERIOR --
if balanza:
    if balanza < -500_000:
        sit = f"Balanza de aceros largos: **déficit de {abs(balanza)/1000:,.0f}K ton**."
        imp = "México importa significativamente más acero largo del que exporta. Competencia importada presiona precio local."
        esc = "Si los aranceles a China no se aplican o se evaden, el déficit puede crecer y comprimir márgenes."
        acc = "Revisar política de precios frente a importaciones. Identificar ventajas de servicio vs. precio chino."
        color = "#C62828"
    elif balanza < 0:
        sit = f"Balanza negativa: **{balanza/1000:,.0f}K ton** de déficit."
        imp = "Hay presión importadora moderada. El acero externo compite en ciertos productos y regiones."
        esc = "Sin medidas arancelarias adicionales, la penetración importada puede crecer."
        acc = "Fortalecer diferenciación por servicio: rapidez de entrega, crédito, soporte técnico."
        color = "#E65100"
    else:
        sit = f"Balanza positiva: **superávit de {balanza/1000:,.0f}K ton**."
        imp = "México exporta más de lo que importa. Mercado interno competitivo."
        esc = "Situación favorable; monitorear si el superávit se sostiene o si cambia por nuevos aranceles."
        acc = "Explorar oportunidades de exportación a Centroamérica y EE. UU. donde sea viable."
        color = "#2E7D32"

    _bloque_gerencial("Comercio Exterior — Aceros Largos", sit, imp, esc, acc, color)

if not any([v_construccion, v_inflacion, v_pib, balanza]):
    st.info("Sin datos reales disponibles. Conectar BigQuery para obtener la lectura gerencial automática.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 3: SEMÁFORO GENERAL DEL NEGOCIO
# ---------------------------------------------------------------------------

st.subheader("Semáforo del Negocio — Aceros Largos")
st.caption("Síntesis de todas las señales en una sola lectura ejecutiva.")

señales_activas = []
if v_construccion:  señales_activas.append(v_construccion)

if señales_activas:
    promedio_tension = sum(1 for v in señales_activas if v < -5) + \
                      sum(1 for v in señales_activas if v < 0) * 0.5
    nivel_riesgo = promedio_tension / max(len(señales_activas), 1)

    if nivel_riesgo >= 0.7 or (v_construccion and v_construccion < -8):
        nivel = "ALERTA — Condiciones adversas"
        descripcion = "La mayoría de las señales apuntan a contracción. El negocio enfrenta presión en demanda, costos y competencia simultáneamente."
        bg = "#FFEBEE"
        border = "#C62828"
        recomendacion_global = "Posición defensiva: controlar inventario, cuidar cartera, priorizar clientes con mayor certidumbre de pago."
    elif nivel_riesgo >= 0.3 or (v_construccion and v_construccion < -3):
        nivel = "PRECAUCIÓN — Señales mixtas"
        descripcion = "Algunas señales son negativas pero hay factores que amortiguan. Vigilar evolución en las próximas 4-6 semanas."
        bg = "#FFF3E0"
        border = "#E65100"
        recomendacion_global = "Monitoreo activo. No adelantar compras grandes. Mantener flexibilidad operativa."
    else:
        nivel = "FAVORABLE — Condiciones positivas"
        descripcion = "Las señales apuntan a estabilidad o crecimiento moderado. Oportunidad para capturar mercado."
        bg = "#E8F5E9"
        border = "#2E7D32"
        recomendacion_global = "Asegurar disponibilidad. Activar propuestas comerciales. Preparar capacidad para el repunte."

    st.html(f"""
    <div style="
        background: {bg};
        border: 2px solid {border};
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0 20px 0;
    ">
        <div style="font-size:20px; font-weight:800; color:#1B3A5C; margin-bottom:10px;">{nivel}</div>
        <p style="font-size:14px; color:#333; margin:0 0 10px 0;">{descripcion}</p>
        <p style="font-size:14px; color:#1B3A5C; font-weight:700; margin:0;">
            ▶ {recomendacion_global}
        </p>
    </div>
    """)

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 4: CONSTRUCCIÓN — EVOLUCIÓN REAL
# ---------------------------------------------------------------------------

st.subheader("Evolución de la Construcción (señal principal)")
st.caption("La construcción explica ~70% de la demanda de varilla y alambrón. Leer esta gráfica es leer el futuro cercano de nuestra demanda.")

construccion_serie = pd.DataFrame(construccion_info.get("serie_historica", []))
if not construccion_serie.empty and "fecha" in construccion_serie.columns:
    construccion_serie["fecha"] = pd.to_datetime(construccion_serie["fecha"], errors="coerce")
    construccion_serie = construccion_serie.dropna(subset=["fecha"])
    construccion_serie = construccion_serie.sort_values("fecha").tail(24).copy()
    construccion_serie["valor"] = pd.to_numeric(construccion_serie["valor"], errors="coerce")
    construccion_serie = construccion_serie.dropna(subset=["valor"])

    if not construccion_serie.empty:
        x = construccion_serie["fecha"].dt.strftime("%b %y").tolist()
        y = construccion_serie["valor"].tolist()

        # Dos vistas en paralelo: barras de variación + waterfall de acumulación
        col_bar, col_wf = st.columns(2)

        with col_bar:
            fig_bar = chart_barras_variacion(
                x=x, y=y,
                titulo="Variación % Anual — cada barra es un mes",
                yaxis_title="% YoY",
                umbral_critico=-10,
                umbral_alerta=-3,
                height=310,
                anotacion_leyenda="Crítico < -10% | Alerta -10% a -3% | Precaución -3% a 0% | Favorable > 0%",
            )
            st.plotly_chart(fig_bar, width="stretch")

        with col_wf:
            # Waterfall de los últimos 12 meses: se ve cómo se acumula la caída o recuperación
            x_wf = x[-12:]
            y_wf = y[-12:]
            fig_wf = chart_waterfall(
                etiquetas=x_wf, valores=y_wf,
                titulo="Cascada — cómo se va acumulando la tendencia",
                yaxis_title="% pp acumulados",
                height=310,
            )
            st.plotly_chart(fig_wf, width="stretch")

        # Leyenda ejecutiva debajo del gráfico
        tendencia_ultimos = [v for v in y[-3:] if v is not None]
        if tendencia_ultimos:
            promedio_reciente = sum(tendencia_ultimos) / len(tendencia_ultimos)
            if promedio_reciente < -8:
                st.warning("**Lectura crítica**: La construcción lleva varios meses en caída severa. La presión sobre demanda de largos es estructural, no puntual.")
            elif promedio_reciente < -3:
                st.warning("**Lectura**: La construcción sigue en terreno negativo. Sin reversa en política de crédito o gasto público, la demanda de largos permanecerá bajo presión.")
            elif promedio_reciente > 0:
                st.success("**Lectura**: La construcción muestra recuperación. Es señal temprana de mayor demanda de varilla y alambrón en las próximas semanas.")
            else:
                st.info("**Lectura**: Construcción cerca de cero. Mercado lateral sin impulso claro.")
    else:
        st.info("Sin datos de construcción disponibles en el período seleccionado.")
else:
    st.info("No hay serie histórica de construcción disponible. Verificar conexión a BigQuery.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 6: PRÓXIMOS PASOS RECOMENDADOS
# ---------------------------------------------------------------------------

st.subheader("¿Qué debería hacer esta semana?")

acciones = []

if v_construccion and v_construccion < -5:
    acciones.append(("Alta prioridad", "Revisar el pipeline de proyectos de clientes constructoras. Identificar cuáles se cancelaron o pospusieron."))
    acciones.append(("Alta prioridad", "Evaluar inventario de varilla corrugada y alambrón. No comprar materia prima extra hasta ver señal de recuperación."))

if v_inflacion and v_inflacion > 5:
    acciones.append(("Media prioridad", "Revisar lista de precios. Asegurar que el margen no se esté erosionando por costos energéticos y logística."))

if balanza and balanza < -200_000:
    acciones.append(("Media prioridad", "Analizar precios de importación de varilla china. Confirmar que somos competitivos en calidad/servicio donde el precio difiere."))

if v_pib and v_pib > 2:
    acciones.append(("Oportunidad", "PIB en zona de crecimiento. Buscar licitaciones de obra pública o proyectos de infraestructura."))



if not acciones:
    acciones.append(("Seguimiento", "Sin alertas críticas activas. Continuar monitoreo semanal de indicadores."))

for prioridad, texto in acciones:
    color_fila = "#FFEBEE" if "Alta" in prioridad else "#FFF3E0" if "Media" in prioridad else "#E8F5E9" if "Oportunidad" in prioridad else "#E3F2FD"
    st.html(f"""
    <div style="background:{color_fila}; padding:12px 16px; border-radius:6px; margin-bottom:8px;">
        <strong>{prioridad}:</strong> {texto}
    </div>
    """)

st.divider()
st.caption(f"Datos: INEGI · MOCAMX · BigQuery TYASA · Actualizado: {get_last_update() if DATOS_REALES else 'N/D'}")
