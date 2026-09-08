"""
pages/mercado/08_pronostico_comercio.py — Pronóstico de Importación (CANACERO)

Reutiliza el motor de pronóstico de aceros_planos/negros/analytics/forecasting.py
(ETS, SARIMA, XGBoost, Naive, auto-selección por backtesting) sobre las series
mensuales de comercio exterior nacional filtradas a las fracciones de TYASA
(mercado/canacero/loaders.py). Mismo molde visual que
pages/ap_negros/04_forecasting.py — histórico+pronóstico con banda 90%,
tabla de valores futuros, backtesting.
"""

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)
_scripts_dir = os.path.join(_root, "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from config import COLORS, COLOR_SEQUENCE, FORECAST_HORIZON_DEFAULT, FORECAST_HORIZON_MAX

from fracciones_tyasa import FRACCIONES_TYASA
from mercado.canacero.loaders import (
    load_serie_tiempo_tyasa,
    load_series_fracciones_tyasa,
    load_descripciones_tyasa,
)
from mercado.inegi.loaders import load_serie_por_nombre
from mercado_noticias.loaders import load_variables_mercado, load_eventos_cerca_de, load_eventos_en_rango
from mercado_noticias.analytics.detector import detectar_quiebres
from mercado_noticias.analytics.ai_analysis import _call_gemini_text
from mercado_noticias.analytics.noticias import buscar_noticias_actuales

DIAS_NOTICIAS_RECIENTES = 60  # más allá de esto, la búsqueda en vivo ya no sirve (busca desde "hoy", no desde <fecha>)
from aceros_planos.negros.analytics.forecasting import (
    generar_forecast,
    filtrar_por_dimension,
    MODELOS_DISPONIBLES,
)
from core.components.kpi_cards import seccion_titulo
from core.components.filters import sidebar_header
from core.components.tables import tabla_ejecutiva
from core.components.charts import barras_horizontales

INEGI_EXOG = ["IMAI_HierroAcero_3311_Indice", "IMAI_Construccion_Indice", "BC_Siderurgia_Importaciones"]
MERCADO_VISUAL = ["USD_MXN", "HRC_CME_USD", "Mineral_Hierro"]
_MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _mes_anio_es(fecha) -> str:
    f = pd.Timestamp(fecha)
    return f"{_MESES_ES[f.month - 1]} {f.year}"

try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""


@st.cache_data(ttl=1800, show_spinner="Cargando indicadores INEGI...")
def _construir_df_exog_inegi() -> pd.DataFrame:
    """fecha + una columna por indicador INEGI, mismo rango que CANACERO — es
    lo que entra al modelo (rezagado dentro de forecasting.py)."""
    partes = []
    for nombre in INEGI_EXOG:
        s = load_serie_por_nombre(nombre)[["fecha", "valor"]].rename(columns={"valor": nombre})
        partes.append(s.set_index("fecha"))
    return pd.concat(partes, axis=1).reset_index()


@st.cache_data(ttl=1800, show_spinner="Cargando contexto macro...")
def _construir_contexto_visual() -> pd.DataFrame:
    """INEGI + variables de mercado (USD/MXN, HRC, mineral de hierro),
    mensualizadas — solo para el panel visual, estas últimas no entran al
    modelo (su historial solo llega a 2024)."""
    df_inegi = _construir_df_exog_inegi()
    df_mkt = load_variables_mercado(dias=1200)
    if df_mkt.empty:
        return df_inegi
    df_mkt = df_mkt[df_mkt["nombre"].isin(MERCADO_VISUAL)].copy()
    df_mkt["fecha"] = df_mkt["fecha"].dt.to_period("M").dt.to_timestamp()
    df_mkt_mensual = (
        df_mkt.sort_values("fecha").groupby(["fecha", "nombre"])["valor"].last()
        .unstack("nombre").reset_index()
    )
    return df_inegi.merge(df_mkt_mensual, on="fecha", how="outer").sort_values("fecha")


def _contexto_a_formato_largo(df_ctx: pd.DataFrame) -> pd.DataFrame:
    """(fecha, nombre, categoria, valor) — formato que espera
    mercado_noticias.analytics.detector.detectar_quiebres()."""
    variables = [c for c in df_ctx.columns if c != "fecha"]
    largo = df_ctx.melt(id_vars="fecha", value_vars=variables, var_name="nombre", value_name="valor")
    largo["categoria"] = largo["nombre"].apply(lambda n: "INEGI" if n in INEGI_EXOG else "Mercado")
    return largo.dropna(subset=["valor"])

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
sidebar_header("Parámetros", "🔮")
horizonte = st.sidebar.slider(
    "Horizonte (meses)", min_value=1, max_value=FORECAST_HORIZON_MAX,
    value=FORECAST_HORIZON_DEFAULT, key="fc_com_horizonte",
)
modelo_key = st.sidebar.selectbox(
    "Modelo de pronóstico", options=list(MODELOS_DISPONIBLES.keys()),
    format_func=lambda k: MODELOS_DISPONIBLES[k], index=0, key="fc_com_modelo",
)
movimiento_label = st.sidebar.radio(
    "Movimiento", ["Importación", "Exportación"], key="fc_com_movimiento",
)
movimiento = "IMPORTACION" if movimiento_label == "Importación" else "EXPORTACION"
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"""
    <div style='font-size:0.78rem;color:{COLORS["text_light"]};'>
    <b>Guía de modelos</b><br><br>
    ETS — Holt-Winters. Ideal para volumen estable con estacionalidad anual.<br><br>
    SARIMA — Clásico estadístico. Bueno cuando hay tendencia clara.<br><br>
    XGBoost — Machine Learning con rezagos. Captura patrones no lineales.<br><br>
    Naive — Baseline: igual al mismo mes del año pasado.<br><br>
    Auto — Prueba los 4 y elige el de menor MAPE en backtesting.
    </div>
    """,
    unsafe_allow_html=True,
)

