"""Pruebas de mercado_noticias/analytics/rutas_alertas.py (sin Oracle)."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mercado_noticias.analytics.rutas_alertas import alertas_rutas  # noqa: E402


def _noticias(titulos, dias_atras=1):
    hoy = pd.Timestamp("2026-10-28")
    return pd.DataFrame({
        "fecha_pub": [hoy - pd.Timedelta(days=dias_atras)] * len(titulos),
        "titulo": titulos, "fuente": "X", "url": [f"https://x.com/{i}" for i in range(len(titulos))],
        "variable_principal": "otro", "grupo_tematico": "Urgente", "razon": "",
    })


def test_liga_pasos_paises_y_puertos_con_claves_del_monitor():
    a = alertas_rutas(_noticias([
        "Houthi attacks on ships in the Red Sea - Reuters",
        "Transnet strike halts Richards Bay port",
        "India steel demand grows 8%",                  # país sin palabra de logística: no cuenta
        "Bloqueo en el puerto de Veracruz por transportistas",
        "Veracruz: inauguran parque",                   # puerto sin logística: no cuenta
    ]), hoy="2026-10-28")
    nodos = set(a["nodo"])
    assert {"paso:bab", "pais:710", "puerto:ver"} <= nodos
    assert "pais:356" not in nodos
    bab = a[a["nodo"] == "paso:bab"].iloc[0]
    assert bab["severidad"] == "alta" and bab["titulo"] == "Houthi attacks on ships in the Red Sea"


def test_descarta_noticias_viejas():
    assert alertas_rutas(_noticias(["Panama Canal drought limits transits"], dias_atras=40), hoy="2026-10-28").empty
