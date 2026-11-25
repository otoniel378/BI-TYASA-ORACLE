"""Pruebas de mercado_rutas (sin Oracle ni red)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mercado_rutas.red import MATERIALES, PAISES, PASOS, PUERTOS, SALIDAS  # noqa: E402
from mercado_rutas.riesgo import estado_red, estado_trafico, evaluar_ruta, peor, rutas_de  # noqa: E402


def test_red_consistente():
    for s in SALIDAS.values():
        assert all(p in PASOS for p in s["puntos"] if isinstance(p, str))
    for iso, o in PAISES.items():
        assert all(s in SALIDAS for s in o["salidas"]), iso
    for _, (_, paises) in MATERIALES.items():
        assert all(i in PAISES for i in paises)


def test_rutas_por_pais_y_escenario():
    rs = rutas_de("156")                       # China: 3 salidas x 5 puertos
    assert len(rs) == 15 and all(r["disponible"] for r in rs)
    assert rs[0]["puerto"] in ("laz", "man")   # lo más rápido es directo al Pacífico
    cerr = rutas_de("156", frozenset({"panama"}))
    assert all(not r["disponible"] for r in cerr if "panama" in r["pasos"])
    assert cerr[0]["disponible"] and "panama" not in cerr[0]["pasos"]
    assert rutas_de("484")[0]["puerto"] is None  # México: solo carretera


def test_estado_trafico():
    idx = pd.date_range("2026-01-01", periods=200, freq="D")
    s = pd.Series(np.r_[np.full(186, 50.0), np.full(14, 25.0)], index=idx)
    assert estado_trafico(s)["estado"] == "Muy reducido"
    assert estado_trafico(pd.Series(50.0, index=idx))["estado"] == "Normal"
    assert estado_trafico(s.iloc[:20])["estado"] == "Sin datos"


def test_nivel_de_punto_y_ruta():
    idx = pd.date_range("2026-01-01", periods=200, freq="D")
    pasos = pd.DataFrame({"fecha": idx, "paso": "cabo", "transitos": 50.0})
    puertos = pd.DataFrame({"fecha": idx, "puerto": "ver", "llamadas": 5.0})
    avisos = pd.DataFrame({"nodo": ["pais:710"], "lugar": ["Sudáfrica"], "severidad": ["alta"]})
    oleaje = pd.DataFrame({"puerto": ["ver"], "oleaje_max_m": [3.0], "dia": ["2026-07-20"]})
    red = estado_red(pasos, puertos, avisos, oleaje, pd.DataFrame(columns=["nombre", "tipo", "puerto", "km"]))
    r = red.set_index("nodo")
    assert r.loc["paso:cabo", "nivel"] == "normal"
    assert r.loc["puerto:ver", "nivel"] == "vigilar"            # oleaje
    assert r.loc["pais:710", "nivel"] == "riesgo"                # noticia grave
    assert r.loc["paso:suez", "nivel"] == "sin datos"
    ruta = next(x for x in rutas_de("710") if x["puerto"] == "ver")
    ev = evaluar_ruta(ruta, red)
    assert ev["nivel"] == "riesgo" and ev["graves"] == 1
    assert peor("normal", "vigilar") == "vigilar"
    assert set(PUERTOS) == {"ver", "coa", "alt", "laz", "man"}


def test_ruta_por_tren_y_grupos():
    from mercado_rutas.red import FRONTERAS, GRUPOS
    assert all(m in MATERIALES for g in GRUPOS.values() for m in g)
    assert set(MATERIALES) == {m for g in GRUPOS.values() for m in g}
    tren = [r for r in rutas_de("840") if r["modo"] == "tren"]
    assert len(tren) == 1 and tren[0]["frontera"] in FRONTERAS and not tren[0]["pasos"]
    avisos = pd.DataFrame({"nodo": ["frontera:laredo"], "lugar": ["Nuevo Laredo"], "severidad": ["alta"]})
    red = estado_red(pd.DataFrame(columns=["fecha", "paso", "transitos"]),
                     pd.DataFrame(columns=["fecha", "puerto", "llamadas"]), avisos, pd.DataFrame(),
                     pd.DataFrame(columns=["nombre", "tipo", "puerto", "km"]))
    assert evaluar_ruta(tren[0], red)["nivel"] == "riesgo"
    # Colombia entra por el Caribe: al Golfo sin cruzar Panamá
    assert "panama" not in next(r for r in rutas_de("170") if r["puerto"] == "ver")["pasos"]


def test_origenes_con_proveedores():
    from mercado_rutas.proveedores import origenes, ruta_principal
    prov = pd.DataFrame({"material": ["FeCr"], "proveedor": ["X"], "pais_iso": ["156"], "ruta_id": ["156-a-ver"]})
    assert origenes("FeCr", ["710", "156"], prov) == ["156", "710"]
    assert ruta_principal("FeCr", "156", prov) == ("156-a-ver", "X")
    assert ruta_principal("FeSi", "156", prov) == (None, None)