st.title("Pronóstico de Comercio Exterior")
st.divider()

with st.spinner("Cargando series históricas..."):
    df_total = load_serie_tiempo_tyasa(movimiento)
    df_fracciones = load_series_fracciones_tyasa(movimiento)
    descripciones_fraccion = load_descripciones_tyasa()
    df_exog_inegi = _construir_df_exog_inegi()
    df_contexto_visual = _construir_contexto_visual()
    df_contexto_largo = _contexto_a_formato_largo(df_contexto_visual)


def _colores_modelo(nombre: str) -> str:
    if "ETS" in nombre or "Holt" in nombre:
        return COLORS["success"]
    if "XGB" in nombre:
        return COLOR_SEQUENCE[1]
    if "SARIMA" in nombre or "ARIMA" in nombre:
        return COLORS["secondary"]
    return COLORS["neutral"]


def _grafico_forecast(resultado, titulo: str = "") -> go.Figure:
    fc_df, hist_df = resultado.forecast, resultado.historico
    fig = go.Figure()
    if fc_df.empty or hist_df.empty:
        return fig

    fc_fut = fc_df[fc_df["ds"] > hist_df["ds"].max()].copy()
    color_fc = _colores_modelo(resultado.modelo)

    if not fc_fut.empty and fc_fut["yhat_upper"].notna().any():
        band = fc_fut.dropna(subset=["yhat_upper", "yhat_lower"])
        if not band.empty:
            fig.add_trace(go.Scatter(
                x=pd.concat([band["ds"], band["ds"].iloc[::-1]]),
                y=pd.concat([band["yhat_upper"], band["yhat_lower"].iloc[::-1]]),
                fill="toself", fillcolor="rgba(74,123,167,0.15)",
                line=dict(color="rgba(0,0,0,0)"), name="Banda 90%", hoverinfo="skip",
            ))

    fig.add_trace(go.Scatter(x=hist_df["ds"], y=hist_df["y"], name="Histórico",
                              line=dict(color=COLORS["primary"], width=2.5),
                              hovertemplate="%{x|%b %Y}<br>Real: %{y:,.1f} ton<extra></extra>"))

    if not fc_fut.empty:
        fig.add_trace(go.Scatter(x=fc_fut["ds"], y=fc_fut["yhat"],
                                  name=f"Pronóstico ({horizonte}m)",
                                  line=dict(color=color_fc, width=2.5, dash="dot"),
                                  mode="lines+markers", marker=dict(size=7),
                                  hovertemplate="%{x|%b %Y}<br>Pronóstico: %{y:,.1f} ton<extra></extra>"))

    corte = str(hist_df["ds"].max())
    fig.add_shape(type="line", x0=corte, x1=corte, y0=0, y1=1, xref="x", yref="paper",
                  line=dict(color=COLORS["neutral"], width=1.5, dash="dot"))
    fig.add_annotation(x=corte, y=1, xref="x", yref="paper", text="Hoy", showarrow=False,
                       yanchor="bottom", font=dict(size=11, color=COLORS["neutral"]))
    fig.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(showgrid=False), yaxis=dict(title="Toneladas", gridcolor="#E5E7EB"),
        legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
        title=dict(text=titulo, font=dict(size=14, color=COLORS["primary"]), x=0), height=390,
        transition=dict(duration=400, easing="cubic-in-out"),
    )
    return fig


