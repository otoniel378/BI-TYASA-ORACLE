"""
escenarios.py — Simulador "¿qué pasa si…?" de la demanda de Aceros Planos Negros.

En lugar de pesos fijos, la sensibilidad de la venta a cada variable se estima con
la historia: regresión de la variación anual de la venta (log, ventana de 3 meses)
contra la variación anual de los indicadores, con su rezago. Errores HAC porque
las ventanas móviles se traslapan.

    Δ12 log(venta_t) = c + Σ β_i · Δ12 log(indicador_i, t - rezago_i) + e

Simular: la venta de cada mes futuro = la del mismo mes del año anterior
× exp(c + Σ β_i · log(1 + cambio_i)) × (1 + ajuste propio). El ajuste propio cubre
lo que la historia no permite medir (p. ej. un precio de HRC con solo 2 años de datos).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Variable:
    clave: str          # NOMBRE en GOLD_INDICADORES_INEGI
    etiqueta: str
    fuente: str
    rezago: int         # meses que tarda en reflejarse en la venta
    corto: str = ""     # nombre corto para gráficas


VARIABLES = (
    Variable("IMAI_ProductosMetalicos_332_Indice", "Fabricación de productos metálicos",
             "INEGI · actividad industrial (rama 332)", 1, "Productos metálicos"),
    Variable("RAIAVL_UnidadesProducidas_Ligeros", "Producción de autos ligeros", "INEGI · RAIAVL", 2, "Autos ligeros"),
    Variable("BC_Siderurgia_Importaciones", "Importaciones de acero a México",
             "INEGI · balanza comercial (la mueven los aranceles)", 1, "Importaciones"),
)
DESDE = "2021-01-01"          # evita el rebote de la pandemia en las variaciones anuales
DESDE_RANGOS = "2022-01-01"   # para los escenarios adverso / positivo
VENTANA = 3
P_CLARO = 0.10                # efecto "claro" si p < 0.10


@dataclass
class ModeloEscenarios:
    constante: float
    coefs: pd.DataFrame            # clave, etiqueta, fuente, rezago, beta, lo, hi, p, claro
    r2: float
    n: int
    sigma: float                   # desviación del residuo (log)
    desde: pd.Timestamp
    hasta: pd.Timestamp
    actual: pd.DataFrame = field(default_factory=pd.DataFrame)   # clave, pct, fecha (últimos 3 meses publicados)
    rangos: pd.DataFrame = field(default_factory=pd.DataFrame)   # clave, bajo, alto (p10 / p90 en %)
    error_msg: str = ""


def _var_anual(s: pd.Series, ventana: int = VENTANA, suma: bool = False) -> pd.Series:
    m = s.rolling(ventana).sum() if suma else s.rolling(ventana).mean()
    return np.log(m.where(m > 0)).diff(12)


def estimar(venta: pd.Series, indicadores: pd.DataFrame, variables=VARIABLES,
            desde: str = DESDE) -> ModeloEscenarios:
    """venta: toneladas por mes (índice = primer día del mes, meses completos).
    indicadores: una columna por Variable.clave, índice mensual."""
    import statsmodels.api as sm

    venta = venta.asfreq("MS").fillna(0.0)
    y = _var_anual(venta, suma=True).rename("y")
    xs = [_var_anual(indicadores[v.clave].astype(float)).shift(v.rezago).rename(v.clave) for v in variables]
    df = pd.concat([y, *xs], axis=1).dropna()
    df = df[df.index >= pd.Timestamp(desde)]
    vacio = ModeloEscenarios(0.0, pd.DataFrame(), np.nan, len(df), np.nan, pd.NaT, pd.NaT)
    if len(df) < 24:
        vacio.error_msg = f"Solo {len(df)} meses comparables; se necesitan 24."
        return vacio

    m = sm.OLS(df["y"], sm.add_constant(df.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": VENTANA})
    ic = m.conf_int(alpha=0.10)
    coefs = pd.DataFrame([{
        "clave": v.clave, "etiqueta": v.etiqueta, "fuente": v.fuente, "rezago": v.rezago,
        "beta": float(m.params[v.clave]), "lo": float(ic.loc[v.clave, 0]), "hi": float(ic.loc[v.clave, 1]),
        "p": float(m.pvalues[v.clave]),
    } for v in variables])
    coefs["claro"] = coefs["p"] < P_CLARO

    actual, rangos = [], []
    for v in variables:
        s = indicadores[v.clave].dropna().astype(float)
        va = (s.rolling(VENTANA).mean().pct_change(12) * 100).dropna()
        if va.empty:
            continue
        actual.append({"clave": v.clave, "pct": float(va.iloc[-1]), "fecha": va.index[-1]})
        h = va[va.index >= pd.Timestamp(DESDE_RANGOS)]
        rangos.append({"clave": v.clave, "bajo": float(h.quantile(0.10)), "alto": float(h.quantile(0.90))})

    return ModeloEscenarios(
        constante=float(m.params["const"]), coefs=coefs, r2=float(m.rsquared), n=int(m.nobs),
        sigma=float(np.std(m.resid, ddof=len(m.params))), desde=df.index.min(), hasta=df.index.max(),
        actual=pd.DataFrame(actual), rangos=pd.DataFrame(rangos),
    )


def efecto_pct(modelo: ModeloEscenarios, cambios: dict[str, float], ajuste_propio: float = 0.0) -> dict:
    """Variación anual esperada de la venta (%) y aporte de cada variable (puntos de log → %)."""
    aportes = {}
    for _, r in modelo.coefs.iterrows():
        c = float(cambios.get(r["clave"], 0.0))
        aportes[r["clave"]] = r["beta"] * np.log1p(c / 100)
    log_total = modelo.constante + sum(aportes.values()) + np.log1p(ajuste_propio / 100)
    return {
        "total": (np.exp(log_total) - 1) * 100,
        "tendencia": (np.exp(modelo.constante) - 1) * 100,
        "aportes": {k: (np.exp(v) - 1) * 100 for k, v in aportes.items()},
        "ajuste_propio": ajuste_propio,
    }


def simular(modelo: ModeloEscenarios, historico: pd.Series, meses: list, cambios: dict[str, float],
            ajuste_propio: float = 0.0, z: float = 1.2816) -> pd.DataFrame:
    """ds, ton, lo, hi para cada mes de <meses>. Banda de 80 % con el error del modelo.
    Si el mismo mes del año anterior también es futuro, se usa lo ya simulado."""
    hist = historico.asfreq("MS").fillna(0.0)
    factor = np.exp(np.log1p(efecto_pct(modelo, cambios, ajuste_propio)["total"] / 100))
    banda = np.exp(z * modelo.sigma)
    ref = dict(hist.items())
    filas = []
    for ds in sorted(pd.Timestamp(m) for m in meses):
        base = ref.get(ds - pd.DateOffset(years=1), np.nan)
        ton = base * factor
        ref[ds] = ton
        filas.append({"ds": ds, "ton": ton, "lo": ton / banda, "hi": ton * banda, "mismo_mes_anio_previo": base})
    return pd.DataFrame(filas)


def preajuste(modelo: ModeloEscenarios, nombre: str) -> dict[str, float]:
    """Cambios de cada variable para los escenarios predefinidos."""
    if nombre == "actual" and not modelo.actual.empty:
        return {r["clave"]: round(r["pct"], 1) for _, r in modelo.actual.iterrows()}
    if nombre in ("adverso", "positivo") and not modelo.rangos.empty:
        # Adverso = el extremo histórico que baja la venta (si el efecto es negativo,
        # como las importaciones, es el alto); positivo = el contrario.
        signo = dict(zip(modelo.coefs["clave"], np.sign(modelo.coefs["beta"])))
        sale = {}
        for _, r in modelo.rangos.iterrows():
            sube = signo.get(r["clave"], 1) >= 0
            sale[r["clave"]] = round(r["alto"] if sube == (nombre == "positivo") else r["bajo"], 1)
        return sale
    return {c: 0.0 for c in modelo.coefs.get("clave", [v.clave for v in VARIABLES])}
