"""
pages/aceros_largos/02_macroeconomia.py — Análisis Macroeconómico Aceros Largos
Vista gerencial: cada indicador explicado en términos de impacto y acción.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta

from aceros_largos.charts_gerencial import (
    chart_barras_variacion,
    chart_area_tendencia,
    chart_waterfall,
    chart_gauge_simple,
)
from aceros_largos.loaders import (
    load_macroeconomic_indicators,
    get_last_update,
    get_data_sources,
)

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _tarjeta_indicador(titulo, valor_str, tendencia_str, situacion, impacto, accion, color, ayuda=""):
    """Tarjeta gerencial completa para un indicador."""
    st.html(f"""
    <div style="
        border: 1px solid #e0e0e0;
        border-left: 6px solid {color};
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
        background: #fafafa;
    ">
        <div style="font-size:17px; font-weight:700; color:#1B3A5C; margin-bottom:4px;">{titulo}</div>
        <div style="display:flex; gap:24px; margin-bottom:10px;">
            <div>
                <span style="font-size:26px; font-weight:800; color:{color};">{valor_str}</span>
                <span style="font-size:13px; color:#555; margin-left:8px;">{tendencia_str}</span>
            </div>
        </div>
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <tr>
                <td style="padding:3px 8px 3px 0; color:#555; width:110px; vertical-align:top;"><strong>Situación</strong></td>
                <td style="padding:3px 0; color:#222;">{situacion}</td>
            </tr>
            <tr>
                <td style="padding:3px 8px 3px 0; color:#555; vertical-align:top;"><strong>Impacto en largos</strong></td>
                <td style="padding:3px 0; color:#222;">{impacto}</td>
            </tr>
            <tr>
                <td style="padding:3px 8px 3px 0; color:#555; vertical-align:top;"><strong>Qué hacer</strong></td>
                <td style="padding:3px 0; color:#1B3A5C; font-weight:600;">{accion}</td>
            </tr>
        </table>
        {f'<div style="font-size:11px; color:#aaa; margin-top:8px;">{ayuda}</div>' if ayuda else ''}
    </div>
    """)


def _prep_serie(info, periodo_meses):
    """Prepara x, y desde serie_historica."""
    raw = info.get("serie_historica", [])
    if not raw:
        return [], []
    df = pd.DataFrame(raw)
    col_fecha = "fecha" if "fecha" in df.columns else ("periodo" if "periodo" in df.columns else None)
    if col_fecha is None:
        return [], []
    df["_fecha"] = pd.to_datetime(df[col_fecha], errors="coerce")
    df["valor"]  = pd.to_numeric(df.get("valor", pd.Series()), errors="coerce")
    df = df.dropna(subset=["_fecha", "valor"])
    cutoff = datetime.now() - timedelta(days=periodo_meses * 30)
    df = df[df["_fecha"] >= cutoff].sort_values("_fecha")
    x = df["_fecha"].dt.strftime("%b %y").tolist()
    y = df["valor"].tolist()
    return x, y


# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------

st.title("Análisis Macroeconómico — Aceros Largos")
st.markdown(
    "Cada indicador explicado en términos de **qué está pasando**, **cómo afecta a Aceros Largos** y **qué acción conviene tomar**. "
    "Sin fórmulas. Sin tecnicismos."
)

with st.sidebar:
    st.header("Controles")
    periodo_options = {"Últimos 6 meses": 6, "Último año": 12, "Últimos 2 años": 24}
    periodo_label = st.selectbox("Período de análisis", list(periodo_options.keys()), index=1)
    periodo_meses = periodo_options[periodo_label]
    st.caption(f"Fuentes: {', '.join(get_data_sources()[:2])}")
    st.caption(f"Actualizado: {get_last_update()}")

with st.spinner("Cargando indicadores…"):
    macro_data = load_macroeconomic_indicators()

def _safe(key):
    v = macro_data.get(key, {})
    return v if isinstance(v, dict) else {}

construccion = _safe("construccion")
inflacion    = _safe("inflacion")
pib          = _safe("pib")
usd_mxn      = _safe("usd_mxn")



st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 1: CONSTRUCCIÓN — el indicador que más importa
# ---------------------------------------------------------------------------

st.subheader("1. Construcción — el driver principal")
st.caption("La construcción explica ~70% de la demanda de varilla y alambrón. Es el indicador que más rápido impacta tus ventas.")

v_con = construccion.get("valor_actual") or 0
t_con = construccion.get("tendencia") or 0

if v_con:
    if v_con <= -10:
        sit = "La construcción cae más de 10% anual. Contracción severa."
        imp = "Proyectos cancelados o pausados. Demanda de varilla y alambrón en caída directa."
        acc = "Reducir exposición a clientes constructores con proyectos no comprometidos. Revisar inventarios."
        color = "#C62828"
    elif v_con < -3:
        sit = f"Baja {abs(v_con):.1f}% anual. Debilitamiento sostenido."
        imp = "Clientes del sector privado postergan pedidos. Presión moderada en volumen."
        acc = "Segmentar cartera: priorizar clientes con obra activa. No adelantar compras de materia prima."
        color = "#E65100"
    elif v_con < 0:
        sit = f"Caída leve de {abs(v_con):.1f}% anual. Mercado lateral."
        imp = "Sin crecimiento de demanda. Riesgo de que profundice si no hay estímulo."
        acc = "Mantener posición. Vigilar permisos de edificación como señal adelantada."
        color = "#FDD835"
    else:
        sit = f"Crece {v_con:.1f}% anual. Señal positiva."
        imp = "Mayor actividad en obra implica mayor demanda potencial de varilla y alambrón."
        acc = "Asegurar disponibilidad de producto. Activar propuestas comerciales con desarrolladores."
        color = "#2E7D32"

    _tarjeta_indicador(
        titulo=f"Actividad de la Construcción: {v_con:.1f}% YoY",
        valor_str=f"{v_con:.1f}%",
        tendencia_str=f"{t_con:+.1f} pp vs mes anterior",
        situacion=sit,
        impacto=imp,
        accion=acc,
        color=color,
        ayuda="Fuente: INEGI — Encuesta Nacional de Empresas Constructoras"
    )

    col_g, col_i = st.columns([2, 1])
    with col_g:
        x_con, y_con = _prep_serie(construccion, periodo_meses)
        if x_con:
            col_bar_c, col_wf_c = st.columns(2)
            with col_bar_c:
                fig_bar_c = chart_barras_variacion(
                    x=x_con, y=y_con,
                    titulo="Variación mensual % YoY",
                    height=270,
                    umbral_critico=-10, umbral_alerta=-3,
                    anotacion_leyenda="Crítico <-10% | Alerta -10 a -3% | Precaución -3 a 0% | Favorable >0%",
                )
                st.plotly_chart(fig_bar_c, width="stretch")
            with col_wf_c:
                fig_wf_c = chart_waterfall(
                    etiquetas=x_con[-12:], valores=y_con[-12:],
                    titulo="Cascada de tendencia (12M)",
                    height=270,
                )
                st.plotly_chart(fig_wf_c, width="stretch")
        else:
            st.info("Sin serie histórica disponible.")

    with col_i:
        st.markdown("**¿Qué significa cada nivel?**")
        st.markdown("""
        | Rango | Señal |
        |-------|-------|
        | > 0% | Demanda crece |
        | -3% a 0% | Mercado lateral |
        | -10% a -3% | Debilitamiento |
        | < -10% | Contracción severa |
        """)
        if t_con < -2:
            st.warning(f"La tendencia sigue cayendo ({t_con:+.1f} pp). Riesgo de profundizar.")
        elif t_con > 2:
            st.success(f"Tendencia mejorando ({t_con:+.1f} pp). Señal de recuperación.")
        else:
            st.info("Tendencia estable. Sin cambio de dirección claro.")
else:
    st.info("Sin datos de construcción disponibles.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 2: INFLACIÓN
# ---------------------------------------------------------------------------

st.subheader("2. Inflación (INPC) — ¿cuánto nos cuesta producir?")
st.caption("La inflación impacta directamente el costo de energía, logística y materias auxiliares.")

v_inf = inflacion.get("valor_actual") or 0
t_inf = inflacion.get("tendencia") or 0

if v_inf:
    if v_inf > 6:
        sit = f"Inflación en {v_inf:.2f}% — muy por encima del objetivo de 3%."
        imp = "Costos energéticos, de transporte y materias auxiliares al alza. Márgenes comprimidos."
        acc = "Revisar lista de precios urgente. Validar cláusulas de ajuste en contratos de largo plazo."
        color = "#C62828"
    elif v_inf > 4:
        sit = f"Inflación en {v_inf:.2f}% — elevada pero bajando gradualmente."
        imp = "Costos más altos que lo neutral. Margen bajo presión leve-moderada."
        acc = "Monitorear mensualmente. Preparar propuesta de ajuste si sube 0.5 pp en próximos 2 meses."
        color = "#E65100"
    elif v_inf > 3:
        sit = f"Inflación en {v_inf:.2f}% — cerca del objetivo, controlada."
        imp = "Costos estables. Banxico en modo de relajación, lo que mejora el crédito para construcción."
        acc = "Mantener precios. Anticipar recuperación de demanda hipotecaria si la tasa baja."
        color = "#FDD835"
    else:
        sit = f"Inflación en {v_inf:.2f}% — bajo control, favorable."
        imp = "Costos estables. Ambiente positivo para expansión de inversión y construcción."
        acc = "Aprovechar ambiente de costos bajos para fortalecer márgenes."
        color = "#2E7D32"

    col_t, col_g = st.columns([1, 2])
    with col_t:
        _tarjeta_indicador(
            titulo=f"INPC: {v_inf:.2f}%",
            valor_str=f"{v_inf:.2f}%",
            tendencia_str=f"{t_inf:+.2f} pp vs mes anterior",
            situacion=sit,
            impacto=imp,
            accion=acc,
            color=color,
            ayuda="Fuente: INEGI — Índice Nacional de Precios al Consumidor"
        )
        # Gauge puntual de inflación
        fig_gauge = chart_gauge_simple(
            valor=v_inf, titulo="INPC actual",
            rango_min=0, rango_max=12,
            umbral_rojo=6, umbral_amarillo=4,
            unidad="%"
        )
        st.plotly_chart(fig_gauge, width="stretch")
    with col_g:
        # La tabla INPC solo guarda el ÍNDICE base (80-170), no la variación %.
        # Calculamos YoY mes a mes: (índice_hoy / índice_hace_12_meses - 1) * 100
        from aceros_largos.loaders_new_data import load_inegi_inpc_data
        df_inpc_raw = load_inegi_inpc_data(36)  # 3 años para tener 12M de base
        x_inf_bar, y_inf_bar = [], []
        if not df_inpc_raw.empty and "valor" in df_inpc_raw.columns and "fecha" in df_inpc_raw.columns:
            df_inpc_raw["valor"] = pd.to_numeric(df_inpc_raw["valor"], errors="coerce")
            df_inpc_raw["fecha"] = pd.to_datetime(df_inpc_raw["fecha"], errors="coerce")
            df_inpc_raw = df_inpc_raw.dropna(subset=["fecha", "valor"])
            # Quedarse con una sola serie (la más frecuente para evitar mezcla)
            if "concepto" in df_inpc_raw.columns:
                concepto_top = df_inpc_raw["concepto"].value_counts().index[0]
                df_inpc_raw = df_inpc_raw[df_inpc_raw["concepto"] == concepto_top]
            df_inpc_raw = df_inpc_raw.sort_values("fecha").drop_duplicates(subset=["fecha"])
            # Calcular variación YoY: (índice_t / índice_{t-12}) - 1
            df_inpc_raw = df_inpc_raw.set_index("fecha").sort_index()
            df_inpc_raw["yoy"] = (df_inpc_raw["valor"] / df_inpc_raw["valor"].shift(12) - 1) * 100
            df_yoy = df_inpc_raw.dropna(subset=["yoy"]).reset_index()
            # Filtrar período del sidebar
            cutoff = datetime.now() - timedelta(days=max(periodo_meses, 18) * 30)
            df_yoy = df_yoy[df_yoy["fecha"] >= cutoff]
            if not df_yoy.empty:
                x_inf_bar = df_yoy["fecha"].dt.strftime("%b %y").tolist()
                y_inf_bar = df_yoy["yoy"].round(2).tolist()

        if x_inf_bar:
            fig_inf = chart_barras_variacion(
                x=x_inf_bar, y=y_inf_bar,
                titulo="Inflación INPC — variación % anual mensual",
                yaxis_title="% YoY",
                umbral_critico=6, umbral_alerta=4,
                height=290,
                mostrar_labels=True,
                anotacion_leyenda="Favorable < 4% | Alerta 4–6% | Crítico > 6%",
            )
            # Para inflación: rojo es ALTO (malo), verde es BAJO (bueno); invertir semáforo
            new_colors = [
                "#C62828" if v > 6 else "#E65100" if v > 4 else "#2E7D32"
                for v in y_inf_bar
            ]
            fig_inf.update_traces(marker_color=new_colors)
            st.plotly_chart(fig_inf, width="stretch")
            ultima_inf = df_yoy["fecha"].max()
            st.caption(f"Dato más reciente: **{ultima_inf.strftime('%B %Y')}** | Calculado como variación del índice INPC vs mismo mes del año anterior.")
        else:
            st.info("Sin serie histórica de INPC disponible.")
else:
    st.info("Sin datos de inflación disponibles.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 3: PIB
# ---------------------------------------------------------------------------

st.subheader("3. PIB — ¿crece o se contrae la economía?")
st.caption("El PIB es el termómetro general. Una economía que crece invierte más en infraestructura y vivienda.")

v_pib = pib.get("valor_actual") or 0
t_pib = pib.get("tendencia") or 0

if v_pib:
    if v_pib < 0:
        sit = f"El PIB cae {abs(v_pib):.1f}% — la economía en recesión."
        imp = "Inversión pública y privada contraídas. Demanda de acero débil en todos los segmentos."
        acc = "Posición defensiva: controlar crédito, reducir plazos, priorizar clientes con pago al contado o plazos cortos."
        color = "#C62828"
    elif v_pib < 1.5:
        sit = f"PIB crece solo {v_pib:.1f}% — economía estancada."
        imp = "Sin impulso para nueva inversión. Demanda de aceros largos sin crecimiento orgánico."
        acc = "Diversificar hacia clientes de obra pública o infraestructura que no dependan del PIB privado."
        color = "#E65100"
    elif v_pib < 3:
        sit = f"PIB crece {v_pib:.1f}% — crecimiento moderado."
        imp = "Hay actividad económica suficiente para sostener proyectos de construcción en marcha."
        acc = "Mantener relaciones comerciales activas. Identificar proyectos nuevos en pipeline."
        color = "#FDD835"
    else:
        sit = f"PIB crece {v_pib:.1f}% — expansión sólida."
        imp = "Mayor inversión genera más proyectos de vivienda e infraestructura y más demanda de acero."
        acc = "Capturar oportunidades. Evaluar si la capacidad de producción puede responder al crecimiento."
        color = "#2E7D32"

    col_t, col_g = st.columns([1, 2])
    with col_t:
        _tarjeta_indicador(
            titulo=f"PIB: {v_pib:.1f}% YoY",
            valor_str=f"{v_pib:.1f}%",
            tendencia_str=f"{t_pib:+.1f} pp vs trimestre anterior",
            situacion=sit,
            impacto=imp,
            accion=acc,
            color=color,
            ayuda="Fuente: INEGI — Cuentas Nacionales (trimestral)"
        )
    with col_g:
        # La tabla PIB trae múltiples series mezcladas.
        # La serie correcta del PIB total es: "Variación porcentual anual|B.1bP---Producto interno bruto"
        x_pib, y_pib = [], []
        raw_pib = pib.get("serie_historica", [])
        if raw_pib:
            df_pib_raw = pd.DataFrame(raw_pib)
            df_pib_raw["valor"] = pd.to_numeric(df_pib_raw.get("valor", pd.Series()), errors="coerce")

            df_pib_filtrado = pd.DataFrame()
            if "descripcion" in df_pib_raw.columns:
                # Prioridad 1: serie exacta del PIB total nacional (variación % anual)
                mask_pib_total = df_pib_raw["descripcion"].str.contains(
                    r"B\.1bP|PIB total|Producto interno bruto", case=False, na=False, regex=True
                ) & df_pib_raw["descripcion"].str.contains(
                    r"[Vv]ariaci[oó]n porcentual anual", case=False, na=False, regex=True
                )
                if mask_pib_total.any():
                    df_pib_filtrado = df_pib_raw[mask_pib_total].copy()

            # Fallback: cualquier variación % con rango razonable de PIB (-15% a 20%)
            if df_pib_filtrado.empty:
                mask_rango = df_pib_raw["valor"].between(-15, 20)
                if "descripcion" in df_pib_raw.columns:
                    mask_rango &= df_pib_raw["descripcion"].str.contains(
                        r"[Vv]ariaci[oó]n porcentual anual", case=False, na=False, regex=True
                    )
                df_pib_filtrado = df_pib_raw[mask_rango].copy()
                # Quedarse con una sola descripción (la más frecuente)
                if not df_pib_filtrado.empty and "descripcion" in df_pib_filtrado.columns:
                    desc_top = df_pib_filtrado["descripcion"].value_counts().index[0]
                    df_pib_filtrado = df_pib_filtrado[df_pib_filtrado["descripcion"] == desc_top]

            if not df_pib_filtrado.empty:
                col_fecha = "fecha" if "fecha" in df_pib_filtrado.columns else (
                    "periodo" if "periodo" in df_pib_filtrado.columns else None)
                if col_fecha:
                    df_pib_filtrado["_fecha"] = pd.to_datetime(df_pib_filtrado[col_fecha], errors="coerce")
                    # PIB es trimestral: siempre mostrar mínimo 3 años para ver tendencia real
                    # ignorar el filtro del sidebar para esta serie
                    df_pib_filtrado = df_pib_filtrado.dropna(subset=["_fecha", "valor"])
                    df_pib_filtrado = df_pib_filtrado.sort_values("_fecha").drop_duplicates(subset=["_fecha"])
                    # Mostrar últimos 16 trimestres (4 años) o todos si hay menos
                    df_pib_filtrado = df_pib_filtrado.tail(16)
                    x_pib = df_pib_filtrado["_fecha"].dt.strftime("Q%q\n%Y").tolist()
                    y_pib = df_pib_filtrado["valor"].tolist()

        if x_pib and len(x_pib) >= 2:
            fig_pib = chart_barras_variacion(
                x=x_pib, y=y_pib,
                titulo="PIB México — variación % anual por trimestre (últimos 4 años)",
                yaxis_title="% Variación Anual",
                umbral_critico=0, umbral_alerta=1.5,
                height=310,
                mostrar_labels=True,
                anotacion_leyenda="Crítico < 0% | Alerta 0–1.5% | Favorable > 1.5%",
            )
            st.plotly_chart(fig_pib, width="stretch")
            # Nota ejecutiva sobre el rezago
            ultima_fecha_pib = df_pib_filtrado["_fecha"].max() if "df_pib_filtrado" in dir() and not df_pib_filtrado.empty else None
            if ultima_fecha_pib is not None:
                trimestre_str = f"Q{((ultima_fecha_pib.month - 1) // 3) + 1} {ultima_fecha_pib.year}"
                st.caption(
                    f"Dato más reciente disponible: **{trimestre_str}**. "
                    "INEGI publica el PIB con ~2 meses de rezago tras cerrar el trimestre. "
                    "El dato de Q1 2026 (enero–marzo) se publicará aproximadamente en junio 2026."
                )
        elif v_pib:
            # Sin serie histórica filtrable: mostrar solo el KPI actual con contexto visual
            st.html(f"""
            <div style="
                background: {'#E8F5E9' if v_pib >= 0 else '#FFEBEE'};
                border: 2px solid {'#2E7D32' if v_pib >= 0 else '#C62828'};
                border-radius: 10px; padding: 24px; text-align: center; margin-top: 8px;
            ">
                <div style="font-size: 13px; color: #555; margin-bottom: 8px;">
                    PIB — variación anual más reciente
                </div>
                <div style="font-size: 52px; font-weight: 800; color: {'#2E7D32' if v_pib >= 0 else '#C62828'};">
                    {v_pib:+.1f}%
                </div>
                <div style="font-size: 13px; color: #777; margin-top: 8px;">
                    {'Economía creciendo' if v_pib >= 2 else 'Crecimiento débil' if v_pib >= 0 else 'Economía en contracción'}
                </div>
            </div>
            """)
            st.caption("Serie histórica no disponible o con formato no compatible para graficar.")
        else:
            st.info("Sin datos de PIB disponibles.")
else:
    st.info("Sin datos de PIB disponibles.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 4: USD/MXN
# ---------------------------------------------------------------------------

st.subheader("4. Tipo de Cambio USD/MXN — ¿cuánto cuesta el acero importado?")
st.caption("El peso débil encarece las importaciones de acero; el peso fuerte las abarata y aumenta la competencia.")

v_usd = usd_mxn.get("valor_actual") or 0
t_usd = usd_mxn.get("tendencia") or 0

# Protección adicional de UI: si la fuente trae un valor fuera de rango, no
# mostrarlo. USD/MXN real debe estar en pesos por dólar, no índices u otras
# variables financieras.
if v_usd and not (10 <= float(v_usd) <= 30):
    v_usd = 0
    t_usd = 0

if v_usd:
    if v_usd > 20:
        sit = f"USD/MXN en ${v_usd:.2f} — peso débil."
        imp = "El acero importado es más caro en pesos, lo que da protección natural para producción nacional. Pero si usamos insumos importados (chatarra, ferroaleaciones), nuestros costos también suben."
        acc = "Verificar si el diferencial de precio compensa la competencia importada. Comunicar ventaja de acero nacional."
        color = "#2E7D32"
    elif v_usd > 17.5:
        sit = f"USD/MXN en ${v_usd:.2f} — tipo de cambio neutral."
        imp = "Importaciones competitivas. Sin ventaja clara ni para la producción nacional ni para el importador."
        acc = "Monitorear movimientos del peso. Analizar exposición a insumos dolarizados."
        color = "#FDD835"
    else:
        sit = f"USD/MXN en ${v_usd:.2f} — peso fuerte."
        imp = "El acero importado es barato en pesos, lo que genera mayor competencia de China y otros exportadores. Riesgo de pérdida de mercado."
        acc = "Reforzar diferenciación por servicio: entrega inmediata, crédito, soporte técnico. No competir solo en precio."
        color = "#C62828"

    col_t, col_g = st.columns([1, 2])
    with col_t:
        _tarjeta_indicador(
            titulo=f"USD/MXN: ${v_usd:.2f}",
            valor_str=f"${v_usd:.2f}",
            tendencia_str=f"{t_usd:+.2f}% vs mes anterior",
            situacion=sit,
            impacto=imp,
            accion=acc,
            color=color,
            ayuda="Fuente: Banco de México — tipo de cambio FIX"
        )
    with col_g:
        # USD/MXN: ticker MXN=X en gold_variables_mercado, datos diarios.
        # Agregamos a mensual (promedio) para suavizar y ver tendencia clara.
        from aceros_largos.loaders_new_data import load_macro_market_series
        df_fx_raw = load_macro_market_series(max(periodo_meses, 18))
        x_usd_bar, y_usd_bar = [], []
        if not df_fx_raw.empty:
            df_fx = df_fx_raw[df_fx_raw["serie"] == "usd_mxn"].copy()
            if df_fx.empty and "ticker" in df_fx_raw.columns:
                df_fx = df_fx_raw[df_fx_raw["ticker"] == "MXN=X"].copy()
            if not df_fx.empty:
                df_fx["valor"] = pd.to_numeric(df_fx["valor"], errors="coerce")
                df_fx["fecha"] = pd.to_datetime(df_fx["fecha"], errors="coerce")
                df_fx = df_fx.dropna(subset=["fecha", "valor"])
                # Filtrar rango razonable (16-25 pesos por USD)
                df_fx = df_fx[df_fx["valor"].between(16, 25)]
                # Agregar a promedio mensual
                df_fx["mes"] = df_fx["fecha"].dt.to_period("M")
                df_mensual = df_fx.groupby("mes")["valor"].mean().reset_index()
                df_mensual["fecha"] = df_mensual["mes"].dt.to_timestamp()
                cutoff = datetime.now() - timedelta(days=periodo_meses * 30)
                df_mensual = df_mensual[df_mensual["fecha"] >= cutoff].sort_values("fecha")
                if not df_mensual.empty:
                    x_usd_bar = df_mensual["fecha"].dt.strftime("%b %y").tolist()
                    y_usd_bar = df_mensual["valor"].round(2).tolist()

        if x_usd_bar:
            # Barras con color: rojo = peso fuerte (< 17.5, más competencia),
            # verde = peso débil (> 20, protección)
            bar_colors_fx = [
                "#2E7D32" if v > 20 else "#E65100" if v > 17.5 else "#C62828"
                for v in y_usd_bar
            ]
            import plotly.graph_objects as go_local
            fig_fx = go_local.Figure()
            fig_fx.add_trace(go_local.Bar(
                x=x_usd_bar, y=y_usd_bar,
                marker_color=bar_colors_fx,
                marker_line_width=0,
                text=[f"${v:.2f}" for v in y_usd_bar],
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate="%{x}: <b>$%{y:.2f}</b><extra></extra>",
            ))
            # Línea de promedio
            prom_fx = sum(y_usd_bar) / len(y_usd_bar)
            fig_fx.add_hline(y=prom_fx, line_dash="dot", line_color="#757575",
                             opacity=0.7,
                             annotation_text=f"Promedio: ${prom_fx:.2f}",
                             annotation_font_color="#757575",
                             annotation_position="bottom right")
            fig_fx.add_hline(y=17.5, line_dash="dot", line_color="#E65100",
                             opacity=0.5, annotation_text="$17.5 neutral",
                             annotation_position="top right")
            fig_fx.add_hline(y=20, line_dash="dot", line_color="#2E7D32",
                             opacity=0.5, annotation_text="$20 peso débil",
                             annotation_position="top right")
            fig_fx.update_layout(
                title="USD/MXN — promedio mensual (pesos por dólar)",
                height=290, showlegend=False,
                yaxis=dict(title="Pesos por USD", range=[15, 23], gridcolor="#f0f0f0"),
                xaxis=dict(tickangle=-30 if len(x_usd_bar) > 10 else 0, tickfont=dict(size=10)),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                margin=dict(t=50, b=50, l=55, r=80),
            )
            st.plotly_chart(fig_fx, width="stretch")
            st.caption(
                "Peso débil > $20: importaciones más caras, protección para producción nacional. "
                "Peso fuerte < $17.5: acero importado más barato, mayor competencia."
            )
        else:
            st.info("Sin datos de tipo de cambio disponibles.")
else:
    st.info("Sin datos de tipo de cambio disponibles.")

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 6: SÍNTESIS Y ESCENARIOS
# ---------------------------------------------------------------------------

st.subheader("Escenarios: ¿qué puede pasar en los próximos 3 meses?")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.html("""
    <div style="background:#FFEBEE; border:1px solid #C62828; border-radius:8px; padding:14px;">
        <div style="font-size:15px; font-weight:700; color:#C62828; margin-bottom:8px;">Escenario Adverso</div>
        <ul style="margin:0; padding-left:18px; font-size:13px; color:#333;">
            <li>Construcción sigue cayendo más de 10%</li>
            <li>Crédito de construcción sigue restringido</li>
            <li>Inversión pública se retrasa</li>
        </ul>
        <div style="margin-top:10px; font-size:13px; font-weight:600; color:#C62828;">
            Impacto: presión alta sobre pedidos, precios y cartera de clientes
        </div>
        <div style="margin-top:6px; font-size:12px; color:#555;">
            Acción: posición defensiva, control de inventario, foco en clientes seguros
        </div>
    </div>
    """)

with col_b:
    st.html("""
    <div style="background:#FFF3E0; border:1px solid #E65100; border-radius:8px; padding:14px;">
        <div style="font-size:15px; font-weight:700; color:#E65100; margin-bottom:8px;">Escenario Base</div>
        <ul style="margin:0; padding-left:18px; font-size:13px; color:#333;">
            <li>Construcción estabiliza entre -5% y 0%</li>
            <li>Financiamiento de obra mejora gradualmente</li>
            <li>Inversión pública moderada</li>
        </ul>
        <div style="margin-top:10px; font-size:13px; font-weight:600; color:#E65100;">
            Impacto: demanda lateral, sin señal suficiente para crecer inventario agresivamente
        </div>
        <div style="margin-top:6px; font-size:12px; color:#555;">
            Acción: mantener operación actual, optimizar mezcla de productos
        </div>
    </div>
    """)

with col_c:
    st.html("""
    <div style="background:#E8F5E9; border:1px solid #2E7D32; border-radius:8px; padding:14px;">
        <div style="font-size:15px; font-weight:700; color:#2E7D32; margin-bottom:8px;">Escenario Positivo</div>
        <ul style="margin:0; padding-left:18px; font-size:13px; color:#333;">
            <li>Gasto público activa obras en Q2</li>
            <li>Crédito hipotecario y de obra se reactiva</li>
            <li>Construcción vuelve a terreno positivo</li>
        </ul>
        <div style="margin-top:10px; font-size:13px; font-weight:600; color:#2E7D32;">
            Impacto: probabilidad de recuperación gradual de pedidos si la construcción confirma mejora
        </div>
        <div style="margin-top:6px; font-size:12px; color:#555;">
            Acción: preparar disponibilidad, activar clientes dormidos, adelantar compras selectivas
        </div>
    </div>
    """)

st.divider()

# ---------------------------------------------------------------------------
# SECCIÓN 7: ALERTAS AUTOMÁTICAS
# ---------------------------------------------------------------------------

st.subheader("Alertas Activas")

alertas = []
recomendaciones = []

for indicador, info in macro_data.items():
    if not isinstance(info, dict):
        continue
    t = info.get("tendencia", 0) or 0
    v = info.get("valor_actual", 0) or 0

    if indicador == "construccion":
        if v < -10:
            alertas.append("**Construcción en contracción severa** — impacto directo y sostenido en demanda de varilla y alambrón.")
            recomendaciones.append("Revisar inventario. No comprar materia prima extra. Activar búsqueda de nuevos segmentos.")
        elif v < -5:
            alertas.append(f"**Construcción debilitándose** ({v:.1f}%) — monitorear de cerca.")
            recomendaciones.append("Segmentar cartera. Priorizar clientes con proyectos activos.")
        if t < -3:
            alertas.append(f"**Construcción acelerando caída** (tendencia {t:+.1f} pp) — riesgo de que profundice.")
    elif indicador == "inflacion":
        if v > 6:
            alertas.append(f"**Inflación muy alta** ({v:.2f}%) — presión en costos de producción.")
            recomendaciones.append("Revisar precios y contratos. Confirmar cláusulas de ajuste.")
        elif v > 4.5 and t > 0:
            alertas.append(f"**Inflación subiendo** ({v:.2f}%, {t:+.2f} pp) — vigilar evolución.")
    elif indicador == "pib":
        if v < 0:
            alertas.append(f"**PIB negativo** ({v:.1f}%) — economía en contracción.")
            recomendaciones.append("Posición defensiva. Control de cartera y crédito.")
    elif indicador == "usd_mxn":
        if v and v < 17:
            alertas.append(f"**Peso fuerte** (${v:.2f}) — acero importado barato, mayor competencia.")
            recomendaciones.append("Reforzar diferenciación por servicio vs. precio de importación.")

raw_seg = macro_data.get("construccion_segmentada", [])
if isinstance(raw_seg, list) and raw_seg:
    df_seg = pd.DataFrame(raw_seg)
    if not df_seg.empty and {"segmento", "valor"}.issubset(df_seg.columns):
        for seg in df_seg["segmento"].dropna().unique():
            seg_df = df_seg[df_seg["segmento"] == seg].copy()
            seg_df["valor"] = pd.to_numeric(seg_df["valor"], errors="coerce")
            seg_df = seg_df.dropna(subset=["valor"]).sort_values("fecha", ascending=False)
            if not seg_df.empty:
                ultimo = seg_df.iloc[0]["valor"]
                if ultimo < -15:
                    alertas.append(f"**{seg}**: caída de {abs(ultimo):.1f}% — subsector en contracción severa.")

if alertas:
    for a in alertas:
        st.markdown(a)
    if recomendaciones:
        st.markdown("**Recomendaciones:**")
        for i, r in enumerate(recomendaciones, 1):
            st.markdown(f"{i}. {r}")
else:
    st.success("No hay alertas críticas en los indicadores macroeconómicos actuales.")

st.divider()
st.caption(f"Datos: INEGI · Banxico · BigQuery TYASA · Actualizado: {get_last_update()}")
