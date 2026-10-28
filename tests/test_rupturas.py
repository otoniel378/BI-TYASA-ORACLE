"""Pruebas de mercado_noticias/analytics/rupturas.py (sin Oracle)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mercado_noticias.analytics.rupturas import (  # noqa: E402
    MIN_SEGMENTO, agregar_desempeno_posterior, bandas_normales, detectar_rupturas, huella_impacto, normalizar_mensual,
    resumen_casos_parecidos, rupturas_a_dataframe, tipo_impacto_noticias, vincular_eventos,
)


def _serie_con_quiebre(seed: int = 0) -> pd.Series:
    """10 años estables y luego 3 años de alza fuerte y volátil."""
    rng = np.random.default_rng(seed)
    r = np.concatenate([rng.normal(0.0, 0.02, 120), rng.normal(0.05, 0.08, 36)])
    idx = pd.date_range("2005-01-01", periods=len(r) + 1, freq="MS")
    return pd.Series(100 * np.exp(np.concatenate([[0.0], np.cumsum(r)])), index=idx)


def test_normalizar_arrastra_cotizacion_sin_interpolar():
    df = pd.DataFrame({
        "fecha": pd.to_datetime(["2020-01-15", "2020-04-10", "2020-04-20"]),
        "serie": "X", "valor": [10.0, 20.0, 30.0],
    })
    m = normalizar_mensual(df)["X"]
    assert list(m.values) == [10.0, 10.0, 10.0, 30.0]  # feb-mar arrastran, abril = último del mes


def test_detecta_quiebre_cerca_de_la_fecha_real():
    rupturas = detectar_rupturas(_serie_con_quiebre(), "X")
    assert rupturas, "debe detectar al menos un quiebre"
    real = pd.Timestamp("2015-01-01")
    mas_cercano = min(rupturas, key=lambda q: abs(q.fecha - real))
    assert abs((mas_cercano.fecha - real).days) <= 92
    assert mas_cercano.direccion == "Sube" and mas_cercano.evidencia == "Fuerte"


def test_serie_sin_cambio_no_da_quiebres_fuertes():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2005-01-01", periods=160, freq="MS")
    s = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0, 0.03, 160))), index=idx)
    assert not [q for q in detectar_rupturas(s, "X") if q.evidencia == "Fuerte"]


def test_banda_marca_salto_brusco_y_no_un_escalon_chico():
    idx = pd.date_range("2015-01-01", periods=30, freq="MS")
    valores = [100.0] * 18 + [104.0] * 6 + [160.0] * 6  # escalón de 4% (normal) y salto de ~54%
    b = bandas_normales(pd.Series(valores, index=idx))
    assert not b.loc["2016-07-01", "fuera"]
    assert b.loc["2017-01-01", "fuera"]


def test_casos_parecidos_miden_desde_la_confirmacion():
    idx = pd.date_range("2010-01-01", periods=40, freq="MS")
    precios = pd.DataFrame({"X": np.arange(100.0, 140.0)}, index=idx)
    rupt = pd.DataFrame({"serie": ["X"], "fecha": [idx[0]], "regimen": ["Estable → Alza"]})
    out = agregar_desempeno_posterior(rupt, precios)
    base = precios["X"].iloc[MIN_SEGMENTO]
    assert np.isclose(out["despues_3m"].iloc[0], (precios["X"].iloc[MIN_SEGMENTO + 3] / base - 1) * 100)
    assert resumen_casos_parecidos(out, "Estable → Alza", excluir=("X", idx[0])).empty


def test_huella_evento_manda_y_caida_de_bolsa_es_financiero():
    idx = pd.date_range("2000-01-01", periods=120, freq="MS")
    sp = pd.Series(1000.0, index=idx)
    sp.loc["2008-09-01":] = 700.0                       # caída de 30%
    mercado = pd.DataFrame({"sp500": sp})
    rupt = pd.DataFrame({
        "serie": ["X", "Y", "Z"],
        "fecha": pd.to_datetime(["2008-10-01", "2003-05-01", "2003-06-01"]),
        "evento_tipo": [None, "Política comercial", None],
    })
    out = huella_impacto(rupt, mercado).set_index("serie")
    assert out.loc["X", "tipo_impacto"] == "Macro/financiero" and out.loc["X", "tipo_fuente"] == "huella de mercado"
    assert out.loc["Y", "tipo_impacto"] == "Política comercial" and out.loc["Y", "tipo_fuente"] == "evento verificado"
    assert out.loc["Z", "tipo_impacto"] == "Oferta/producción"   # sin señal y sola: propio de la aleación


def test_vincula_solo_eventos_de_la_misma_serie_y_ventana():
    rupt = rupturas_a_dataframe(detectar_rupturas(_serie_con_quiebre(), "X"))
    fecha = rupt["fecha"].iloc[0]
    eventos = pd.DataFrame({
        "id": ["bueno", "otra_serie", "lejano"],
        "fecha_inicio": [fecha - pd.DateOffset(months=1), fecha, fecha - pd.DateOffset(years=3)],
        "fecha_fin": [pd.NaT, pd.NaT, pd.NaT],
        "nombre": ["b", "o", "l"], "descripcion": ["", "", ""], "fuente": ["", "", ""],
        "variables_relacionadas": ["X,Y", "Y", "X"],
    })
    out = vincular_eventos(rupt, eventos)
    assert out.loc[out["fecha"] == fecha, "evento_id"].iloc[0] == "bueno"


def test_tipo_impacto_noticias():
    noticias = pd.DataFrame({
        "titulo": ["Sanciones a Rusia golpean el suministro de metales", "Sube el arancel al acero",
                   "Tamaño del mercado de acero HRC 2034", "Gerdau inaugura planta",
                   "Producción de acero crudo sube en julio", "Oil prices jump"],
        "razon": ["", "", "", "guerra comercial", "", ""],
        "variable_principal": ["otro", "aranceles_comercio", "HRC_laminado_caliente", "otro", "otro", "otro"],
        "grupo_tematico": ["Urgente", "Urgente", "Insumos", "Empresas", "Insumos", "Energía"],
    })
    out = tipo_impacto_noticias(noticias).set_index("titulo")["tipo_impacto"]
    assert out["Sanciones a Rusia golpean el suministro de metales"] == "Geopolítico/conflicto"
    assert out["Sube el arancel al acero"] == "Política comercial"
    assert "Tamaño del mercado de acero HRC 2034" not in out.index      # estudio de mercado: fuera
    assert out["Gerdau inaugura planta"] is None                       # la razón no cuenta
    assert out["Producción de acero crudo sube en julio"] != "Energía"  # "crudo" no es petróleo
    assert out["Oil prices jump"] == "Energía"                         # grupo de búsqueda = tipo