def _grafico_contexto_macro(df_ctx: pd.DataFrame, fecha_min) -> go.Figure:
    """Todas las variables indexadas a 100 en su primer valor disponible
    dentro del rango mostrado — se grafican distintas escalas (índice INEGI,
    USD/MXN, USD/ton) en el mismo eje solo así son comparables visualmente."""
    fig = go.Figure()
    d = df_ctx[df_ctx["fecha"] >= fecha_min] if not df_ctx.empty else df_ctx
    variables = [c for c in d.columns if c != "fecha"]
    for i, var in enumerate(variables):
        serie = d[["fecha", var]].dropna()
        if serie.empty or not serie[var].iloc[0]:
            continue
        indexado = serie[var] / serie[var].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=serie["fecha"], y=indexado, name=var.replace("_", " "),
            line=dict(width=1.8, color=COLOR_SEQUENCE[i % len(COLOR_SEQUENCE)]),
            hovertemplate=f"%{{x|%b %Y}}<br>{var}: %{{y:.1f}} (base 100)<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=30, b=30), height=260,
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="#E5E7EB", title="Índice (base 100 al inicio del rango)"),
        legend=dict(orientation="h", y=-0.35, x=0.5, xanchor="center", font=dict(size=9)),
        transition=dict(duration=400, easing="cubic-in-out"),
    )
    return fig


def _tabla_futuro(resultado) -> pd.DataFrame:
    fc, hist = resultado.forecast, resultado.historico
    if fc.empty or hist.empty:
        return pd.DataFrame()
    fut = fc[fc["ds"] > hist["ds"].max()].copy()
    fut = fut.rename(columns={"ds": "PERIODO", "yhat": "FORECAST_TON",
                               "yhat_lower": "LOWER_90", "yhat_upper": "UPPER_90"})
    for c in ["FORECAST_TON", "LOWER_90", "UPPER_90"]:
        if c in fut.columns:
            fut[c] = fut[c].round(1)
    return fut.reset_index(drop=True)


