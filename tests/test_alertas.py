"""Pruebas de la bandeja de alertas core/alertas.py (sin Oracle: se sustituyen las fuentes)."""
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import alertas, metricas  # noqa: E402
from core.alertas import Alerta  # noqa: E402


def _con_fuentes(monkeypatch, fuentes: dict):
    monkeypatch.setattr(alertas, "FUENTES", fuentes)


def test_ordena_por_prioridad_y_fecha_y_quita_duplicados(monkeypatch):
    _con_fuentes(monkeypatch, {
        "A": lambda hoy: [Alerta("info", "Mercado Global", "A", "i", clave="x1"),
                          Alerta("alta", "Sistema", "A", "vieja", fecha=date(2026, 1, 1), clave="x2")],
        "B": lambda hoy: [Alerta("alta", "Sistema", "B", "nueva", fecha=date(2026, 5, 1), clave="x3"),
                          Alerta("media", "Sistema", "B", "dup", clave="x2")],
    })
    titulos = [a.titulo for a in alertas.recolectar(date(2026, 6, 1))]
    assert titulos == ["nueva", "vieja", "i"]


def test_una_fuente_caida_no_tumba_la_bandeja(monkeypatch):
    def falla(hoy):
        raise RuntimeError("ORA-12345")
    _con_fuentes(monkeypatch, {"Buena": lambda hoy: [Alerta("media", "Sistema", "Buena", "ok", clave="ok")],
                               "Rota": falla})
    res = alertas.recolectar(date(2026, 6, 1))
    assert [a.titulo for a in res] == ["ok", "No se pudo revisar: Rota"]
    assert res[1].prioridad == "info" and "ORA-12345" in res[1].detalle


def test_especialista_sin_planos_no_ve_alertas_de_planos(monkeypatch):
    _con_fuentes(monkeypatch, {"Clientes": lambda hoy: [Alerta("alta", "Aceros Planos", "Clientes", "c", clave="c")],
                               "DOF": lambda hoy: [Alerta("media", "Mercado Global", "DOF", "d", clave="d")]})
    assert [a.titulo for a in alertas.recolectar(date(2026, 6, 1), areas_permitidas=["aceros_largos"])] == ["d"]
    assert len(alertas.recolectar(date(2026, 6, 1), areas_permitidas=["aceros_planos"])) == 2


def test_clientes_top_en_fuga_son_alta_y_el_resto_se_agrupa(monkeypatch):
    clientes = pd.DataFrame({
        "CLIENTE": ["TOP1", "TOP2", "CHICO", "PERDIDO"],
        "ULTIMA_COMPRA": pd.to_datetime(["2026-01-01", "2026-02-25", "2025-12-20", "2025-01-01"]),
        "TON_RECIENTE": [900.0, 800.0, 5.0, 1.0],
        "DIAS_SIN_COMPRA": [68, 13, 80, 433],
    })
    monkeypatch.setattr(metricas, "ultima_compra_por_cliente", lambda: clientes)
    monkeypatch.setattr(alertas, "TOP_CLIENTES_PRIORITARIOS", 2)
    res = alertas.alertas_clientes(date(2026, 3, 10))
    assert [(a.prioridad, a.clave) for a in res] == [("alta", "fuga_TOP1"), ("media", "fuga_resto")]
    assert "1 clientes más" in res[1].titulo  # PERDIDO (> 180 días) ya es inactivo: no es fuga


def test_caida_del_mes_marca_prioridad_por_umbral(monkeypatch):
    def con_pct(pct):
        monkeypatch.setattr(metricas, "variacion", lambda m, contra: {
            "pct": pct, "mes": pd.Timestamp("2026-02-01"), "mes_base": pd.Timestamp("2025-02-01"),
            "actual": 75.0, "base": 100.0})
        return [a.prioridad for a in alertas.alertas_volumen(date(2026, 3, 10))]
    assert con_pct(-30) == ["alta"]
    assert con_pct(-12) == ["media"]
    assert con_pct(-5) == []
