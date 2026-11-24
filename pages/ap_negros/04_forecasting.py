"""
04_forecasting.py — Forecasting de Demanda — Aceros Planos Negros.
Modelos: Holt-Winters ETS | SARIMA | XGBoost | Naive Estacional | Auto
"""

import os, sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from config import COLORS, COLOR_SEQUENCE, FORECAST_HORIZON_DEFAULT, FORECAST_HORIZON_MAX

from aceros_planos.negros.loaders import (
    load_gold_demanda_mensual_total,
    load_gold_demanda_mensual,
    load_serie_mensual_proceso,
    get_fecha_corte,
)
from aceros_planos.negros.analytics.forecasting import (
    generar_forecast,
    filtrar_por_dimension,
    MODELOS_DISPONIBLES,
)
from aceros_planos.negros.analytics.escenarios import VARIABLES as VARIABLES_ESC, efecto_pct, estimar, preajuste, simular
from aceros_planos.negros.loaders_contexto import load_indicadores_escenarios
from core.components.aciertos import aviso_confiabilidad, render_aciertos
from core.seleccion_modelos import generar
from core.components.kpi_cards import seccion_titulo
from core.components.filters import sidebar_header
from core.components.tables import tabla_ejecutiva, tabla_metricas

# Sidebar
sidebar_header("Parametros")
horizonte = st.sidebar.slider("Horizonte (meses)", min_value=1,
                               max_value=FORECAST_HORIZON_MAX, value=FORECAST_HORIZON_DEFAULT, key="fc_horizonte")
modelo_key = st.sidebar.selectbox("Modelo de pronostico", options=list(MODELOS_DISPONIBLES.keys()),
                                   format_func=lambda k: MODELOS_DISPONIBLES[k], index=0, key="fc_modelo")
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"""
    <div style='font-size:0.78rem;color:{COLORS["text_light"]};'>
    <b>Guia de modelos</b><br><br>
    ETS — Holt-Winters. Ideal para demanda estable con estacionalidad anual.<br><br>
    SARIMA — Clasico estadistico. Bueno cuando hay tendencia clara.<br><br>
    XGBoost — Machine Learning con rezagos. Captura patrones no lineales.<br><br>
    Naive — Baseline: igual al mismo mes del anio pasado.<br><br>
    Combinado — Promedio de ETS y SARIMA.<br><br>
    Automatico — Usa el modelo que mejor ha acertado en esta serie.
    </div>
    """,
    unsafe_allow_html=True,
)

with st.spinner("Cargando datos..."):
    df_total   = load_gold_demanda_mensual_total()
    df_mensual = load_gold_demanda_mensual()
    df_proceso = load_serie_mensual_proceso()
    fecha_corte = get_fecha_corte()

# Opciones comunes de pronóstico: se excluye el último mes si está incompleto,
# los meses sin embarques cuentan como 0 t y los cuatro modelos se validan con
# los mismos últimos 6 meses (comparación justa en el modo automático).
_FC_OPC = dict(fecha_corte=fecha_corte, ventana_prueba=6, rellenar_huecos=True)
_FC_OPC_OM = dict(fecha_corte=fecha_corte, rellenar_huecos=True)  # validación de origen móvil

st.markdown(
    f"""
    <h2 style='color:{COLORS["primary"]};margin-bottom:0;'>Forecasting de Demanda</h2>
    <p style='color:{COLORS["text_light"]};'>
        Modelo: <b>{MODELOS_DISPONIBLES[modelo_key]}</b> &nbsp;&middot;&nbsp; Horizonte: <b>{horizonte} meses</b>
    </p>
    """,
    unsafe_allow_html=True,
)
st.divider()


def _colores_modelo(nombre: str) -> str:
    if "ETS" in nombre or "Holt" in nombre:
        return COLORS["success"]
    if "XGB" in nombre:
        return COLOR_SEQUENCE[1]
    if "SARIMA" in nombre or "ARIMA" in nombre:
        return COLORS["secondary"]
    return COLORS["neutral"]