def _grafico_barras_anio(df_anio: pd.DataFrame, variables: list, anio: int) -> go.Figure:
    """Una sola gráfica de barras agrupadas, todas las variables juntas —
    indexadas a 100 en su primer valor del año (mismo truco que la línea de
    contexto macro) para poder comparar aunque tengan escalas muy distintas
    (un índice INEGI de ~100 junto a millones de BC_Siderurgia no se vería
    nada si se graficaran en unidades reales)."""
    fig = go.Figure()
    for i, var in enumerate(variables):
        serie_var = df_anio[["fecha", var]].dropna().sort_values("fecha")
        if serie_var.empty or not serie_var[var].iloc[0]:
            continue
        meses = serie_var["fecha"].apply(lambda f: _MESES_ES[f.month - 1][:3])
        indexado = serie_var[var] / serie_var[var].iloc[0] * 100
        fig.add_trace(go.Bar(
            x=meses, y=indexado, name=var.replace("_", " "),
            marker_color=COLOR_SEQUENCE[i % len(COLOR_SEQUENCE)],
            hovertemplate=f"%{{x}} {anio}<br>{var}: %{{y:.1f}} (base 100)<extra></extra>",
        ))
    fig.update_layout(
        barmode="group",
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=30, b=30), height=380,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB", title="Índice (base 100 = Ene)"),
        legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center", font=dict(size=9)),
        transition=dict(duration=400, easing="cubic-in-out"),
    )
    return fig


def _render_resumen_anio(anio: int, key_prefix: str):
    """Panorama del año completo: valor mensual por variable (barras),
    todas las rupturas estadísticas detectadas en cualquier mes del año, y
    los eventos históricos catalogados que se traslapan con el año."""
    fecha_ini = pd.Timestamp(year=anio, month=1, day=1)
    fecha_fin = pd.Timestamp(year=anio, month=12, day=31)
    df_anio = df_contexto_visual[
        (df_contexto_visual["fecha"] >= fecha_ini) & (df_contexto_visual["fecha"] <= fecha_fin)
    ].copy()

    variables = [c for c in df_contexto_visual.columns if c != "fecha"]
    variables_con_dato = [v for v in variables if v in df_anio.columns and df_anio[v].notna().any()]

    if variables_con_dato:
        st.plotly_chart(
            _grafico_barras_anio(df_anio, variables_con_dato, anio),
            use_container_width=True, key=f"{key_prefix}_bar_{anio}",
        )
    else:
        st.caption(f"Sin datos de contexto macro para {anio}.")

    meses_anio = pd.date_range(fecha_ini, fecha_fin, freq="MS")
    quiebres_anio = []
    for m in meses_anio:
        for r in detectar_quiebres(df_contexto_largo, fecha_corte=m, umbral_sigma=1.5):
            if r.quiebre:
                quiebres_anio.append({
                    "Mes": _mes_anio_es(m), "Variable": r.variable, "Sigma": r.sigma,
                    "Cambio %": r.cambio_pct, "Severidad": r.severidad,
                })

    col_q, col_e = st.columns(2)
    with col_q:
        st.markdown(f"**Rupturas estadísticas en {anio}**")
        if quiebres_anio:
            _ORDEN_SEVERIDAD = {"Crítico": 0, "Alto": 1, "Moderado": 2, "Normal": 3}
            tabla_q = pd.DataFrame(quiebres_anio).sort_values(
                by="Severidad", key=lambda s: s.map(_ORDEN_SEVERIDAD)
            )
            st.dataframe(tabla_q, hide_index=True, use_container_width=True, height=220)
        else:
            st.caption("Sin rupturas estadísticas significativas en ningún mes de este año.")

    with col_e:
        st.markdown(f"**Eventos históricos en {anio}**")
        eventos_anio = load_eventos_en_rango(fecha_ini, fecha_fin)
        if eventos_anio.empty:
            st.caption("Sin eventos catalogados en este año.")
        else:
            for _, ev in eventos_anio.iterrows():
                st.markdown(f"**{ev['nombre']}**")
                st.caption(ev["descripcion"])


