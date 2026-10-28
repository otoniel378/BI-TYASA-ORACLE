"""
mercado_fastmarkets/alerta_alzas.py — Semáforo de alerta temprana de alzas en
ferroaleaciones (pages/mercado/09_quiebres_ferroaleaciones.py).

Pregunta: ¿qué tan probable es que la serie suba más de UMBRAL_ALZA (15%) en
los próximos HORIZONTE (3) meses? Viene del prototipo del "Estudio de riesgos
en insumos" (detectó a tiempo 63% de las alzas fuertes 2008-2026 en 4 insumos).

Semáforo (2008-2026, fuera de muestra, 9 series; en un mes cualquiera la serie
sube +15% en 3 meses ~12% de las veces):
  - Verde: modelo < 20% y precio dentro del rango normal -> subió 10%.
  - Amarillo: modelo >= 20% o precio arriba del rango -> 20%.
  - Rojo: las dos a la vez -> 32% (la mayoría en 2021).
Detecta a tiempo 53% de las alzas con 1.8 falsas alarmas por serie al año. Con
el amarillo en 10% detectaba 84% pero con 3.8 falsas alarmas y casi la mitad
de los meses en alerta; en 25%, 43% con 1.3.
La probabilidad del modelo NO se usa como número literal: arriba de 20% ya no
acierta más que entre 10 y 20% (con 30%+ subió 12%), y calibrarla con isotónica
hacia adelante lo empeoró (el patrón alto no se sostiene de un periodo a otro).
Lo que sí separa es "bajo" contra "no bajo"; el precio arriba del rango normal
(rupturas.bandas_normales) es la señal más fuerte (32% contra 11.5%).

  - Un solo modelo para todas las series (panel con indicador de serie): cada
    serie tiene pocos episodios de alza; juntas alcanzan para entrenar.
  - Variables: impulso y volatilidad del propio precio, distancia a máximos y
    mínimos, lo que hacen las demás ferroaleaciones y 3 meses de gas Henry Hub,
    Brent, cobre, USD/MXN e índice dólar.
  - Validación "hacia adelante": cada año se predice solo con lo que se sabía
    antes de ese año (una etiqueta del mes t se conoce en t+HORIZONTE).

Funciones puras (sin Oracle ni Streamlit); las corre scripts/update_semaforo_ferros.py.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

HORIZONTE = 3          # meses hacia adelante
UMBRAL_ALZA = 0.15     # alza que cuenta como "fuerte" (con 20% solo 4 de 9 series tenían señal confiable)
AMARILLO = 0.20        # probabilidad del modelo a partir de la cual el riesgo es "elevado"
PRIMER_ANIO_PRUEBA = 2008
EXTERNAS_YF = {"NG=F": "gas_hh", "BZ=F": "brent", "HG=F": "cobre", "MXN=X": "usd_mxn", "DX-Y.NYB": "dolar_idx"}


# Variables para la huella de impacto de los quiebres (rupturas.huella_impacto);
# se guardan mensuales en GOLD_MERCADO_MENSUAL.
MERCADO_HUELLA_YF = {
    "^GSPC": "sp500", "^VIX": "vix", "CL=F": "petroleo_wti", "NG=F": "gas_hh",
    "DX-Y.NYB": "dolar_idx", "HG=F": "cobre", "BDRY": "flete_seco",
}


def semaforo(p: float, arriba: bool = False) -> str:
    """Rojo = modelo elevado y precio arriba del rango normal; Amarillo = una de las dos."""
    elevado = p >= AMARILLO
    return "Rojo" if elevado and arriba else "Amarillo" if elevado or arriba else "Verde"


def agregar_rango(df: pd.DataFrame, precios: pd.DataFrame) -> pd.DataFrame:
    """Agrega 'arriba' (precio del mes arriba de su rango normal, que solo usa
    meses anteriores) y 'semaforo' a filas (serie, fecha, prob)."""
    from mercado_noticias.analytics.rupturas import bandas_normales
    arriba = []
    for serie in precios.columns:
        b = bandas_normales(precios[serie].dropna())
        arriba.append(pd.DataFrame({"serie": serie, "fecha": b.index.values,
                                    "arriba": (b["precio"] > b["banda_sup"]).values}))
    out = df.merge(pd.concat(arriba), on=["serie", "fecha"], how="left")
    out["arriba"] = out["arriba"].fillna(False).astype(bool)
    out["semaforo"] = [semaforo(p, a) for p, a in zip(out["prob"], out["arriba"])]
    return out


def cargar_externas(desde: str = "1999-01-01", tickers: dict | None = None) -> pd.DataFrame:
    """Promedio mensual de variables de mercado (yfinance; por defecto las del
    modelo, EXTERNAS_YF). Vacío si no hay red."""
    import yfinance as yf
    series = {}
    for ticker, nombre in (tickers or EXTERNAS_YF).items():
        try:
            d = yf.download(ticker, start=desde, progress=False, auto_adjust=True)
            if len(d):
                series[nombre] = d["Close"].squeeze().resample("MS").mean()
        except Exception as e:
            print(f"  Aviso: no se pudo bajar {ticker} ({e})")
    return pd.DataFrame(series)


def construir_panel(precios: pd.DataFrame, externas: pd.DataFrame) -> pd.DataFrame:
    """precios: ancho mensual (normalizar_mensual, índice = primer día del mes).
    Devuelve una fila por (serie, mes) con variables, alza futura y etiqueta y."""
    ext_r3 = (externas / externas.shift(3) - 1).add_suffix("_r3") if not externas.empty else pd.DataFrame()
    bloques = []
    for serie in precios.columns:
        p = precios[serie].dropna()
        if len(p) < 24:
            continue
        pares = precios.drop(columns=serie).reindex(p.index)
        lr = np.log(p).diff()
        f = pd.DataFrame(index=p.index)
        for k in (1, 3, 6, 12):
            f[f"r{k}"] = p / p.shift(k) - 1
        f["vol6"] = lr.rolling(6).std()
        f["vs_max12"] = p / p.rolling(12).max() - 1
        f["vs_min12"] = p / p.rolling(12).min() - 1
        f["z24"] = (p - p.rolling(24).mean()) / p.rolling(24).std()
        f["pares_r1"] = (pares / pares.shift(1) - 1).mean(axis=1)
        f["pares_r3"] = (pares / pares.shift(3) - 1).mean(axis=1)
        if not ext_r3.empty:
            f = f.join(ext_r3, how="left")
        fwd = p.shift(-HORIZONTE) / p - 1
        f["alza_fut"] = fwd
        f["y"] = np.where(fwd.notna(), (fwd > UMBRAL_ALZA).astype(float), np.nan)
        f["serie"] = serie
        bloques.append(f)
    panel = pd.concat(bloques)
    panel.index.name = "fecha"
    panel = panel.reset_index()
    for serie in panel["serie"].unique():
        panel[f"es_{serie}"] = (panel["serie"] == serie).astype(float)
    return panel[panel["r12"].notna()].reset_index(drop=True)


def columnas_modelo(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c not in {"fecha", "serie", "alza_fut", "y"}]


def _modelo() -> XGBClassifier:
    return XGBClassifier(n_estimators=250, max_depth=3, learning_rate=0.04, subsample=0.8,
                         colsample_bytree=0.8, min_child_weight=5, eval_metric="logloss")


def walk_forward(panel: pd.DataFrame) -> pd.DataFrame:
    """Probabilidad fuera de muestra para cada mes desde PRIMER_ANIO_PRUEBA."""
    cols = columnas_modelo(panel)
    salida = []
    for anio in range(PRIMER_ANIO_PRUEBA, panel["fecha"].dt.year.max() + 1):
        corte = pd.Timestamp(f"{anio}-01-01") - pd.DateOffset(months=HORIZONTE)
        train = panel[(panel["fecha"] < corte) & panel["y"].notna()]
        test = panel[panel["fecha"].dt.year == anio].copy()
        if test.empty or train["y"].sum() < 5:
            continue
        test["prob"] = _modelo().fit(train[cols], train["y"]).predict_proba(test[cols])[:, 1]
        salida.append(test[["fecha", "serie", "prob", "alza_fut", "y"]])
    return pd.concat(salida).reset_index(drop=True)


def prediccion_actual(panel: pd.DataFrame) -> pd.DataFrame:
    """Probabilidad del último mes de cada serie con un modelo entrenado con
    todas las etiquetas ya conocidas, y qué variables la empujan más."""
    cols = columnas_modelo(panel)
    entren = panel[panel["y"].notna()]
    modelo = _modelo().fit(entren[cols], entren["y"])
    ult = panel.sort_values("fecha").groupby("serie").tail(1).copy()
    ult["prob"] = modelo.predict_proba(ult[cols])[:, 1]
    return ult[["fecha", "serie", "prob", "r1", "r3"]].reset_index(drop=True)


def _episodios(y: pd.Series) -> list[int]:
    return list(y.index[(y == 1) & (y.shift(1) != 1)])


def metricas(oos: pd.DataFrame, umbral: float = AMARILLO) -> pd.DataFrame:
    """Por serie y total: episodios de alza, detectados a tiempo (alerta entre 2
    meses antes y el inicio), falsas alarmas por año y % de alertas que acertaron.
    Alerta = prob >= <umbral>, o semáforo distinto de verde si <oos> ya lo trae
    (agregar_rango)."""
    filas = []
    con_y = oos[oos["y"].notna()]
    for serie, g in list(con_y.groupby("serie")) + [("Total", con_y)]:
        tot = det = falsas = meses = 0
        aciertos = []
        for _, gs in (g.groupby("serie") if serie == "Total" else [(serie, g)]):
            gs = gs.sort_values("fecha").reset_index(drop=True)
            alerta = gs["semaforo"] != "Verde" if "semaforo" in gs else gs["prob"] >= umbral
            for i in _episodios(gs["y"]):
                tot += 1
                det += bool(alerta.iloc[max(0, i - 2):i + 1].any())
            y_prox = gs["y"][::-1].rolling(3, min_periods=1).max()[::-1]
            falsas += int((alerta & (y_prox == 0)).sum())
            meses += len(gs)
            aciertos += list(gs.loc[alerta, "y"])
        auc = roc_auc_score(g["y"], g["prob"]) if g["y"].nunique() == 2 else np.nan
        filas.append({
            "serie": serie, "episodios": tot, "detectados": det,
            "pct_detectados": det / tot if tot else np.nan,
            "falsas_por_anio": falsas / (meses / 12) if meses else np.nan,
            "aciertan": float(np.mean(aciertos)) if aciertos else np.nan,
            "auc": auc, "prob_base": float(g["y"].mean()),
        })
    return pd.DataFrame(filas)
