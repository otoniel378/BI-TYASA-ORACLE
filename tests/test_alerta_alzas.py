"""Pruebas de mercado_fastmarkets/alerta_alzas.py (sin Oracle ni red)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mercado_fastmarkets.alerta_alzas import agregar_rango, construir_panel, metricas, semaforo  # noqa: E402


def _precios() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2000-01-01", periods=120, freq="MS")
    return pd.DataFrame({
        s: 100 * np.exp(np.cumsum(rng.normal(0, 0.06, len(idx)))) for s in ("A", "B")
    }, index=idx)


def test_semaforo_umbrales():
    assert [semaforo(p) for p in (0.05, 0.20, 0.6)] == ["Verde", "Amarillo", "Amarillo"]
    assert semaforo(0.05, arriba=True) == "Amarillo" and semaforo(0.20, arriba=True) == "Rojo"


def test_etiqueta_es_alza_mayor_a_15pct_en_3_meses_y_sin_futuro_es_nan():
    precios = _precios()
    panel = construir_panel(precios, pd.DataFrame())
    a = panel[panel["serie"] == "A"].set_index("fecha")
    t = a.index[20]
    esperado = precios["A"].loc[t + pd.DateOffset(months=3)] / precios["A"].loc[t] - 1 > 0.15
    assert a.loc[t, "y"] == float(esperado)
    assert a["y"].iloc[-3:].isna().all()          # los últimos 3 meses aún no tienen resultado
    assert {"es_A", "es_B"} <= set(panel.columns)


def test_metricas_cuenta_episodio_detectado_a_tiempo():
    fechas = pd.date_range("2010-01-01", periods=12, freq="MS")
    y = [0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0]
    prob = [0.0, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # aviso 2 meses antes
    oos = pd.DataFrame({"fecha": fechas, "serie": "A", "prob": prob, "y": y, "alza_fut": 0.0})
    m = metricas(oos).set_index("serie").loc["A"]
    assert m["episodios"] == 1 and m["detectados"] == 1


def test_agregar_rango_marca_precio_arriba_y_semaforo():
    precios = _precios()
    precios.index.name = "fecha"
    precios.iloc[-1, 0] = precios.iloc[-2, 0] * 5            # salto enorme el último mes en A
    filas = pd.DataFrame({"serie": ["A", "A", "B"], "fecha": [precios.index[-1], precios.index[-2], precios.index[-1]],
                          "prob": [0.5, 0.05, 0.05]})
    out = agregar_rango(filas, precios).set_index(["serie", "fecha"])
    assert out.loc[("A", precios.index[-1]), "arriba"] and out.loc[("A", precios.index[-1]), "semaforo"] == "Rojo"
    assert out.loc[("B", precios.index[-1]), "semaforo"] == "Verde"
