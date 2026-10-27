"""
rupturas.py — Detección de MÚLTIPLES quiebres estructurales en series de
precio largas (ferroaleaciones Fastmarkets), con validación estadística de
cada quiebre.

A diferencia de detector.py (una fecha de corte dada por el usuario o los
últimos días), aquí la serie completa se segmenta en regímenes:

  1. Normalización: precio vigente al cierre de cada mes, escala log,
     índice base 100 para comparar unidades distintas ($/lb, ¢/lb, $/lt).
     Las ferroaleaciones de Fastmarkets son cotizaciones escalonadas: el
     precio solo cambia cuando hay nueva cotización (antes de 2015 el
     archivo trae solo las fechas de cambio; después repite el valor cada
     semana). Por eso se arrastra la última cotización (ffill) y NO se
     interpola: interpolar inventaría movimientos que no existieron.
  2. Detección: segmentación óptima (programación dinámica) de los
     rendimientos mensuales log por cambio de media y varianza; el número
     de quiebres se elige con BIC. Es el enfoque de Bai-Perron adaptado a
     rendimientos — en niveles de precio (caminata aleatoria) cualquier
     segmentación "encuentra" quiebres espurios.
  3. Validación por quiebre, contra el régimen anterior y el siguiente:
       - Welch t-test: ¿cambió la tendencia (rendimiento medio)?
       - Levene (mediana): ¿cambió la volatilidad?
       - Chow (detector.chow_test) sobre el log del precio: ¿cambió la
         relación nivel-tiempo?
     Evidencia "Fuerte" si la tendencia o la volatilidad cambian con
     p < 0.01, "Moderada" si p < 0.05. Con decenas de quiebres probados a
     la vez, algunos "Moderados" pueden ser azar; los "Fuertes" no.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import levene, ttest_ind

from mercado_noticias.analytics.detector import chow_test

MIN_SEGMENTO = 6       # meses mínimos por régimen
MAX_QUIEBRES = 15
ALFA_FUERTE, ALFA = 0.01, 0.05
# Varianza mínima de rendimientos mensuales (desv. 1%): meses sin nueva
# cotización tienen rendimiento exactamente 0, y sin piso un tramo "sin
# cotizar" parecería un régimen de volatilidad cero.
VAR_MIN = 0.01 ** 2


@dataclass
class Ruptura:
    serie: str
    fecha: pd.Timestamp          # primer mes del régimen nuevo
    regimen: str                 # "Estable → Alza", "Alza → Baja", ... (tendencia antes → después)
    direccion: str               # "Sube" | "Baja": la tendencia nueva vs. la anterior
    volatilidad: str             # "Sube" | "Baja" | "Sin cambio" (Levene, p < ALFA)
    tendencia_pre_anual: float   # % anualizado
    tendencia_post_anual: float
    vol_pre_anual: float         # % anualizado
    vol_post_anual: float
    cambio_precio_6m: float | None  # % promedio 6m después vs 6m antes
    p_tendencia: float
    p_volatilidad: float
    F_chow: float | None
    p_chow: float | None
    evidencia: str               # "Fuerte" | "Moderada" | "Débil"
    significativo: bool
    meses_pre: int
    meses_post: int


# ── Normalización ────────────────────────────────────────────────────────────
def normalizar_mensual(df_long: pd.DataFrame) -> pd.DataFrame:
    """df_long: fecha, serie, valor -> ancho mensual (una columna por serie)
    con la cotización vigente al cierre de cada mes. Se arrastra la última
    cotización entre su primer y su último dato; nunca se extrapola."""
    df = df_long.dropna(subset=["valor"])
    df = df[df["valor"] > 0].copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha")
    df["mes"] = df["fecha"].dt.to_period("M").dt.to_timestamp()
    ancho = df.groupby(["mes", "serie"])["valor"].last().unstack("serie").sort_index().asfreq("MS")
    for c in ancho.columns:
        ultimo = ancho[c].last_valid_index()
        ancho.loc[:ultimo, c] = ancho.loc[:ultimo, c].ffill()
    ancho.index.name = "fecha"
    return ancho


def indexar(ancho: pd.DataFrame, base: pd.Timestamp) -> pd.DataFrame:
    """Índice base 100 en el mes <base> (o el primer dato posterior si esa
    serie aún no existía)."""
    out = {}
    for c in ancho.columns:
        s = ancho[c].dropna()
        ref = s[s.index >= base]
        if ref.empty:
            continue
        out[c] = s / ref.iloc[0] * 100
    return pd.DataFrame(out)


# ── Detección ────────────────────────────────────────────────────────────────
def _costos_desde(cs1: np.ndarray, cs2: np.ndarray, j: int, i_validos: np.ndarray) -> np.ndarray:
    """Costo (-2 log-verosimilitud Gaussiana, sin constante) de los segmentos
    r[i:j] para todos los i en <i_validos>: n·log(varianza MLE)."""
    n = j - i_validos
    s1 = cs1[j] - cs1[i_validos]
    s2 = cs2[j] - cs2[i_validos]
    var = np.maximum(s2 / n - (s1 / n) ** 2, VAR_MIN)
    return n * np.log(var)


def segmentar(r: np.ndarray, min_seg: int = MIN_SEGMENTO, max_k: int = MAX_QUIEBRES) -> list[int]:
    """Índices de quiebre (inicio de cada régimen nuevo) que minimizan el BIC."""
    n = len(r)
    max_k = min(max_k, n // min_seg - 1)
    if max_k < 1:
        return []
    cs1 = np.concatenate([[0.0], np.cumsum(r)])
    cs2 = np.concatenate([[0.0], np.cumsum(r ** 2)])

    INF = np.inf
    # F[k, j] = costo mínimo de r[0:j] con k quiebres; P guarda el último quiebre
    F = np.full((max_k + 1, n + 1), INF)
    P = np.zeros((max_k + 1, n + 1), dtype=int)
    for j in range(min_seg, n + 1):
        F[0, j] = _costos_desde(cs1, cs2, j, np.array([0]))[0]
    for k in range(1, max_k + 1):
        for j in range((k + 1) * min_seg, n + 1):
            i_validos = np.arange(k * min_seg, j - min_seg + 1)
            tot = F[k - 1, i_validos] + _costos_desde(cs1, cs2, j, i_validos)
            m = int(np.argmin(tot))
            F[k, j], P[k, j] = tot[m], i_validos[m]

    # BIC: por régimen se estiman media y varianza, más la fecha de cada quiebre
    bic = [F[k, n] + (3 * k + 2) * np.log(n) for k in range(max_k + 1)]
    k_opt = int(np.argmin(bic))
    cortes, j = [], n
    for k in range(k_opt, 0, -1):
        j = P[k, j]
        cortes.append(j)
    return sorted(cortes)


TENDENCIA_ESTABLE = 5.0   # % anual: entre -5% y +5% la tendencia se lee como estable


def _estado(tendencia_anual: float) -> str:
    if tendencia_anual > TENDENCIA_ESTABLE:
        return "Alza"
    if tendencia_anual < -TENDENCIA_ESTABLE:
        return "Baja"
    return "Estable"


def detectar_rupturas(precio: pd.Series, nombre: str, desde: pd.Timestamp | None = None) -> list[Ruptura]:
    """Segmenta una serie mensual de precio (salida de normalizar_mensual) y
    valida cada quiebre contra sus regímenes vecinos."""
    p = precio.dropna()
    if desde is not None:
        p = p[p.index >= desde]
    log_p = np.log(p)
    r = log_p.diff().dropna()
    if len(r) < 3 * MIN_SEGMENTO:
        return []

    cortes = segmentar(r.values)
    limites = [0] + cortes + [len(r)]
    resultado = []
    for b in range(1, len(limites) - 1):
        ini, corte, fin = limites[b - 1], limites[b], limites[b + 1]
        pre, post = r.iloc[ini:corte], r.iloc[corte:fin]
        fecha = r.index[corte]

        _, p_t = ttest_ind(post, pre, equal_var=False)
        _, p_v = levene(pre, post, center="median")
        tramo = log_p[(log_p.index >= pre.index[0] - pd.offsets.MonthBegin(1)) & (log_p.index <= post.index[-1])]
        F, p_c = chow_test(tramo, fecha)

        antes = p[(p.index < fecha) & (p.index >= fecha - pd.DateOffset(months=6))]
        despues = p[(p.index >= fecha) & (p.index < fecha + pd.DateOffset(months=6))]
        cambio = (despues.mean() / antes.mean() - 1) * 100 if len(antes) and len(despues) else None

        t_pre, t_post = pre.mean() * 12 * 100, post.mean() * 12 * 100
        v_pre, v_post = pre.std() * np.sqrt(12) * 100, post.std() * np.sqrt(12) * 100
        regimen = f"{_estado(t_pre)} → {_estado(t_post)}"
        direccion = "Sube" if t_post > t_pre else "Baja"
        volatilidad = ("Sube" if v_post > v_pre else "Baja") if p_v < ALFA else "Sin cambio"
        p_min = min(p_t, p_v)
        evidencia = "Fuerte" if p_min < ALFA_FUERTE else "Moderada" if p_min < ALFA else "Débil"

        resultado.append(Ruptura(
            serie=nombre, fecha=fecha, regimen=regimen, direccion=direccion, volatilidad=volatilidad,
            tendencia_pre_anual=round(t_pre, 1), tendencia_post_anual=round(t_post, 1),
            vol_pre_anual=round(v_pre, 1), vol_post_anual=round(v_post, 1),
            cambio_precio_6m=round(cambio, 1) if cambio is not None else None,
            p_tendencia=round(float(p_t), 4), p_volatilidad=round(float(p_v), 4),
            F_chow=F, p_chow=p_c,
            evidencia=evidencia,
            significativo=bool(p_min < ALFA),
            meses_pre=len(pre), meses_post=len(post),
        ))
    return resultado


def bandas_normales(precio: pd.Series, ventana: int = 12, k: float = 2.5, sd_min: float = 0.05) -> pd.DataFrame:
    """Banda de control móvil para graficar "lo normal": para cada mes, el
    promedio del log del precio en los <ventana> meses ANTERIORES ± k
    desviaciones de ese mismo periodo (mínimo <sd_min>, ~5%, para que un
    tramo plano sin cotizaciones nuevas no deje una banda de ancho cero).
    Con k=2.5 y piso 5% queda fuera ~8% de los meses en las 9 series
    (2000-2026); con k=2 era ~14%, demasiado ruido en escalones normales.
    Un mes está "fuera" si el precio sale de la banda que el año previo
    marcaba como normal. Columnas: precio, centro, banda_inf, banda_sup, fuera."""
    p = precio.dropna()
    log_p = np.log(p)
    previo = log_p.shift(1).rolling(ventana, min_periods=ventana // 2)
    centro = previo.mean()
    sd = previo.std().clip(lower=sd_min)
    out = pd.DataFrame({
        "precio": p,
        "centro": np.exp(centro),
        "banda_inf": np.exp(centro - k * sd),
        "banda_sup": np.exp(centro + k * sd),
    })
    out["fuera"] = (out["precio"] < out["banda_inf"]) | (out["precio"] > out["banda_sup"])
    return out


def rupturas_a_dataframe(rupturas: list[Ruptura]) -> pd.DataFrame:
    if not rupturas:
        return pd.DataFrame()
    return pd.DataFrame([vars(x) for x in rupturas]).sort_values("fecha", ascending=False).reset_index(drop=True)


# ── Vinculación con eventos ──────────────────────────────────────────────────
# El precio mensual reacciona con rezago (cotizaciones escalonadas, contratos):
# un quiebre se vincula a un evento si su fecha cae entre 2 meses antes del
# inicio y 4 meses después del fin (o del inicio, si es puntual).
MESES_ANTES_EVENTO, MESES_DESPUES_EVENTO = 2, 4


def vincular_eventos(rupturas: pd.DataFrame, eventos: pd.DataFrame) -> pd.DataFrame:
    """Agrega a cada quiebre el evento curado más cercano que mencione su serie
    en VARIABLES_RELACIONADAS (columnas evento_*). Sin evento -> None: se deja
    sin explicar a propósito, para no inventar relaciones."""
    out = rupturas.copy()
    for col in ("evento_id", "evento_nombre", "evento_descripcion", "evento_fuente", "evento_inicio"):
        out[col] = None
    if out.empty or eventos.empty:
        return out
    ev = eventos.copy()
    ev["fin_efectivo"] = ev["fecha_fin"].fillna(ev["fecha_inicio"])
    ev["vars"] = ev["variables_relacionadas"].fillna("").str.split(",").map(lambda v: {x.strip() for x in v})
    for i, q in out.iterrows():
        cand = ev[ev["vars"].map(lambda v: q["serie"] in v)]
        desde = cand["fecha_inicio"] - pd.DateOffset(months=MESES_ANTES_EVENTO)
        hasta = cand["fin_efectivo"] + pd.DateOffset(months=MESES_DESPUES_EVENTO)
        cand = cand[(q["fecha"] >= desde) & (q["fecha"] <= hasta)]
        if cand.empty:
            continue
        mejor = cand.loc[(cand["fecha_inicio"] - q["fecha"]).abs().idxmin()]
        out.at[i, "evento_id"] = mejor["id"]
        out.at[i, "evento_nombre"] = mejor["nombre"]
        out.at[i, "evento_descripcion"] = mejor["descripcion"]
        out.at[i, "evento_fuente"] = mejor["fuente"]
        out.at[i, "evento_inicio"] = mejor["fecha_inicio"]
    return out