def _grafico_forecast(resultado, titulo="") -> go.Figure:
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

    fig.add_trace(go.Scatter(x=hist_df["ds"], y=hist_df["y"], name="Historico",
                              line=dict(color=COLORS["primary"], width=2.5),
                              hovertemplate="%{x|%b %Y}<br>Real: %{y:,.1f} ton<extra></extra>"))

    if not fc_fut.empty:
        fig.add_trace(go.Scatter(x=fc_fut["ds"], y=fc_fut["yhat"],
                                  name=f"Pronostico ({horizonte}m)",
                                  line=dict(color=color_fc, width=2.5, dash="dot"),
                                  mode="lines+markers", marker=dict(size=7),
                                  hovertemplate="%{x|%b %Y}<br>Pronostico: %{y:,.1f} ton<extra></extra>"))

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


def _render_resultado(res, key_prefix: str):
    if res.error_msg:
        st.error(f"Error: {res.error_msg}")
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
        if res.metricas:
            tabla_metricas(res.metricas, titulo="Metricas de backtesting")

    aviso_confiabilidad(res)
    fig = _grafico_forecast(res, titulo=f"Historico + Pronostico {horizonte} meses")
    st.plotly_chart(fig, width="stretch")

    df_fut = _tabla_futuro(res)
    if not df_fut.empty:
        seccion_titulo(f"Valores pronosticados - proximos {horizonte} meses")
        tabla_ejecutiva(df_fut, col_formatos={"FORECAST_TON": "{:,.1f}", "LOWER_90": "{:,.1f}", "UPPER_90": "{:,.1f}"},
                        key=f"{key_prefix}_tabla", height=270)

    if not res.backtest.empty:
        st.divider()
        seccion_titulo("Backtesting", "Comparacion real vs predicho")
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
        )
        st.plotly_chart(fig_bt, width="stretch")


def _cache_key(prefix: str, modelo: str, horizonte: int, dim: str = "") -> str:
    # La fecha de corte entra en la llave: al cargar datos nuevos se recalcula.
    return f"fc_{prefix}_{modelo}_{horizonte}_{dim}_{fecha_corte}"


def _get_or_compute(cache_key: str, fn):
    if cache_key not in st.session_state:
        with st.spinner("Calculando pronostico..."):
            st.session_state[cache_key] = fn()
    return st.session_state[cache_key]


_MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


@st.cache_data(ttl=3600, show_spinner=False)
def _modelo_escenarios(venta: pd.Series, indicadores: pd.DataFrame, _corte: str):
    return estimar(venta, indicadores)


tab1, tab2, tab6, tab3, tab4, tab5 = st.tabs(["Demanda Total", "Comparar Modelos", "¿Qué tan bien acierta?",
                                              "Por Proceso", "Por Familia", "Simulador de escenarios"])

with tab1:
    seccion_titulo("Demanda Total", f"{horizonte} meses proyectados")
    if df_total.empty:
        st.warning("Sin datos de demanda total.")
    else:
        ck = _cache_key("total", modelo_key, horizonte)
        res_total = _get_or_compute(ck, lambda: generar(df_total, horizonte, modelo_key, "NEGROS|TOTAL", **_FC_OPC))
        _render_resultado(res_total, key_prefix="total")

