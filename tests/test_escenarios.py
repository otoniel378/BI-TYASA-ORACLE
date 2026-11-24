"""Pruebas del simulador de escenarios (aceros_planos/negros/analytics/escenarios.py), sin Oracle."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aceros_planos.negros.analytics import escenarios as E  # noqa: E402

VARS = (E.Variable("A", "Indicador A", "prueba", 1, "A"),
        E.Variable("B", "Indicador B", "prueba", 0, "B"))


def _datos(beta_a=3.0, beta_b=-0.5, ruido=0.02, semilla=1):
    """Venta construida con sensibilidades conocidas sobre la variación anual."""
    rng = np.random.default_rng(semilla)
    idx = pd.date_range("2018-01-01", "2026-02-01", freq="MS")
    a = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(idx))))
    b = 1000 * np.exp(np.cumsum(rng.normal(0, 0.05, len(idx))))
    ind = pd.DataFrame({"A": a, "B": b}, index=idx)
    log_v = np.log(1000) + beta_a * np.log(ind["A"]).shift(1) + beta_b * np.log(ind["B"])
    log_v += rng.normal(0, ruido, len(idx)) + 0.3 * np.sin(2 * np.pi * idx.month / 12)  # estacionalidad
    return np.exp(log_v).dropna(), ind


def test_recupera_las_sensibilidades_conocidas():
    venta, ind = _datos()
    m = E.estimar(venta, ind, variables=VARS)
    assert not m.error_msg
    b = m.coefs.set_index("clave")["beta"]
    assert abs(b["A"] - 3.0) < 0.6 and abs(b["B"] + 0.5) < 0.2
    assert m.coefs["claro"].all() and m.r2 > 0.5


def test_pocos_meses_avisa_en_lugar_de_estimar():
    venta, ind = _datos()
    m = E.estimar(venta[venta.index >= "2024-06-01"], ind, variables=VARS)
    assert m.error_msg and m.coefs.empty


def test_simular_parte_del_mismo_mes_del_anio_anterior():
    venta, ind = _datos()
    m = E.estimar(venta, ind, variables=VARS)
    m.constante = 0.0
    meses = pd.date_range("2026-03-01", periods=14, freq="MS")
    sim = E.simular(m, venta, meses, {"A": 0.0, "B": 0.0})
    # Sin cambios y sin tendencia, cada mes repite el del año anterior; el mes 13
    # en adelante se apoya en lo ya simulado.
    assert np.isclose(sim.loc[0, "ton"], venta[pd.Timestamp("2025-03-01")])
    assert np.isclose(sim.loc[12, "ton"], sim.loc[0, "ton"])
    assert (sim["lo"] < sim["ton"]).all() and (sim["hi"] > sim["ton"]).all()


def test_efecto_y_aportes_cuadran():
    venta, ind = _datos()
    m = E.estimar(venta, ind, variables=VARS)
    ef = E.efecto_pct(m, {"A": 2.0, "B": 10.0}, ajuste_propio=5.0)
    beta = m.coefs.set_index("clave")["beta"]
    esperado = np.exp(m.constante + beta["A"] * np.log1p(0.02) + beta["B"] * np.log1p(0.10)) * 1.05 - 1
    assert np.isclose(ef["total"], esperado * 100)
    assert ef["aportes"]["A"] > 0 > ef["aportes"]["B"]


def test_adverso_sube_lo_que_resta_y_baja_lo_que_suma():
    venta, ind = _datos()
    m = E.estimar(venta, ind, variables=VARS)
    adv, pos = E.preajuste(m, "adverso"), E.preajuste(m, "positivo")
    assert adv["A"] < pos["A"]          # A suma a la venta: adverso = año bajo
    assert adv["B"] > pos["B"]          # B resta (como importaciones): adverso = año alto
    assert E.efecto_pct(m, adv)["total"] < E.efecto_pct(m, pos)["total"]
    assert set(E.preajuste(m, "base").values()) == {0.0}