def _render_detalle_punto(fecha: pd.Timestamp, key_prefix: str):
    """Panel de detalle para el punto del timeline que el usuario clickeó:
    confirmación estadística de quiebre (detector.py), evento histórico
    curado si cae cerca, y análisis con IA a petición (no automático)."""
    with st.container(border=True):
        st.markdown(f"**📍 {_mes_anio_es(fecha)}**")

        resultados_quiebre = [
            r for r in detectar_quiebres(df_contexto_largo, fecha_corte=fecha, umbral_sigma=1.5)
            if r.quiebre
        ]
        eventos = load_eventos_cerca_de(fecha)

        col_q, col_e = st.columns(2)
        with col_q:
            st.markdown("**Confirmación estadística**")
            if not resultados_quiebre:
                st.caption("Sin ruptura estadística significativa detectada en las variables monitoreadas.")
            else:
                tabla_q = pd.DataFrame([{
                    "Variable": r.variable, "Sigma": r.sigma, "Cambio %": r.cambio_pct,
                    "Severidad": r.severidad,
                } for r in resultados_quiebre])
                st.dataframe(tabla_q, hide_index=True, use_container_width=True)

        with col_e:
            st.markdown("**Evento histórico**")
            if eventos.empty:
                st.caption("Sin eventos catalogados cerca de esta fecha.")
            else:
                for _, ev in eventos.iterrows():
                    st.markdown(f"**{ev['nombre']}**")
                    st.caption(ev["descripcion"])

        noticias_por_variable = {}
        es_reciente = (pd.Timestamp.now() - fecha).days <= DIAS_NOTICIAS_RECIENTES
        if resultados_quiebre:
            st.markdown("**Noticias relacionadas**")
            if es_reciente:
                with st.spinner("Buscando noticias..."):
                    for r in resultados_quiebre[:3]:
                        noticias = buscar_noticias_actuales(r.variable, dias=DIAS_NOTICIAS_RECIENTES, max_resultados=3)
                        if noticias:
                            noticias_por_variable[r.variable] = noticias
                if noticias_por_variable:
                    for var, noticias in noticias_por_variable.items():
                        st.caption(var.replace("_", " "))
                        for n in noticias:
                            st.markdown(f"- [{n.get('titulo', '(sin título)')}]({n.get('url', '')}) — {n.get('fuente', '')}")
                else:
                    st.caption("No se encontraron noticias recientes relacionadas.")
            else:
                st.caption(
                    f"🔍 Búsqueda en vivo solo disponible para periodos de los últimos {DIAS_NOTICIAS_RECIENTES} "
                    "días — no existe un archivo confiable de noticias pasadas para fechas históricas. Por eso "
                    "las fechas viejas dependen de que el evento esté catalogado arriba."
                )

        if not resultados_quiebre and eventos.empty:
            return

        ck_ia = f"{key_prefix}_ia_{fecha.strftime('%Y%m')}"
        if not _GEMINI_KEY:
            st.caption("🤖 Análisis con IA no disponible — falta configurar GEMINI_API_KEY.")
        elif ck_ia in st.session_state:
            st.markdown(st.session_state[ck_ia])
        elif st.button("🤖 Analizar con IA", key=f"btn_{ck_ia}"):
            partes_prompt = [f"Fecha: {_mes_anio_es(fecha)}."]
            if resultados_quiebre:
                partes_prompt.append("Rupturas estadísticas detectadas: " + "; ".join(
                    f"{r.variable} (sigma={r.sigma}, cambio={r.cambio_pct}%, {r.severidad})"
                    for r in resultados_quiebre
                ))
            if not eventos.empty:
                partes_prompt.append("Eventos conocidos en esa fecha: " + "; ".join(
                    f"{ev['nombre']}: {ev['descripcion']}" for _, ev in eventos.iterrows()
                ))
            if noticias_por_variable:
                titulos = [n.get("titulo", "") for lista in noticias_por_variable.values() for n in lista]
                partes_prompt.append("Noticias recientes encontradas: " + "; ".join(titulos[:6]))
            prompt = (
                "Eres analista de mercado para una acerera mexicana (TYASA). "
                + " ".join(partes_prompt)
                + " En máximo 3 frases, explica qué significó esto para el mercado siderúrgico "
                  "mexicano y el comercio exterior de acero."
            )
            with st.spinner("Consultando IA..."):
                respuesta = _call_gemini_text(prompt, _GEMINI_KEY)
            st.session_state[ck_ia] = respuesta
            st.rerun()


