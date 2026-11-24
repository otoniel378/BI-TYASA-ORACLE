"""Pruebas de core/calidad_datos.py y su paso a la bandeja (sin Oracle: se sustituye _q)."""
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import alertas, calidad_datos as C  # noqa: E402

HOY = date(2026, 11, 24)


def _consulta_ventas(bronce="2026-03-10", plata="2026-03-10", oro="2026-03-01", t_oro=1000.0,
                     prod_oro=10, meses=None):
    meses = meses if meses is not None else {f"2025-{m:02d}-01": 100.0 for m in range(1, 13)}
    meses = {**meses, "2026-01-01": 100.0, "2026-02-01": 100.0, "2026-03-01": 30.0}

    def q(sql, params=None):
        if "BRONZE_VENTAS_RAW" in sql:
            return pd.DataFrame({"F": [pd.Timestamp(bronce)]})
        if "FROM DUAL" in sql:
            return pd.DataFrame({"F": [pd.Timestamp(oro)], "T": [t_oro], "P": [prod_oro], "C": [5]})
        if "TRUNC(FECHAEMB" in sql:
            return pd.DataFrame({"MES": pd.to_datetime(list(meses)), "T": list(meses.values())})
        return pd.DataFrame({"F": [pd.Timestamp(plata)], "T": [1000.0], "P": [10], "C": [5], "N": [500],
                             "MAL": [0], "SIN": [0]})
    return q


def _por_regla(revs):
    return {r.regla: r.estado for r in revs}


def test_ventas_todo_cuadra(monkeypatch):
    monkeypatch.setattr(C, "_q", _consulta_ventas())
    assert set(_por_regla(C.reglas_ventas(HOY)).values()) == {"ok"}


def test_bronce_nuevo_sin_plata_ni_oro_y_descuadre(monkeypatch):
    monkeypatch.setattr(C, "_q", _consulta_ventas(bronce="2026-11-20", t_oro=900.0, prod_oro=9))
    r = _por_regla(C.reglas_ventas(HOY))
    assert r["Plata al día con Bronce"] == "falla"
    assert r["Oro cuadra con Plata"] == "falla"


def test_oro_atrasado_un_mes(monkeypatch):
    monkeypatch.setattr(C, "_q", _consulta_ventas(oro="2026-02-01"))
    assert _por_regla(C.reglas_ventas(HOY))["Oro al día con Plata"] == "falla"


def test_mes_vacio_y_mes_atipico(monkeypatch):
    meses = {f"2025-{m:02d}-01": 100.0 for m in range(1, 13)}
    meses["2025-05-01"] = 0.0
    meses["2025-08-01"] = 900.0
    monkeypatch.setattr(C, "_q", _consulta_ventas(meses=meses))
    revs = {r.regla: r for r in C.reglas_ventas(HOY)}
    assert revs["Sin meses vacíos"].estado == "aviso" and "05/2025" in revs["Sin meses vacíos"].detalle
    assert revs["Sin meses atípicos"].estado == "aviso" and "08/2025" in revs["Sin meses atípicos"].detalle


def test_frescura_por_umbral_y_periodo_mensual(monkeypatch):
    monkeypatch.setattr(C, "FUENTES", (
        C.Fuente("Diaria", "X", "D", "fecha", "diaria", 4, 10),
        C.Fuente("Atrasada", "X", "A", "fecha", "diaria", 4, 10),
        C.Fuente("Mensual", "X", "M", "periodo", "mensual", 75, 120),
        C.Fuente("Vacía", "X", "V", "fecha", "manual", 45, 90),
    ))
    valores = {"D": pd.Timestamp("2026-11-24"), "A": pd.Timestamp("2026-11-17"), "M": "2026-09", "V": None}
    monkeypatch.setattr(C, "_q", lambda sql, p=None: pd.DataFrame({"F": [valores[sql]]}))
    est = {r.fuente: r.estado for r in C.revisar_frescura(HOY)}
    # sep-2026 cuenta desde el 01/10 (54 días): al día.
    assert est == {"Diaria": "ok", "Atrasada": "aviso", "Mensual": "ok", "Vacía": "falla"}


def test_regla_que_truena_no_tumba_la_revision(monkeypatch):
    monkeypatch.setattr(C, "revisar_frescura", lambda hoy: [])
    def falla(hoy):
        raise RuntimeError("ORA-00942")
    monkeypatch.setattr(C, "REGLAS", {"Ventas": falla, "Mercado": lambda hoy: [C.Revision("M", "m", "r", "ok")]})
    res = C.revisar(HOY)
    assert [r.estado for r in res] == ["falla", "ok"] and "ORA-00942" in res[0].detalle


def test_bandeja_falla_usa_prioridad_de_la_fuente_y_aviso_es_informativa(monkeypatch):
    monkeypatch.setattr(C, "revisar", lambda hoy: [
        C.Revision("Aceros Planos", "Ventas (SAP)", "Al día", "falla", "hace 259 días", tipo="frescura", prioridad="alta"),
        C.Revision("Mercado Global", "CANACERO", "Al día", "aviso", "hace 146 días", tipo="frescura"),
        C.Revision("Aceros Planos", "Ventas (SAP)", "Oro cuadra con Plata", "ok"),
    ])
    res = alertas.alertas_calidad(HOY)
    assert [(a.prioridad, a.fuente) for a in res] == [("alta", "Calidad de datos"), ("info", "Calidad de datos")]
    assert all(a.destino == alertas.DESTINO_ESTADO_DATOS for a in res)
