"""Pruebas del catálogo de métricas core/metricas.py (sin Oracle: se intercepta la consulta)."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import metricas  # noqa: E402


class _Captura:
    """Sustituye metricas._consulta: guarda el SQL y los binds y regresa <respuesta>."""
    def __init__(self, respuesta: pd.DataFrame):
        self.respuesta, self.llamadas = respuesta, []

    def __call__(self, sql, params):
        self.llamadas.append((sql, dict(params)))
        return self.respuesta.copy()


def _con_captura(monkeypatch, respuesta):
    cap = _Captura(respuesta)
    monkeypatch.setattr(metricas, "_consulta", cap)
    return cap


def test_ultimo_mes_completo():
    assert metricas.ultimo_mes_completo(pd.Timestamp("2026-03-10")) == pd.Timestamp("2026-02-01")
    assert metricas.ultimo_mes_completo(pd.Timestamp("2026-03-31")) == pd.Timestamp("2026-03-01")


def test_estado_cliente_usa_los_umbrales_del_catalogo():
    assert metricas.estado_cliente(metricas.DIAS_CLIENTE_ACTIVO) == "Activo"
    assert metricas.estado_cliente(metricas.DIAS_CLIENTE_ACTIVO + 1) == "En riesgo"
    assert metricas.estado_cliente(metricas.DIAS_CLIENTE_EN_RIESGO + 1) == "Inactivo"


def test_calcular_usa_binds_y_hasta_incluido(monkeypatch):
    cap = _con_captura(monkeypatch, pd.DataFrame({"CLIENTE": ["A"], "VALOR": [10]}))
    metricas.calcular("toneladas", "2026-01-01", "2026-01-31", por="cliente",
                      filtros={"producto": "LAMINA'; DROP TABLE X--"}, top=5)
    sql, params = cap.llamadas[0]
    assert "SUM(PESO_TON)" in sql and "GROUP BY CLIENTE" in sql and "FETCH FIRST 5 ROWS ONLY" in sql
    assert "DROP TABLE" not in sql and params["f0"] == "LAMINA'; DROP TABLE X--"   # el valor va como bind
    assert params["hasta"] == pd.Timestamp("2026-02-01").to_pydatetime()           # < día siguiente = incluido


def test_dimension_desconocida_no_llega_al_sql(monkeypatch):
    _con_captura(monkeypatch, pd.DataFrame({"VALOR": [1]}))
    try:
        metricas.calcular("toneladas", por="CLIENTE; DELETE")
    except KeyError:
        return
    raise AssertionError("debió rechazar la dimensión")


def test_variacion_compara_meses_completos(monkeypatch):
    llamadas = []

    def valor_falso(metrica, desde, hasta, area="NEGROS", filtros=None):
        llamadas.append((pd.Timestamp(desde), pd.Timestamp(hasta)))
        return 120.0 if pd.Timestamp(desde).month == 2 else 100.0

    monkeypatch.setattr(metricas, "valor", valor_falso)
    monkeypatch.setattr(metricas, "fecha_corte", lambda area="NEGROS": pd.Timestamp("2026-03-10"))
    v = metricas.variacion("toneladas")
    assert v["mes"] == pd.Timestamp("2026-02-01") and v["mes_base"] == pd.Timestamp("2026-01-01")
    assert round(v["pct"], 1) == 20.0
    assert llamadas[0] == (pd.Timestamp("2026-02-01"), pd.Timestamp("2026-02-28"))