def _render_resultado(res, key_prefix: str):
    if res.error_msg:
        st.error(f"No se pudo generar el pronóstico: {res.error_msg}")
        return

    color_mod = _colores_modelo(res.modelo)
    col_m, col_mt = st.columns([1, 3])
    with col_m:
        st.markdown(
            f"""<div style='background:{COLORS["surface"]};border:1px solid #E5E7EB;
            border-left:5px solid {color_mod};border-radius:8px;padding:14px;'>
            <div style='color:{COLORS["text_light"]};font-size:0.75rem;font-weight:600;'>MODELO USADO</div>
            <div style='color:{color_mod};font-size:1.05rem;font-weight:700;line-height:1.4;'>{res.modelo}</div>
            </div>""", unsafe_allow_html=True,
        )
    with col_mt:
        mape = res.metricas.get("MAPE (%)", float("nan")) if res.metricas else float("nan")
        mape_txt = f"{mape:.1f}%" if not np.isnan(mape) else "N/A"
        if not np.isnan(mape):
            nivel, color_mape = ("alto", COLORS["danger"]) if mape > 50 else (
                ("moderado", COLORS["warning"]) if mape > 30 else ("aceptable", COLORS["success"])
            )
            st.markdown(
                f"<div style='background:{color_mape}22;border:1px solid {color_mape}55;"
                f"border-radius:6px;padding:8px 14px;color:{color_mape};font-weight:600;'>"
                f"MAPE {nivel}: {mape_txt}</div>",
                unsafe_allow_html=True,
            )

    fig = _grafico_forecast(res, titulo=f"Histórico + Pronóstico {horizonte} meses")
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_chart_forecast")

    if not df_contexto_visual.empty and not res.historico.empty:
        seccion_titulo("Contexto macro", "Mismo periodo, indexado a 100")
        st.plotly_chart(
            _grafico_contexto_macro(df_contexto_visual, res.historico["ds"].min()),
            use_container_width=True, key=f"{key_prefix}_chart_macro",
        )

        # La exploración por año/mes usa TODO el historial de contexto macro
        # disponible (INEGI llega mucho más atrás que CANACERO) — no se limita
        # al arranque de la serie pronosticada, para poder ver años como 2020
        # (COVID) aunque el pronóstico en sí solo tenga datos desde 2021.
        fechas_disp = sorted(df_contexto_visual["fecha"].dropna().unique(), reverse=True)
        anios_disp = sorted({pd.Timestamp(f).year for f in fechas_disp}, reverse=True)

        if anios_disp:
            st.markdown("###### Explorar por año")
            anio_sel = st.selectbox("Año", anios_disp, key=f"{key_prefix}_selector_anio")
            _render_resumen_anio(anio_sel, key_prefix)

            meses_del_anio = [f for f in fechas_disp if pd.Timestamp(f).year == anio_sel]
            if meses_del_anio:
                st.markdown("###### Ver el detalle de un mes específico (opcional)")
                mes_sel = st.selectbox(
                    "Mes", meses_del_anio, format_func=_mes_anio_es,
                    key=f"{key_prefix}_selector_mes",
                )
                _render_detalle_punto(pd.Timestamp(mes_sel), key_prefix)

    if res.contribuciones is not None and not res.contribuciones.empty:
        st.divider()
        seccion_titulo("Sensibilidad del modelo", "Qué tanto empujó cada variable el pronóstico (XGBoost, SHAP nativo)")
        st.plotly_chart(
            barras_horizontales(
                res.contribuciones.head(10), x="contribucion", y="variable",
                titulo="Contribución promedio por variable en el horizonte", x_label="Contribución (ton)",
            ),
            use_container_width=True, key=f"{key_prefix}_chart_sensibilidad",
        )
        st.caption(
            "Barras más largas = esa variable movió más el pronóstico. Las variables con prefijo del "
            "propio volumen (lag_, roll_mean_) reflejan inercia histórica; las de INEGI muestran el peso "
            "real del contexto macro."
        )

    df_fut = _tabla_futuro(res)
    if not df_fut.empty:
        seccion_titulo(f"Valores pronosticados — próximos {horizonte} meses")
        tabla_ejecutiva(df_fut, col_formatos={"FORECAST_TON": "{:,.1f}", "LOWER_90": "{:,.1f}", "UPPER_90": "{:,.1f}"},
                        key=f"{key_prefix}_tabla", height=270)

    if not res.backtest.empty:
        st.divider()
        seccion_titulo("Backtesting", "Comparación real vs. predicho")
        bt = res.backtest.copy()
        bt["ERROR_ABS"] = (bt["y_real"] - bt["y_pred"]).abs().round(1)
        bt["ERROR_PCT"] = (bt["ERROR_ABS"] / bt["y_real"].replace(0, np.nan) * 100).round(1)
        fig_bt = go.Figure()
        fig_bt.add_trace(go.Bar(x=bt["ds"], y=bt["y_real"], name="Real",
                                 marker_color=COLORS["primary"], opacity=0.8))
        fig_bt.add_trace(go.Scatter(x=bt["ds"], y=bt["y_pred"], name="Predicho",
                                     mode="lines+markers",
                                     line=dict(color=color_mod, width=2.5, dash="dot"),
                                     marker=dict(size=9)))
        fig_bt.update_layout(
            paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
            font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
            margin=dict(l=40, r=20, t=30, b=40), height=280,
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB", title="Toneladas"),
            legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"), barmode="overlay",
            transition=dict(duration=400, easing="cubic-in-out"),
        )
        st.plotly_chart(fig_bt, use_container_width=True, key=f"{key_prefix}_chart_backtest")