with tab2:
    seccion_titulo("Comparacion de Modelos", "Ejecuta los 4 modelos y compara MAPE, MAE y RMSE")
    if df_total.empty:
        st.warning("Sin datos.")
    else:
        if st.button("Ejecutar comparacion de los 4 modelos", key="btn_comparar"):
            modelos_eval = ["ets", "sarima", "xgb", "naive"]
            resultados_comp = {}
            prog = st.progress(0)
            for i, mk in enumerate(modelos_eval):
                ck_c = _cache_key("comp", mk, horizonte)
                if ck_c not in st.session_state:
                    st.session_state[ck_c] = generar_forecast(df_total, horizonte, modelo=mk, **_FC_OPC)
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
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

            fig_comp = go.Figure()
            colores_comp = {"ets": COLORS["success"], "sarima": COLORS["secondary"],
                            "xgb": COLOR_SEQUENCE[1], "naive": COLORS["neutral"]}
            hist = resultados_comp["ets"].historico
            if not hist.empty:
                fig_comp.add_trace(go.Scatter(x=hist["ds"], y=hist["y"], name="Historico",
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
                title=dict(text="Comparacion de pronosticos — todos los modelos",
                           font=dict(size=14, color=COLORS["primary"]), x=0), height=420,
            )
            st.plotly_chart(fig_comp, width="stretch")
        else:
            st.info("Haz clic en el boton para comparar los 4 modelos.")

with tab6:
    seccion_titulo("¿Qué tan bien acierta?", "Pronósticos hechos desde meses pasados vs. la venta real")
    render_aciertos(df_total, key=f"fc_origen_movil_{fecha_corte}", referencia="lo que se vendió", **_FC_OPC_OM)

with tab3:
    seccion_titulo("Pronostico por Proceso", f"Modelo: {MODELOS_DISPONIBLES[modelo_key]}")
    if df_proceso.empty:
        st.warning("Sin datos de serie por proceso.")
    else:
        procesos = sorted(df_proceso["PROCESO"].dropna().unique().tolist())
        proc_sel = st.selectbox("Proceso:", options=procesos, key="fc_proc")
        if proc_sel:
            df_p = filtrar_por_dimension(df_proceso, "PROCESO", proc_sel)
            n_p  = len(df_p)
            st.caption(f"Serie disponible: **{n_p} meses**")
            if n_p < 12:
                st.warning(f"Solo {n_p} meses disponibles — se requieren minimo 12.")
            else:
                ck_p = _cache_key("proc", modelo_key, horizonte, proc_sel)
                res_p = _get_or_compute(ck_p, lambda: generar(df_p, horizonte, modelo_key, f"NEGROS|PROCESO|{proc_sel}", **_FC_OPC))
                _render_resultado(res_p, key_prefix="proc")

with tab4:
    seccion_titulo("Pronostico por Familia de Producto", f"Modelo: {MODELOS_DISPONIBLES[modelo_key]}")
    excluir_fc = {"OTROS", "OTHER", "N/D", "SIN CLASIFICAR", "S/C"}
    if df_mensual.empty or "PRODUCTO_LIMPIO" not in df_mensual.columns:
        st.warning("Sin datos granulares por producto.")
    else:
        prods = sorted([p for p in df_mensual["PRODUCTO_LIMPIO"].dropna().unique()
                        if str(p).upper() not in excluir_fc])
        prod_sel = st.selectbox("Producto:", options=prods, key="fc_prod")
        if prod_sel:
            df_pr = filtrar_por_dimension(df_mensual, "PRODUCTO_LIMPIO", prod_sel)
            n_pr  = len(df_pr)
            st.caption(f"Serie disponible: **{n_pr} meses**")
            if n_pr < 12:
                st.warning(f"Solo {n_pr} meses — se requieren minimo 12.")
            else:
                ck_pr = _cache_key("prod", modelo_key, horizonte, prod_sel)
                res_pr = _get_or_compute(ck_pr, lambda: generar(df_pr, horizonte, modelo_key, f"NEGROS|PRODUCTO|{prod_sel}", **_FC_OPC))
                _render_resultado(res_pr, key_prefix="prod")

with tab5:
    seccion_titulo("Simulador de escenarios", "¿Qué pasa con la venta si cambia el mercado?")
    st.caption("Mueve los indicadores y mira cómo cambiaría la venta. La sensibilidad de cada uno "
               "se midió con la historia de Negros, no es un supuesto.")

    if df_total.empty:
        st.warning("Sin datos para generar pronóstico base.")
    else:
        ck_base = _cache_key("total", modelo_key, horizonte)
        res_base = _get_or_compute(ck_base, lambda: generar(df_total, horizonte, modelo_key, "NEGROS|TOTAL", **_FC_OPC))
        hist = res_base.historico
        indicadores = load_indicadores_escenarios()

        if res_base.error_msg or hist.empty or indicadores.empty:
            st.error("No se pudo preparar el simulador (sin pronóstico base o sin indicadores de INEGI).")
        else:
            venta_hist = hist.set_index("ds")["y"]
            mod = _modelo_escenarios(venta_hist, indicadores, str(fecha_corte))
            if mod.error_msg:
                st.warning(mod.error_msg)
            else:
                fc_fut = res_base.forecast[res_base.forecast["ds"] > hist["ds"].max()].copy()
                meses = list(fc_fut["ds"])
                coefs = mod.coefs.set_index("clave")
                actual = mod.actual.set_index("clave") if not mod.actual.empty else pd.DataFrame()

                def _aplicar_preajuste():
                    nombre = {"Sin cambios": "base", "Como van hoy": "actual",
                              "Adverso": "adverso", "Positivo": "positivo"}[st.session_state["esc_preajuste"]]
                    for clave, pct in preajuste(mod, nombre).items():
                        st.session_state[f"esc_{clave}"] = float(max(-30.0, min(30.0, pct)))
                    st.session_state["esc_propio"] = 0.0

                for v in VARIABLES_ESC:
                    st.session_state.setdefault(f"esc_{v.clave}", 0.0)
                st.session_state.setdefault("esc_propio", 0.0)

                st.radio("Punto de partida", ["Sin cambios", "Como van hoy", "Adverso", "Positivo"],
                         horizontal=True, key="esc_preajuste", on_change=_aplicar_preajuste,
                         help="Adverso y Positivo usan los peores y mejores años de cada indicador desde 2022.")

                caja_kpis = st.container()
                col_ctrl, col_res = st.columns([1, 1], gap="large")
                cambios = {}
                with col_ctrl:
                    for v in VARIABLES_ESC:
                        r = coefs.loc[v.clave]
                        cambios[v.clave] = st.slider(f"{v.etiqueta} (% vs año anterior)", -30.0, 30.0,
                                                     step=0.5, key=f"esc_{v.clave}")
                        hoy = ""
                        if v.clave in actual.index:
                            a = actual.loc[v.clave]
                            hoy = f" · hoy va {a['pct']:+.1f} % ({_MESES_ES[a['fecha'].month - 1]} {a['fecha'].year})"
                        certeza = "" if r["claro"] else " · efecto incierto"
                        st.caption(f"Si sube 1 %, la venta cambia {r['beta']:+.1f} %{certeza}{hoy}")
                    propio = st.slider("Ajuste propio (%)", -30.0, 30.0, step=1.0, key="esc_propio",
                                       help="Lo que la historia no mide: aranceles nuevos, precio del HRC, "
                                            "un cliente grande que entra o sale…")

                ef = efecto_pct(mod, cambios, propio)
                sim = simular(mod, venta_hist, meses, cambios, propio)
                ton_sim = float(sim["ton"].sum())
                ton_prev = float(sim["mismo_mes_anio_previo"].sum())
                ton_base = float(fc_fut["yhat"].sum())
                vs_pron = (ton_sim / ton_base - 1) * 100 if ton_base else 0.0

                with caja_kpis:
                    color = COLORS["success"] if ef["total"] >= 0 else COLORS["danger"]
                    _caja = (f"background:{COLORS['surface']};border:1px solid #E5E7EB;"
                             f"border-radius:8px;padding:12px;")
                    st.html(f"""
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:4px 0 14px;">
                      <div style="{_caja}border-left:4px solid {color};">
                        <div style="font-size:11px;font-weight:700;color:#64748B;">VENTA DEL ESCENARIO</div>
                        <div style="font-size:20px;font-weight:800;color:{color};">{ton_sim:,.0f} t</div>
                        <div style="font-size:11px;color:#64748B;">próximos {len(meses)} meses</div></div>
                      <div style="{_caja}">
                        <div style="font-size:11px;font-weight:700;color:#64748B;">VS. AÑO ANTERIOR</div>
                        <div style="font-size:20px;font-weight:800;color:{color};">{ef['total']:+.1f} %</div>
                        <div style="font-size:11px;color:#64748B;">mismos meses: {ton_prev:,.0f} t</div></div>
                      <div style="{_caja}">
                        <div style="font-size:11px;font-weight:700;color:#64748B;">VS. PRONÓSTICO</div>
                        <div style="font-size:20px;font-weight:800;color:{COLORS['primary']};">{vs_pron:+.1f} %</div>
                        <div style="font-size:11px;color:#64748B;">pronóstico: {ton_base:,.0f} t</div></div>
                    </div>""")

                with col_res:
                    # De dónde sale el cambio
                    etiquetas = ["Tendencia propia"] + [v.corto or v.etiqueta for v in VARIABLES_ESC] + ["Ajuste propio"]
                    valores = [ef["tendencia"]] + [ef["aportes"][v.clave] for v in VARIABLES_ESC] + [ef["ajuste_propio"]]
                    fig_ap = go.Figure(go.Bar(
                        y=etiquetas[::-1], x=valores[::-1], orientation="h",
                        marker_color=[COLORS["success"] if x >= 0 else COLORS["danger"] for x in valores[::-1]],
                        text=[f"{x:+.1f} %" for x in valores[::-1]], textposition="outside", cliponaxis=False,
                        hovertemplate="%{y}: %{x:+.1f} %<extra></extra>",
                    ))
                    lim = max(5.0, max(abs(x) for x in valores) * 2.0)
                    fig_ap.update_layout(
                        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"], size=12),
                        margin=dict(l=10, r=30, t=40, b=20), height=320, showlegend=False,
                        xaxis=dict(range=[-lim, lim], zeroline=True, zerolinecolor="#94A3B8",
                                   showgrid=False, showticklabels=False),
                        title=dict(text="De dónde sale el cambio vs. año anterior",
                                   font=dict(size=13, color=COLORS["primary"]), x=0),
                    )
                    st.plotly_chart(fig_ap, width="stretch", config={"displayModeBar": False})

                fig_sc = go.Figure()
                h24 = hist[hist["ds"] >= hist["ds"].max() - pd.DateOffset(months=24)]
                fig_sc.add_trace(go.Scatter(
                    x=pd.concat([sim["ds"], sim["ds"][::-1]]), y=pd.concat([sim["hi"], sim["lo"][::-1]]),
                    fill="toself", fillcolor="rgba(74,123,167,0.13)", line=dict(color="rgba(0,0,0,0)"),
                    name="Rango probable (80 %)", hoverinfo="skip"))
                fig_sc.add_trace(go.Scatter(x=h24["ds"], y=h24["y"], name="Venta real",
                                            line=dict(color=COLORS["primary"], width=2.5),
                                            hovertemplate="%{x|%b %Y}: %{y:,.0f} t<extra></extra>"))
                fig_sc.add_trace(go.Scatter(x=fc_fut["ds"], y=fc_fut["yhat"], name="Pronóstico",
                                            line=dict(color=COLORS["neutral"], width=2, dash="dot"),
                                            hovertemplate="%{x|%b %Y}: %{y:,.0f} t<extra></extra>"))
                fig_sc.add_trace(go.Scatter(x=sim["ds"], y=sim["ton"], name="Escenario", mode="lines+markers",
                                            line=dict(color=COLORS["secondary"], width=2.5),
                                            hovertemplate="%{x|%b %Y}: %{y:,.0f} t<extra></extra>"))
                fig_sc.update_layout(
                    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
                    margin=dict(l=40, r=20, t=20, b=40), height=360,
                    xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB", title="Toneladas"),
                    legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
                )
                st.plotly_chart(fig_sc, width="stretch", config={"displayModeBar": False})

                with st.expander("¿Cómo se calcula?"):
                    st.markdown(
                        f"Cada mes del escenario = venta del mismo mes del año anterior × el cambio que "
                        f"resulta de los indicadores. La sensibilidad se midió con {mod.n} meses "
                        f"({_MESES_ES[mod.desde.month - 1]} {mod.desde.year} – {_MESES_ES[mod.hasta.month - 1]} "
                        f"{mod.hasta.year}); los indicadores explican {mod.r2 * 100:.0f} % de los cambios "
                        f"de la venta. El resto depende de cada cliente, por eso el rango es amplio.")
                    tabla = pd.DataFrame({
                        "Indicador": mod.coefs["etiqueta"],
                        "Si sube 1 %": mod.coefs["beta"].map(lambda b: f"{b:+.1f} %"),
                        "Rango": [f"{lo:+.1f} a {hi:+.1f} %" for lo, hi in zip(mod.coefs["lo"], mod.coefs["hi"])],
                        "Tarda": mod.coefs["rezago"].map(lambda r: f"{r} mes" + ("es" if r > 1 else "")),
                        "Efecto": mod.coefs["claro"].map({True: "claro", False: "incierto"}),
                        "Fuente": mod.coefs["fuente"],
                    })
                    st.dataframe(tabla, hide_index=True, width="stretch")
                    st.caption("Precio del HRC y tipo de cambio: solo hay historia desde 2024, aún no alcanza "
                               "para medir su efecto. Construcción no mostró relación con la venta. "
                               "Para esos casos usa el ajuste propio.")
