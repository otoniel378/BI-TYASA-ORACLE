"""
pages/aceros_largos/05_comercio_exterior.py — Comercio Exterior Aceros Largos
Vista gerencial: ¿cuánto acero externo nos compite, quién lo trae y qué hacer?
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from aceros_largos.charts_gerencial import (
    chart_barras_apiladas_comercio,
    chart_barras_horizontales,
)

try:
    from aceros_largos.loaders import load_steel_market_data, get_last_update
    from aceros_largos.loaders_new_data import (
        load_comercio_acero_summary,
        load_comercio_acero_top_countries,
        load_comercio_acero_top_products,
        load_comercio_acero_time_series,
    )
    DATOS_REALES = True
except ImportError as e:
    DATOS_REALES = False
    st.warning(f"No se pudieron cargar datos reales. Error: {e}")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _bloque_comercio(titulo, valor_str, situacion, impacto, escenario, accion, color):
    st.html(f"""
    <div style="
        border-left: 5px solid {color};
        background: #fafafa;
        border-radius: 0 8px 8px 0;
        padding: 16px 18px;
        margin-bottom: 14px;
    ">
        <div style="font-size:16px; font-weight:700; color:#1B3A5C; margin-bottom:6px;">{titulo}</div>
        <div style="font-size:24px; font-weight:800; color:{color}; margin-bottom:10px;">{valor_str}</div>
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <tr>
                <td style="padding:3px 8px 3px 0; color:#555; width:130px; vertical-align:top;"><strong>Situación</strong></td>
                <td style="padding:3px 0; color:#222;">{situacion}</td>
            </tr>
            <tr>
                <td style="padding:3px 8px 3px 0; color:#555; vertical-align:top;"><strong>Nos afecta porque</strong></td>
                <td style="padding:3px 0; color:#222;">{impacto}</td>
            </tr>
            <tr>
                <td style="padding:3px 8px 3px 0; color:#555; vertical-align:top;"><strong>Si sigue así</strong></td>
                <td style="padding:3px 0; color:#222;">{escenario}</td>
            </tr>
            <tr>
                <td style="padding:3px 8px 3px 0; color:#555; vertical-align:top;"><strong>Acción</strong></td>
                <td style="padding:3px 0; color:#1B3A5C; font-weight:700;">{accion}</td>
            </tr>
        </table>
    </div>
    """)


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

st.title("Comercio Exterior — Aceros Largos")
st.markdown(
    "Indicadores de comercio exterior **exclusivamente para productos largos** "
    "(varilla corrugada, alambrón, perfiles estructurales, barras). "
    "Se excluyen aceros inoxidables, rieles y planos. "
    "**Traducido a riesgo competitivo y acción concreta.**"
)
st.caption("Fuente: Monitor Comercio Acero México (MOCAMX) · Filtro activo: familia=LARGOS + patrones de producto largo en BigQuery")

if not DATOS_REALES:
    st.warning("Sin conexión a BigQuery. Los bloques de análisis no tendrán valores.")

with st.sidebar:
    st.header("Filtros")
    periodo_meses = st.selectbox(
        "Período",
        options=[3, 6, 12, 24],
        index=2,
        format_func=lambda x: f"Últimos {x} meses"
    )
    umbral_deficit = st.slider("Alerta déficit (K ton)", 0, 2000, 500)
    umbral_concentracion = st.slider("Alerta concentración (%)", 10, 80, 40)

# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------

_empty_frame = lambda cols: pd.DataFrame(columns=cols)

summary, time_series, top_countries, top_products = {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

if DATOS_REALES:
    with st.spinner("Cargando datos de comercio exterior…"):
        try:
            summary      = load_comercio_acero_summary(periodo_meses)
            time_series  = load_comercio_acero_time_series(periodo_meses)
            top_countries = load_comercio_acero_top_countries("all", 10)
            top_products  = load_comercio_acero_top_products("all", 10)
        except Exception as e:
            st.warning(f"Error cargando datos de comercio: {e}")

    if not isinstance(summary, dict):
        summary = {}

    if not time_series.empty and "mes" in time_series.columns:
        time_series["mes"] = pd.to_datetime(time_series["mes"], errors="coerce")

    if summary or not time_series.empty or not top_countries.empty:
        st.success("Datos reales cargados desde Monitor Comercio Acero México")
    else:
        st.info("Sin datos de comercio disponibles para este período.")

# ---------------------------------------------------------------------------
# KPIs DE COMERCIO
# ---------------------------------------------------------------------------

imp_info = summary.get("importacion", {})
exp_info = summary.get("exportacion", {})

imp_ton = imp_info.get("volumen_total_ton", 0) or 0
exp_ton = exp_info.get("volumen_total_ton", 0) or 0
balanza_ton = exp_ton - imp_ton

imp_paises  = imp_info.get("paises_distintos", 0) or 0
exp_paises  = exp_info.get("paises_distintos", 0) or 0
imp_prod    = imp_info.get("productos_distintos", 0) or 0

hay_datos = bool(imp_ton or exp_ton)

st.divider()
st.subheader("Flujo comercial — solo productos largos")
st.caption("Toneladas reales de varilla, alambrón, perfiles y barras (excluye inoxidables, rieles y planos).")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(
        "Importaciones",
        f"{imp_ton/1000:,.0f}K ton" if imp_ton else "N/D",
        help=f"Toneladas de aceros largos que México importó en los últimos {periodo_meses} meses."
    )
with c2:
    st.metric(
        "Exportaciones",
        f"{exp_ton/1000:,.0f}K ton" if exp_ton else "N/D",
        help=f"Toneladas de aceros largos que México exportó en los últimos {periodo_meses} meses."
    )
with c3:
    bal_str  = f"{balanza_ton/1000:+,.0f}K ton" if hay_datos else "N/D"
    bal_est  = "Déficit" if balanza_ton < 0 else "Superávit" if balanza_ton > 0 else None
    st.metric(
        "Balanza",
        bal_str,
        bal_est,
        delta_color="inverse" if balanza_ton < 0 else "normal",
        help="Exportaciones − Importaciones. Déficit = más acero importado que exportado."
    )
with c4:
    st.metric(
        "Orígenes distintos",
        f"{imp_paises}" if imp_paises else "N/D",
        help="Países desde los que se importó acero largo en el período."
    )

if not hay_datos:
    st.info(
        "Sin datos de volumen en la tabla de comercio para el período seleccionado. "
        "Verificar que la tabla `tyasa_bronce_comercio_acero` tenga datos cargados para aceros largos."
    )
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# BLOQUE GERENCIAL — BALANZA
# ---------------------------------------------------------------------------

st.subheader("¿Cómo nos afecta el comercio exterior?")

if balanza_ton < -umbral_deficit * 1000:
    sit  = f"Déficit de **{abs(balanza_ton)/1000:,.0f}K ton** — ingresa más acero del que sale."
    imp  = "El acero importado compite directamente con nuestra producción, presiona precios y puede quitar volumen a clientes que comparan."
    esc  = "Si el déficit crece y no hay aranceles adicionales, la presión sobre precio local se intensifica."
    acc  = "Identificar productos donde la importación sea mayor. Analizar si competimos en precio o servicio. Evaluar impacto arancelario."
    _bloque_comercio("Balanza Comercial — Déficit Significativo",
                     f"{balanza_ton/1000:+,.0f}K ton", sit, imp, esc, acc, "#C62828")
elif balanza_ton < 0:
    sit  = f"Déficit moderado de **{abs(balanza_ton)/1000:,.0f}K ton**."
    imp  = "Hay penetración importadora pero manejable. El acero externo compite en ciertos productos o regiones específicas."
    esc  = "Sin cambios de política comercial, la tendencia podría mantenerse o crecer gradualmente."
    acc  = "Monitorear qué productos importados son más competitivos. Fortalecer ventajas de servicio: entrega rápida, crédito, soporte."
    _bloque_comercio("Balanza Comercial — Déficit Moderado",
                     f"{balanza_ton/1000:+,.0f}K ton", sit, imp, esc, acc, "#E65100")
else:
    sit  = f"Superávit de **{balanza_ton/1000:,.0f}K ton** — México exporta más de lo que importa."
    imp  = "Posición competitiva favorable. El acero nacional domina el mercado local y también se coloca en el exterior."
    esc  = "Superávit sostenido indica competitividad real. Riesgo si suben aranceles en destinos exportadores."
    acc  = "Explorar nuevos destinos de exportación. Mantener competitividad en costo y calidad."
    _bloque_comercio("Balanza Comercial — Superávit",
                     f"{balanza_ton/1000:+,.0f}K ton", sit, imp, esc, acc, "#2E7D32")

st.divider()

# ---------------------------------------------------------------------------
# EVOLUCIÓN TEMPORAL
# ---------------------------------------------------------------------------

if not time_series.empty and "tipo_operacion" in time_series.columns:
    st.subheader("¿La importación está creciendo o bajando?")
    st.caption(
        "Barras agrupadas: **rojo = importaciones**, **verde = exportaciones**, "
        "**línea punteada azul = balanza**. "
        "Si las barras rojas crecen mes a mes, hay más presión importadora."
    )

    imp_ts = time_series[time_series["tipo_operacion"] == "IMPORTACION"].copy().sort_values("mes")
    exp_ts = time_series[time_series["tipo_operacion"] == "EXPORTACION"].copy().sort_values("mes")

    # Alinear por mes
    if not imp_ts.empty and not exp_ts.empty:
        meses_comunes = sorted(set(imp_ts["mes"].tolist()) & set(exp_ts["mes"].tolist()))
        if meses_comunes:
            imp_alin = imp_ts.set_index("mes").reindex(meses_comunes)["volumen_mensual_ton"].fillna(0).tolist()
            exp_alin = exp_ts.set_index("mes").reindex(meses_comunes)["volumen_mensual_ton"].fillna(0).tolist()
            x_meses  = [m.strftime("%b %y") if hasattr(m, "strftime") else str(m) for m in meses_comunes]

            fig_com = chart_barras_apiladas_comercio(
                x=x_meses,
                importaciones=imp_alin,
                exportaciones=exp_alin,
                titulo="Importaciones vs Exportaciones mensual — aceros largos (toneladas)",
                height=360,
            )
            st.plotly_chart(fig_com, width="stretch")
        else:
            st.info("Sin meses comunes entre importaciones y exportaciones.")
    elif not imp_ts.empty:
        x_imp = imp_ts["mes"].dt.strftime("%b %y").tolist()
        y_imp = imp_ts["volumen_mensual_ton"].tolist()
        fig_com = chart_barras_apiladas_comercio(
            x=x_imp, importaciones=y_imp, exportaciones=[0]*len(y_imp),
            titulo="Importaciones mensuales — aceros largos (toneladas)", height=340,
        )
        st.plotly_chart(fig_com, width="stretch")
    else:
        st.info("Sin serie temporal de flujos disponible.")

    # Lectura automática
    if not imp_ts.empty and len(imp_ts) >= 2:
        ultimo_imp  = imp_ts.iloc[-1]["volumen_mensual_ton"]
        anterior_imp = imp_ts.iloc[-2]["volumen_mensual_ton"]
        var_imp = ((ultimo_imp - anterior_imp) / anterior_imp * 100) if anterior_imp else 0
        if var_imp > 10:
            st.warning(f"Las importaciones subieron **{var_imp:.1f}%** el último mes. Mayor presión competitiva.")
        elif var_imp > 0:
            st.warning(f"Las importaciones subieron **{var_imp:.1f}%** vs mes anterior. Monitorear.")
        elif var_imp < -10:
            st.success(f"Las importaciones bajaron **{abs(var_imp):.1f}%** el último mes. Menor presión importadora.")
        else:
            st.info(f"Importaciones estables ({var_imp:+.1f}% vs mes anterior).")

st.divider()

# ---------------------------------------------------------------------------
# TOP PAÍSES
# ---------------------------------------------------------------------------

if not top_countries.empty:
    st.subheader("¿De dónde viene el acero que nos compite?")
    st.caption("Los países que más importaciones traen son los que mayor presión generan en precio.")

    top_imp = top_countries[top_countries["tipo_operacion"] == "IMPORTACION"].head(6).copy()
    top_exp = top_countries[top_countries["tipo_operacion"] == "EXPORTACION"].head(5).copy()

    col_imp, col_exp = st.columns(2)

    with col_imp:
        st.markdown("**¿De dónde importamos?**")
        if not top_imp.empty:
            total_imp_paises = top_imp["volumen_total_ton"].sum()
            for _, row in top_imp.iterrows():
                pais       = row.get("pais", "N/D")
                vol_k      = row["volumen_total_ton"] / 1000
                pct        = row["volumen_total_ton"] / total_imp_paises * 100 if total_imp_paises else 0
                ops        = row.get("operaciones", 0)
                c_bar      = "#C62828" if pct > umbral_concentracion else "#E65100" if pct > 20 else "#555"

                st.html(f"""
                <div style="padding:8px 10px; border-radius:6px; background:#f5f5f5; margin-bottom:6px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="color:#1B3A5C;">{pais}</strong>
                        <span style="color:{c_bar}; font-weight:700;">{pct:.1f}%</span>
                    </div>
                    <div style="font-size:12px; color:#555;">{vol_k:,.1f}K ton · {ops:,} operaciones</div>
                    <div style="background:#e0e0e0; border-radius:4px; height:6px; margin-top:4px;">
                        <div style="width:{min(pct,100):.0f}%; background:{c_bar}; height:6px; border-radius:4px;"></div>
                    </div>
                </div>
                """)

            # Alerta de concentración
            if not top_imp.empty:
                max_pais = top_imp.iloc[0]
                max_pct  = max_pais["volumen_total_ton"] / total_imp_paises * 100 if total_imp_paises else 0
                if max_pct > umbral_concentracion:
                    st.warning(
                        f"**{max_pais.get('pais','N/D')}** concentra **{max_pct:.1f}%** de las importaciones. "
                        "Dependencia alta de un solo origen: ante aranceles o disrupciones, los flujos pueden cambiar rápido."
                    )
        else:
            st.info("Sin datos de países de origen.")

    with col_exp:
        st.markdown("**¿A dónde exportamos?**")
        if not top_exp.empty:
            total_exp_paises = top_exp["volumen_total_ton"].sum()
            for _, row in top_exp.iterrows():
                pais  = row.get("pais", "N/D")
                vol_k = row["volumen_total_ton"] / 1000
                pct   = row["volumen_total_ton"] / total_exp_paises * 100 if total_exp_paises else 0
                ops   = row.get("operaciones", 0)

                st.html(f"""
                <div style="padding:8px 10px; border-radius:6px; background:#f0f7f0; margin-bottom:6px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="color:#1B3A5C;">{pais}</strong>
                        <span style="color:#2E7D32; font-weight:700;">{pct:.1f}%</span>
                    </div>
                    <div style="font-size:12px; color:#555;">{vol_k:,.1f}K ton · {ops:,} operaciones</div>
                    <div style="background:#e0e0e0; border-radius:4px; height:6px; margin-top:4px;">
                        <div style="width:{min(pct,100):.0f}%; background:#2E7D32; height:6px; border-radius:4px;"></div>
                    </div>
                </div>
                """)
        else:
            st.info("Sin datos de destinos de exportación.")

st.divider()

# ---------------------------------------------------------------------------
# TOP PRODUCTOS
# ---------------------------------------------------------------------------

if not top_products.empty:
    st.subheader("¿Qué productos son más vulnerables a la importación?")
    st.caption("Los productos con mayor volumen importado son los que enfrentan más competencia externa.")

    top_prod_imp = top_products[top_products["tipo_operacion"] == "IMPORTACION"].head(8).copy()
    top_prod_exp = top_products[top_products["tipo_operacion"] == "EXPORTACION"].head(8).copy()

    if not top_prod_imp.empty:
        col_pi, col_pe = st.columns(2)

        with col_pi:
            st.markdown("**Productos más importados**")
            st.caption("Mayor barra = mayor competencia importadora en ese producto.")
            fig_pi = chart_barras_horizontales(
                valores=top_prod_imp["volumen_total_ton"].tolist(),
                etiquetas=[str(p)[:35] if p else "N/D" for p in top_prod_imp["producto"].tolist()],
                titulo="Importaciones por producto (ton)",
                color_base="#C62828",
                unidad=" ton",
                height=320,
            )
            st.plotly_chart(fig_pi, width="stretch")

        with col_pe:
            st.markdown("**Productos más exportados**")
            st.caption("Mayor barra = mayor salida de ese producto al exterior.")
            if not top_prod_exp.empty:
                fig_pe = chart_barras_horizontales(
                    valores=top_prod_exp["volumen_total_ton"].tolist(),
                    etiquetas=[str(p)[:35] if p else "N/D" for p in top_prod_exp["producto"].tolist()],
                    titulo="Exportaciones por producto (ton)",
                    color_base="#2E7D32",
                    unidad=" ton",
                    height=320,
                )
                st.plotly_chart(fig_pe, width="stretch")
            else:
                st.info("Sin datos de exportación por producto.")

st.divider()

# ---------------------------------------------------------------------------
# ALERTAS Y ACCIONES CONCRETAS
# ---------------------------------------------------------------------------

st.subheader("Alertas y Acciones Inmediatas")

alertas = []

if balanza_ton < -umbral_deficit * 1000:
    alertas.append({
        "nivel": "CRÍTICO",
        "titulo": "Déficit comercial alto",
        "mensaje": f"El déficit de {abs(balanza_ton)/1000:,.0f}K ton significa que el mercado recibe mucho más acero importado del que exportamos.",
        "accion": "Analizar qué productos importados tienen mayor penetración. Revisar política de precios en esos segmentos.",
        "bg": "#FFEBEE", "border": "#C62828"
    })

if not top_countries.empty:
    top_imp_c = top_countries[top_countries["tipo_operacion"] == "IMPORTACION"]
    if not top_imp_c.empty and imp_ton > 0:
        max_pais_row = top_imp_c.iloc[0]
        pct_max = max_pais_row["volumen_total_ton"] / imp_ton * 100
        if pct_max > umbral_concentracion:
            alertas.append({
                "nivel": "ALERTA",
                "titulo": f"Alta dependencia de {max_pais_row.get('pais', 'N/D')}",
                "mensaje": f"{pct_max:.1f}% de las importaciones provienen de un solo origen. Ante cambios arancelarios o disrupciones de cadena, los volúmenes pueden redirigirse rápido.",
                "accion": "Monitorear aranceles vigentes y posibles medidas antidumping. Anticipar cambios en precio de importación.",
                "bg": "#FFF3E0", "border": "#E65100"
            })

if not time_series.empty and "tipo_operacion" in time_series.columns:
    imp_ts_a = time_series[time_series["tipo_operacion"] == "IMPORTACION"].sort_values("mes")
    if len(imp_ts_a) >= 3:
        last_3 = imp_ts_a.tail(3)["volumen_mensual_ton"].tolist()
        if all(last_3[i] < last_3[i+1] for i in range(len(last_3)-1)):
            alertas.append({
                "nivel": "ALERTA",
                "titulo": "Importaciones en tendencia alcista",
                "mensaje": "Las importaciones han crecido 3 meses consecutivos. La presión competitiva está aumentando.",
                "accion": "Revisar si el crecimiento es en productos que también producimos. Preparar argumentos de venta frente a acero importado.",
                "bg": "#FFF3E0", "border": "#E65100"
            })

if balanza_ton > 0 and exp_ton > imp_ton * 1.2:
    alertas.append({
        "nivel": "OPORTUNIDAD",
        "titulo": "Posición exportadora sólida",
        "mensaje": "México exporta significativamente más de lo que importa en aceros largos. Señal de competitividad.",
        "accion": "Explorar nuevos mercados de exportación. Evaluar si hay capacidad instalada para crecer en destinos actuales.",
        "bg": "#E8F5E9", "border": "#2E7D32"
    })

if not alertas:
    alertas.append({
        "nivel": "SIN ALERTAS",
        "titulo": "Comercio exterior estable",
        "mensaje": "No se detectan señales críticas en el período seleccionado.",
        "accion": "Continuar monitoreo mensual.",
        "bg": "#E3F2FD", "border": "#1565C0"
    })

for a in alertas:
    st.html(f"""
    <div style="
        background:{a['bg']};
        border:1px solid {a['border']};
        border-left:5px solid {a['border']};
        border-radius:8px;
        padding:14px 16px;
        margin-bottom:10px;
    ">
        <div style="font-weight:700; font-size:14px; color:#1B3A5C; margin-bottom:4px;">
            {a['nivel']} — {a['titulo']}
        </div>
        <p style="margin:0 0 6px 0; font-size:13px; color:#333;">{a['mensaje']}</p>
        <p style="margin:0; font-size:13px; font-weight:600; color:#1B3A5C;">▶ {a['accion']}</p>
    </div>
    """)

st.divider()

# ---------------------------------------------------------------------------
# PREGUNTAS FRECUENTES DEL GERENTE
# ---------------------------------------------------------------------------

with st.expander("Preguntas frecuentes sobre comercio exterior"):
    st.markdown("""
    **¿Déficit significa que perdemos mercado?**
    No necesariamente. Significa que entra más acero del que sale. El impacto real depende de qué productos
    se importan, a qué precio y si compiten directamente con los nuestros.

    **¿Por qué aparece "Varios" como país de origen?**
    Cuando los datos de comercio vienen agregados por mes (sin desagregar por transacción), el origen se
    consolida. Los datos de top países usan registros individuales cuando están disponibles.

    **¿Los datos están en USD o toneladas?**
    La fuente disponible (Monitor Comercio Acero México) reporta principalmente **volumen en toneladas**.
    No se inventan valores en USD para no distorsionar el análisis.

    **¿Con qué frecuencia se actualizan estos datos?**
    La tabla de comercio se carga periódicamente desde la fuente MOCAMX. Los datos tienen un rezago típico
    de 1-2 meses respecto al período real.

    **¿Qué es acero "largo"?**
    Incluye: varilla corrugada, alambrón, perfiles estructurales y barras. Son los productos que demanda
    principalmente el sector de la construcción.
    """)

st.caption(f"Datos: Monitor Comercio Acero México (MOCAMX) · BigQuery TYASA · Actualizado: {get_last_update() if DATOS_REALES else 'N/D'}")