def _cache_key(prefix: str, modelo: str, horizonte: int, dim: str = "") -> str:
    return f"fc_com_{movimiento}_{prefix}_{modelo}_{horizonte}_{dim}"


def _get_or_compute(cache_key: str, fn):
    if cache_key not in st.session_state:
        with st.spinner("Calculando pronóstico..."):
            st.session_state[cache_key] = fn()
    return st.session_state[cache_key]


# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------
tab_total, tab_fraccion, tab_comparar = st.tabs(["Total", "Por fracción", "Comparar modelos"])

with tab_total:
    seccion_titulo("Volumen nacional total — fracciones TYASA", f"{horizonte} meses proyectados")
    if df_total.empty:
        st.warning("Sin datos de CANACERO para este movimiento.")
    else:
        ck = _cache_key("total", modelo_key, horizonte)
        res_total = _get_or_compute(
            ck, lambda: generar_forecast(
                df_total, horizonte, col_periodo="periodo_mes", col_val="volumen_total",
                modelo=modelo_key, df_exog=df_exog_inegi,
            )
        )
        _render_resultado(res_total, key_prefix="total")

with tab_fraccion:
    seccion_titulo("Pronóstico por fracción", f"Modelo: {MODELOS_DISPONIBLES[modelo_key]}")
    if df_fracciones.empty:
        st.warning("Sin datos de CANACERO por fracción para este movimiento.")
    else:
        opciones_fraccion = sorted(FRACCIONES_TYASA)
        etiquetas_fraccion = {
            f: f"{f} — {descripciones_fraccion.get(f, 'sin descripción')}" for f in opciones_fraccion
        }
        fraccion_sel = st.selectbox(
            "Fracción TYASA", opciones_fraccion, format_func=lambda f: etiquetas_fraccion[f],
            key="fc_com_fraccion",
        )
        df_f = filtrar_por_dimension(df_fracciones, "fraccion", fraccion_sel, col_periodo="periodo_mes", col_val="volumen_total")
        n_f = len(df_f)
        st.caption(f"Serie disponible: **{n_f} meses**")
        if n_f < 12:
            st.warning(f"Solo {n_f} meses disponibles para esta fracción — se requieren mínimo 12.")
        else:
            ck_f = _cache_key("frac", modelo_key, horizonte, fraccion_sel)
            res_f = _get_or_compute(
                ck_f, lambda: generar_forecast(
                    df_f, horizonte, col_periodo="periodo_mes", col_val="volumen_total",
                    modelo=modelo_key, df_exog=df_exog_inegi,
                )
            )
            _render_resultado(res_f, key_prefix="frac")

