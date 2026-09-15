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
)
from aceros_planos.negros.analytics.forecasting import (
    generar_forecast,
    filtrar_por_dimension,
    MODELOS_DISPONIBLES,
)
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
    Auto — Prueba los 4 y elige el de menor MAPE en backtesting.
    </div>
    """,
    unsafe_allow_html=True,
)

with st.spinner("Cargando datos..."):
    df_total   = load_gold_demanda_mensual_total()
    df_mensual = load_gold_demanda_mensual()
    df_proceso = load_serie_mensual_proceso()

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
    return f"fc_{prefix}_{modelo}_{horizonte}_{dim}"


def _get_or_compute(cache_key: str, fn):
    if cache_key not in st.session_state:
        with st.spinner("Calculando pronostico..."):
            st.session_state[cache_key] = fn()
    return st.session_state[cache_key]


tab1, tab2, tab3, tab4, tab5 = st.tabs(["Demanda Total", "Comparar Modelos", "Por Proceso", "Por Familia", "Escenarios"])

with tab1:
    seccion_titulo("Demanda Total", f"{horizonte} meses proyectados")
    if df_total.empty:
        st.warning("Sin datos de demanda total.")
    else:
        ck = _cache_key("total", modelo_key, horizonte)
        res_total = _get_or_compute(ck, lambda: generar_forecast(df_total, horizonte, modelo=modelo_key))
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
                    st.session_state[ck_c] = generar_forecast(df_total, horizonte, modelo=mk)
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
                res_p = _get_or_compute(ck_p, lambda: generar_forecast(df_p, horizonte, modelo=modelo_key))
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
                res_pr = _get_or_compute(ck_pr, lambda: generar_forecast(df_pr, horizonte, modelo=modelo_key))
                _render_resultado(res_pr, key_prefix="prod")

with tab5:
    seccion_titulo("Escenarios de Demanda", "Proyecciones ajustadas por supuestos del mercado")
    st.markdown(
        "<p style='color:#64748B;font-size:0.85rem;'>Aplica factores de ajuste sobre el pronóstico base "
        "para simular escenarios Adverso, Base y Positivo.</p>",
        unsafe_allow_html=True,
    )

    if df_total.empty:
        st.warning("Sin datos para generar pronóstico base.")
    else:
        # Cargar/computar pronóstico base
        ck_base = _cache_key("total", modelo_key, horizonte)
        res_base = _get_or_compute(ck_base, lambda: generar_forecast(df_total, horizonte, modelo=modelo_key))

        if res_base.error_msg or res_base.forecast.empty:
            st.error("No se pudo generar el pronóstico base.")
        else:
            hist   = res_base.historico
            fc_fut = res_base.forecast[res_base.forecast["ds"] > hist["ds"].max()].copy()

            if fc_fut.empty:
                st.info("Sin períodos futuros en el pronóstico.")
            else:
                ton_base = float(fc_fut["yhat"].sum())

                st.markdown("#### Supuestos por escenario")

                _T2 = "#64748B"
                col_adv, col_b, col_pos = st.columns(3)

                with col_adv:
                    st.markdown(f"<div style='text-align:center;font-weight:700;color:#DC2626;"
                                f"font-size:13px;margin-bottom:6px;'>Escenario Adverso</div>",
                                unsafe_allow_html=True)
                    pct_adv_mkt  = st.slider("Mercado acero (% ajuste)", -30, 0, -10,
                                              step=5, key="esc_adv_mkt")
                    pct_adv_tipo = st.slider("Tipo de cambio (% ajuste)", -10, 10, -5,
                                              step=5, key="esc_adv_tipo")
                    pct_adv_dem  = st.slider("Demanda industria (% ajuste)", -20, 0, -8,
                                              step=2, key="esc_adv_dem")

                with col_b:
                    st.markdown(f"<div style='text-align:center;font-weight:700;color:#D97706;"
                                f"font-size:13px;margin-bottom:6px;'>Escenario Base</div>",
                                unsafe_allow_html=True)
                    pct_b_mkt  = st.slider("Mercado acero (% ajuste)", -10, 10, 0,
                                            step=5, key="esc_b_mkt", disabled=True)
                    pct_b_tipo = st.slider("Tipo de cambio (% ajuste)", -5, 5, 0,
                                            step=5, key="esc_b_tipo", disabled=True)
                    pct_b_dem  = st.slider("Demanda industria (% ajuste)", -5, 5, 0,
                                            step=1, key="esc_b_dem", disabled=True)

                with col_pos:
                    st.markdown(f"<div style='text-align:center;font-weight:700;color:#16A34A;"
                                f"font-size:13px;margin-bottom:6px;'>Escenario Positivo</div>",
                                unsafe_allow_html=True)
                    pct_pos_mkt  = st.slider("Mercado acero (% ajuste)", 0, 30, 10,
                                              step=5, key="esc_pos_mkt")
                    pct_pos_tipo = st.slider("Tipo de cambio (% ajuste)", 0, 15, 5,
                                              step=5, key="esc_pos_tipo")
                    pct_pos_dem  = st.slider("Demanda industria (% ajuste)", 0, 20, 8,
                                              step=2, key="esc_pos_dem")

                # Factor neto = promedio ponderado de los 3 ajustes
                def _factor(mkt, tipo, dem):
                    return 1.0 + (mkt * 0.5 + tipo * 0.2 + dem * 0.3) / 100

                f_adv = _factor(pct_adv_mkt, pct_adv_tipo, pct_adv_dem)
                f_b   = 1.0
                f_pos = _factor(pct_pos_mkt, pct_pos_tipo, pct_pos_dem)

                ton_adv = ton_base * f_adv
                ton_pos = ton_base * f_pos

                # Gráfico de barras comparativo
                st.markdown("#### Proyección total del período (ton)")
                escenarios = ["Adverso", "Base", "Positivo"]
                toneladas  = [ton_adv, ton_base, ton_pos]
                colores    = [COLORS["danger"], COLORS["warning"], COLORS["success"]]

                fig_esc = go.Figure(go.Bar(
                    x=escenarios, y=toneladas,
                    marker_color=colores,
                    text=[f"{t:,.0f} ton" for t in toneladas],
                    textposition="outside",
                    textfont=dict(size=12, color=COLORS["text"]),
                    hovertemplate="%{x}<br>Pronóstico: %{y:,.1f} ton<extra></extra>",
                ))
                fig_esc.update_layout(
                    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
                    margin=dict(l=40, r=20, t=20, b=40), showlegend=False, height=320,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(gridcolor="#E5E7EB", title="Toneladas totales proyectadas",
                               range=[0, max(toneladas) * 1.18]),
                )
                st.plotly_chart(fig_esc, width="stretch", config={"displayModeBar": False})

                # Cards de resumen
                _ER = "#DC2626"; _WA = "#D97706"; _OK2 = "#16A34A"; _T1 = "#0F172A"
                st.html(f"""
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:4px;">
                  <div style="background:#FEE2E2;border-radius:10px;padding:14px;border-left:4px solid {_ER};">
                    <div style="font-size:10px;font-weight:700;color:#991B1B;text-transform:uppercase;
                         margin-bottom:4px;">Adverso</div>
                    <div style="font-size:20px;font-weight:800;color:{_ER};">{ton_adv:,.0f} ton</div>
                    <div style="font-size:11px;color:#991B1B;margin-top:3px;">
                      {(f_adv - 1) * 100:+.1f}% vs base
                    </div>
                  </div>
                  <div style="background:#FEF3C7;border-radius:10px;padding:14px;border-left:4px solid {_WA};">
                    <div style="font-size:10px;font-weight:700;color:#92400E;text-transform:uppercase;
                         margin-bottom:4px;">Base</div>
                    <div style="font-size:20px;font-weight:800;color:{_WA};">{ton_base:,.0f} ton</div>
                    <div style="font-size:11px;color:#92400E;margin-top:3px;">
                      Modelo: {MODELOS_DISPONIBLES[modelo_key]}
                    </div>
                  </div>
                  <div style="background:#DCFCE7;border-radius:10px;padding:14px;border-left:4px solid {_OK2};">
                    <div style="font-size:10px;font-weight:700;color:#166534;text-transform:uppercase;
                         margin-bottom:4px;">Positivo</div>
                    <div style="font-size:20px;font-weight:800;color:{_OK2};">{ton_pos:,.0f} ton</div>
                    <div style="font-size:11px;color:#166534;margin-top:3px;">
                      {(f_pos - 1) * 100:+.1f}% vs base
                    </div>
                  </div>
                </div>""")

                # Serie temporal por escenario
                st.markdown("#### Evolución mensual por escenario")
                fig_sc_ts = go.Figure()
                fig_sc_ts.add_trace(go.Scatter(
                    x=hist["ds"], y=hist["y"], name="Histórico",
                    line=dict(color=COLORS["primary"], width=2),
                    hovertemplate="%{x|%b %Y}: %{y:,.1f} ton<extra></extra>",
                ))
                for nombre, factor, color in [
                    ("Adverso",  f_adv, COLORS["danger"]),
                    ("Base",     f_b,   COLORS["warning"]),
                    ("Positivo", f_pos, COLORS["success"]),
                ]:
                    fig_sc_ts.add_trace(go.Scatter(
                        x=fc_fut["ds"], y=fc_fut["yhat"] * factor,
                        name=nombre, mode="lines+markers",
                        line=dict(color=color, width=2, dash="dot"),
                        marker=dict(size=6),
                        hovertemplate=f"{nombre}: %{{x|%b %Y}}<br>%{{y:,.1f}} ton<extra></extra>",
                    ))
                corte = str(hist["ds"].max())
                fig_sc_ts.add_shape(type="line", x0=corte, x1=corte, y0=0, y1=1,
                                    xref="x", yref="paper",
                                    line=dict(color=COLORS["neutral"], width=1.5, dash="dot"))
                fig_sc_ts.update_layout(
                    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
                    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
                    margin=dict(l=40, r=20, t=20, b=40), height=340,
                    xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB", title="Toneladas"),
                    legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center"),
                )
                st.plotly_chart(fig_sc_ts, width="stretch",
                                config={"displayModeBar": False})
