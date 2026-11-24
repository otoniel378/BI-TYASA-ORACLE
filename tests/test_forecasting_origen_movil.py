"""Pruebas de la validación de origen móvil y el modelo combinado (sin Oracle)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.forecasting import (  # noqa: E402
    backtest_origen_movil, generar_forecast, resumen_origen_movil,
)


def _demanda(n: int = 48, seed: int = 0) -> pd.DataFrame:
    """Demanda mensual con estacionalidad anual, desde ene-2022 (cerrada antes del mes en curso)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    y = 1000 + 5 * t + 200 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 30, n)
    return pd.DataFrame({"PERIODO": pd.date_range("2022-01-01", periods=n, freq="MS"), "PESO_TON": y})


def test_cada_horizonte_tiene_al_menos_n_origenes():
    bt = backtest_origen_movil(_demanda(), horizonte=3, n_origenes=4, modelos=("naive", "ets"))
    conteo = bt.groupby(["modelo", "h"]).size()
    assert set(bt["h"]) == {1, 2, 3}
    assert (conteo >= 4).all()


def test_no_usa_datos_posteriores_al_origen():
    bt = backtest_origen_movil(_demanda(), horizonte=3, n_origenes=3, modelos=("naive",))
    assert (bt["ds"] > bt["origen"]).all()
    meses = (bt["ds"].dt.year - bt["origen"].dt.year) * 12 + (bt["ds"].dt.month - bt["origen"].dt.month)
    assert (meses == bt["h"]).all()


def test_naive_estacional_repite_el_mismo_mes_del_anio_anterior():
    df = _demanda()
    bt = backtest_origen_movil(df, horizonte=1, n_origenes=2, modelos=("naive",))
    real = df.set_index("PERIODO")["PESO_TON"]
    for ds, pred in zip(bt["ds"], bt["y_pred"]):
        assert np.isclose(pred, real[ds - pd.DateOffset(years=1)])


def test_resumen_mide_mejora_contra_naive():
    bt = backtest_origen_movil(_demanda(), horizonte=2, n_origenes=4, modelos=("naive", "ets"))
    res = resumen_origen_movil(bt)
    assert (res.loc[res["modelo"] == "naive", "mejora_vs_naive (%)"] == 0).all()
    assert {"MAPE (%)", "WAPE (%)", "cortes"} <= set(res.columns)


def test_combo_promedia_ets_y_sarima():
    df = _demanda()
    kw = dict(ventana_prueba=4)
    r_c = generar_forecast(df, 3, modelo="combo", **kw)
    r_e = generar_forecast(df, 3, modelo="ets", **kw)
    r_s = generar_forecast(df, 3, modelo="sarima", **kw)
    fut = lambda r: r.forecast[r.forecast["ds"] > r.historico["ds"].max()]["yhat"].to_numpy()  # noqa: E731
    assert r_c.modelo.startswith("Combinado")
    assert np.allclose(fut(r_c), (fut(r_e) + fut(r_s)) / 2)
    assert len(r_c.backtest) == 4 and "MAPE (%)" in r_c.metricas


def test_auto_usa_la_seleccion_precalculada():
    r = generar_forecast(_demanda(), 3, modelo="auto", seleccion="naive", ventana_prueba=4)
    assert r.modelo.startswith("Naive") and "precalculado" in r.modelo


def test_auto_sin_seleccion_elige_el_menor_error_de_origen_movil():
    from core.forecasting import error_global, seleccionar_modelo, CANDIDATOS_AUTO
    df = _demanda()
    clave, wape = seleccionar_modelo(df)
    bt = backtest_origen_movil(df, horizonte=6, n_origenes=6, modelos=CANDIDATOS_AUTO)
    assert clave == error_global(bt).idxmin()
    assert list(wape.index) == list(wape.sort_values().index)


def test_backtest_combo_es_el_promedio_de_ets_y_sarima():
    bt = backtest_origen_movil(_demanda(), horizonte=2, n_origenes=2, modelos=("combo", "ets", "sarima"))
    p = bt.pivot_table(index=["origen", "h"], columns="modelo", values="y_pred")
    assert np.allclose(p["combo"], (p["ets"] + p["sarima"]) / 2)


def test_firma_cambia_si_cambian_los_datos():
    from core.forecasting import firma_serie
    df = _demanda()
    otra = df.copy()
    otra.loc[otra.index[-1], "PESO_TON"] += 100
    assert firma_serie(df) != firma_serie(otra)
    assert firma_serie(df) == firma_serie(df.copy())


def test_ruta_anterior_apunta_al_motor_comun():
    # El motor vive en core/forecasting.py; la ruta de Planos se conserva para código de otros equipos.
    from aceros_planos.negros.analytics import forecasting as viejo
    from core import forecasting as comun
    assert viejo is comun and viejo.generar_forecast is comun.generar_forecast