with tab_comparar:
    seccion_titulo("Comparación de Modelos", "Ejecuta los 4 modelos y compara MAPE, MAE y RMSE sobre el total")
    if df_total.empty:
        st.warning("Sin datos.")
    else:
        if st.button("Ejecutar comparación de los 4 modelos", key="fc_com_btn_comparar"):
            modelos_eval = ["ets", "sarima", "xgb", "naive"]
            resultados_comp = {}
            prog = st.progress(0)
            for i, mk in enumerate(modelos_eval):
                ck_c = _cache_key("comp", mk, horizonte)
                if ck_c not in st.session_state:
                    st.session_state[ck_c] = generar_forecast(
                        df_total, horizonte, col_periodo="periodo_mes", col_val="volumen_total", modelo=mk
                    )
                resultados_comp[mk] = st.session_state[ck_c]
                prog.progress((i + 1) / len(modelos_eval))
            prog.empty()

            rows = []
            for mk, r in resultados_comp.items():
                if r.error_msg:
                    rows.append({"Modelo": r.modelo, "MAE": "—", "MAPE": "—", "RMSE": "—"})
                else:
                    m = r.metricas
                    mape_v = m.get("MAPE (%)", float("nan"))
                    rows.append({"Modelo": MODELOS_DISPONIBLES[mk], "MAE": m.get("MAE", "—"),
                                 "MAPE": f"{mape_v:.1f}%" if not np.isnan(mape_v) else "—",
                                 "RMSE": m.get("RMSE", "—")})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            fig_comp = go.Figure()
            colores_comp = {"ets": COLORS["success"], "sarima": COLORS["secondary"],
                            "xgb": COLOR_SEQUENCE[1], "naive": COLORS["neutral"]}
            hist = resultados_comp["ets"].historico
            if not hist.empty:
                fig_comp.add_trace(go.Scatter(x=hist["ds"], y=hist["y"], name="Histórico",
                                               line=dict(color=COLORS["primary"], width=2.5),
                                               hovertemplate="%{x|%b %Y}: %{y:,.1f} ton<extra></extra>"))
            for mk, r in resultados_comp.items():
                if r.error_msg or r.forecast.empty:
                    continue
                fc_fut = r.forecast[r.forecast["ds"] > hist["ds"].max()]
                if fc_fut.empty:
                    continue
                fig_comp.add_trace(go.Scatter(x=fc_fut["ds"], y=fc_fut["yhat"], name=MODELOS_DISPONIBLES[mk],
                                               line=dict(color=colores_comp[mk], width=2, dash="dot"),
                                               mode="lines+markers", marker=dict(size=6)))
            fig_comp.update_layout(
                paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
                margin=dict(l=40, r=20, t=50, b=40), xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor="#E5E7EB", title="Toneladas"),
                legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center"),
                title=dict(text="Comparación de pronósticos — todos los modelos",
                           font=dict(size=14, color=COLORS["primary"]), x=0), height=420,
                transition=dict(duration=400, easing="cubic-in-out"),
            )
            st.plotly_chart(fig_comp, use_container_width=True, key="comparar_chart_modelos")
        else:
            st.info("Haz clic en el botón para comparar los 4 modelos.")

st.caption(
    "Datos: CANACERO SICEP · Fracciones del catálogo TYASA · Modelos: statsmodels / scikit-learn / xgboost"
)
