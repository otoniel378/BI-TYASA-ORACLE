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
import re
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


# ── Quiebre en formación ─────────────────────────────────────────────────────
# Un quiebre se confirma con MIN_SEGMENTO (6) meses de datos nuevos. Para avisar
# antes: ¿los últimos 3-5 meses se comportan distinto del régimen vigente? Se
# acepta si cortar ahí mejora la verosimilitud más de PENAL_EN_FORMACION·log(n)
# (el BIC de un quiebre confirmado cobra 3·log(n)). Simulado mes a mes 2004-2026
# solo con datos disponibles en cada mes, sobre 50 quiebres Fuertes o Moderados:
# el detector solo los veía en una mediana de 7 meses (14% en ≤3 meses); junto
# con este aviso, en 3 meses (52% en ≤3), con ~0.5 avisos falsos por serie al
# año. Con 3·log(n) avisaba solo 30% de los quiebres y con 4·log(n) 6%.
PENAL_EN_FORMACION = 2.0
MESES_EN_FORMACION = (3, 4, 5)


def _costo(x: np.ndarray) -> float:
    return len(x) * np.log(max(x.var(), VAR_MIN))


def quiebre_en_formacion(precio: pd.Series, desde: pd.Timestamp | None = None) -> dict | None:
    """Si los últimos 3-5 meses ya no se parecen al régimen vigente, devuelve
    desde (primer mes distinto), meses, regimen ("Baja → Alza"), tendencias y
    volatilidades anuales antes/después y meses_para_confirmar. None si no."""
    p = precio.dropna()
    if desde is not None:
        p = p[p.index >= desde]
    r = np.log(p).diff().dropna()
    if len(r) < 3 * MIN_SEGMENTO:
        return None
    cortes = segmentar(r.values)
    tramo = r.iloc[cortes[-1] if cortes else 0:]
    mejor_n, mejor_g = None, PENAL_EN_FORMACION * np.log(len(r))
    for n in MESES_EN_FORMACION:
        if len(tramo) - n < MIN_SEGMENTO:
            continue
        g = _costo(tramo.values) - _costo(tramo.values[:-n]) - _costo(tramo.values[-n:])
        if g > mejor_g:
            mejor_n, mejor_g = n, g
    if mejor_n is None:
        return None
    pre, post = tramo.iloc[:-mejor_n], tramo.iloc[-mejor_n:]
    t_pre, t_post = pre.mean() * 12 * 100, post.mean() * 12 * 100
    return {
        "desde": post.index[0], "meses": mejor_n,
        "regimen": f"{_estado(t_pre)} → {_estado(t_post)}",
        "tendencia_pre_anual": round(t_pre, 1), "tendencia_post_anual": round(t_post, 1),
        "vol_pre_anual": round(pre.std() * np.sqrt(12) * 100, 1),
        "vol_post_anual": round(post.std() * np.sqrt(12) * 100, 1),
        "meses_para_confirmar": MIN_SEGMENTO - mejor_n,
    }


def bandas_normales(precio: pd.Series, ventana: int = 12, hueco: int = 3, k: float = 2.5,
                    meses_vol: int = 36, vol_min: float = 0.02) -> pd.DataFrame:
    """Banda de control para graficar "lo normal", con base LIMPIA (mismo
    principio que detector.detectar_quiebres_automatico, que excluye los días
    recientes): para cada mes,
      - centro = mediana del log del precio en los <ventana> meses que terminan
        <hueco> meses antes (el evento en curso no contamina la referencia);
      - ancho = k × volatilidad mensual de los rendimientos de los <meses_vol>
        meses previos al hueco (piso <vol_min>), escalada por √(meses entre el
        centro de la base y el mes evaluado): un precio se dispersa con el tiempo.
    Antes se usaba la desviación del NIVEL de los 12 meses anteriores: en un
    alza esa desviación crecía con el propio precio y el pico de 2008 del FeMn
    (×3) quedaba "normal". Con esta base, en las 9 series 2000-2026 queda fuera
    ~8% de los meses y se marcan 7 de 8 picos conocidos (2008, 2021-22).
    Columnas: precio, centro, banda_inf, banda_sup, fuera."""
    p = precio.dropna()
    log_p = np.log(p)
    centro = log_p.shift(hueco + 1).rolling(ventana, min_periods=ventana // 2).median()
    vol = log_p.diff().shift(hueco + 1).rolling(meses_vol, min_periods=meses_vol // 2).std().clip(lower=vol_min)
    sd = vol * np.sqrt(hueco + 1 + (ventana - 1) / 2)
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


# ── Casos parecidos: qué hizo el precio después ──────────────────────────────
HORIZONTES_MESES = (3, 6, 12)


def agregar_desempeno_posterior(rupturas: pd.DataFrame, precios: pd.DataFrame) -> pd.DataFrame:
    """Agrega a cada quiebre el cambio % del precio desde que el quiebre se
    CONFIRMA (fecha + MIN_SEGMENTO meses: antes no hay datos suficientes para
    saber el régimen nuevo) hasta +3, +6 y +12 meses después (columnas
    despues_3m, ...). Medir desde el mes del quiebre usaría información que en
    ese momento no se tenía. NaN si aún no pasa ese tiempo. <precios>: salida
    de normalizar_mensual (una columna por serie)."""
    out = rupturas.copy()
    out["confirmado"] = out["fecha"] + pd.DateOffset(months=MIN_SEGMENTO)
    for h in HORIZONTES_MESES:
        col = []
        for _, q in out.iterrows():
            s = precios[q["serie"]]
            base, fut = s.get(q["confirmado"]), s.get(q["confirmado"] + pd.DateOffset(months=h))
            col.append((fut / base - 1) * 100 if pd.notna(base) and pd.notna(fut) and base else np.nan)
        out[f"despues_{h}m"] = col
    return out


def resumen_casos_parecidos(rupturas: pd.DataFrame, regimen: str, excluir: tuple | None = None) -> pd.DataFrame:
    """Para quiebres del mismo <regimen> en todas las series (salida de
    agregar_desempeno_posterior), resumen por horizonte: casos, mediana,
    cuartiles y cuántos subieron. <excluir> = (serie, fecha) del propio quiebre."""
    casos = rupturas[rupturas["regimen"] == regimen]
    if excluir is not None:
        casos = casos[~((casos["serie"] == excluir[0]) & (casos["fecha"] == excluir[1]))]
    filas = []
    for h in HORIZONTES_MESES:
        v = casos[f"despues_{h}m"].dropna()
        if v.empty:
            continue
        filas.append({
            "horizonte": h, "casos": len(v), "mediana": v.median(),
            "p25": v.quantile(0.25), "p75": v.quantile(0.75), "subieron": int((v > 0).sum()),
        })
    return pd.DataFrame(filas)


# ── Tipo de impacto ──────────────────────────────────────────────────────────
TIPOS_IMPACTO = [
    "Geopolítico/conflicto", "Política comercial", "Energía", "Clima/desastre",
    "Oferta/producción", "Macro/financiero", "Logística",
]
MESES_HUELLA = 2
# Bolsa: umbrales fijos (caída de 12% en 3 meses o VIX de 30 = estrés financiero).
UMBRAL_BOLSA, UMBRAL_VIX = -0.12, 30.0
# Demás variables: cuenta como señal un cambio a 3 meses en el 5% más extremo de
# su propia historia. Con umbrales fijos (o ventana de ±3 meses y 10%) casi todo
# quiebre coincidía con "algo": el gas Henry Hub se mueve ±30-60% en 3 meses muy
# seguido. Con ±2 meses y 5%, de 49 quiebres sin evento: 29 macro/financiero,
# 12 sin señal (propios de la aleación) y 8 energía.
CUANTIL_SENAL = 0.95


def huella_impacto(rupturas: pd.DataFrame, mercado: pd.DataFrame) -> pd.DataFrame:
    """Clasifica el tipo de impacto probable de cada quiebre con lo que hizo el
    mercado en ±MESES_HUELLA meses. <mercado>: ancho mensual (índice = primer día
    del mes) con columnas sp500, vix, petroleo_wti, gas_hh, dolar_idx, cobre,
    flete_seco (GOLD_MERCADO_MENSUAL); las que falten se ignoran.

    Solo distingue lo que el mercado puede mostrar (financiero, energía, logística,
    alcance general o propio). Geopolítico, política comercial y clima solo se
    saben por un evento verificado: si el quiebre tiene evento con tipo, ése manda
    (columna tipo_fuente = "evento verificado")."""
    out = rupturas.copy()
    r3 = (mercado / mercado.shift(3) - 1) if not mercado.empty else pd.DataFrame()
    umbral = r3.abs().quantile(CUANTIL_SENAL) if not r3.empty else pd.Series(dtype=float)
    simult, senales_col, probable = [], [], []
    for _, q in out.iterrows():
        cerca = out[(out["serie"] != q["serie"])
                    & ((out["fecha"] - q["fecha"]).abs() <= pd.Timedelta(days=31 * MESES_HUELLA))]
        n_sim = cerca["serie"].nunique()
        desde, hasta = q["fecha"] - pd.DateOffset(months=MESES_HUELLA), q["fecha"] + pd.DateOffset(months=MESES_HUELLA)
        v = r3[(r3.index >= desde) & (r3.index <= hasta)] if not r3.empty else r3
        nivel = mercado[(mercado.index >= desde) & (mercado.index <= hasta)] if not mercado.empty else mercado

        def extremo(col):
            if col not in v.columns or v[col].dropna().empty:
                return None
            s = v[col].dropna()
            return float(s.loc[s.abs().idxmax()])

        senales, tipos = [], []
        sp = v["sp500"].min() if "sp500" in v.columns and not v["sp500"].dropna().empty else None
        vix = nivel["vix"].max() if "vix" in nivel.columns and not nivel["vix"].dropna().empty else None
        if (sp is not None and sp <= UMBRAL_BOLSA) or (vix is not None and vix >= UMBRAL_VIX):
            partes = []
            if sp is not None and sp <= UMBRAL_BOLSA:
                partes.append(f"S&P 500 {sp:+.0%}")
            if vix is not None and vix >= UMBRAL_VIX:
                partes.append(f"VIX {vix:.0f}")
            senales.append("Caída de la bolsa (" + ", ".join(partes) + ")")
            tipos.append("Macro/financiero")
        for col, nombre, tipo_col, solo_alza in (
            ("petroleo_wti", "Petróleo", "Energía", False), ("gas_hh", "Gas", "Energía", False),
            ("flete_seco", "Flete granel", "Logística", True), ("dolar_idx", "Dólar", "Macro/financiero", False),
            ("cobre", "Cobre", "Macro/financiero", False),
        ):
            x = extremo(col)
            if x is None or col not in umbral.index:
                continue
            if (x if solo_alza else abs(x)) >= umbral[col]:
                senales.append(f"{nombre} {x:+.0%}")
                tipos.append(tipo_col)
        if n_sim >= 2:
            senales.append(f"{n_sim} aleaciones más quebraron en ±{MESES_HUELLA} meses")

        if tipos:
            tipo = tipos[0]
        elif n_sim >= 2:
            tipo = "Macro/financiero"   # choque general sin señal de mercado clara: demanda global
        else:
            tipo = "Oferta/producción"  # solo esta aleación: algo propio de su oferta (minas, plantas, aranceles)
        simult.append(n_sim)
        senales_col.append("; ".join(senales) if senales else "Sin movimientos fuertes de mercado")
        probable.append(tipo)

    out["aleaciones_simultaneas"] = simult
    out["alcance"] = ["Varias aleaciones" if n >= 2 else "Solo esta aleación" for n in simult]
    out["senales_mercado"] = senales_col
    out["tipo_probable"] = probable
    tipo_evento = out["evento_tipo"] if "evento_tipo" in out.columns else pd.Series([None] * len(out), index=out.index)
    out["tipo_impacto"] = tipo_evento.where(tipo_evento.notna(), out["tipo_probable"])
    out["tipo_fuente"] = np.where(tipo_evento.notna(), "evento verificado", "huella de mercado")
    return out


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
    for col in ("evento_id", "evento_nombre", "evento_descripcion", "evento_fuente", "evento_inicio", "evento_tipo"):
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
        tipo = mejor.get("tipo_impacto")
        out.at[i, "evento_tipo"] = tipo if isinstance(tipo, str) and tipo else None
    return out


# ── Tipo de impacto de las noticias ──────────────────────────────────────────
# Las noticias casi nunca hablan de una ferroaleación en particular: se separan
# por el tipo de impacto que pueden tener. Orden de prioridad: grupo de búsqueda
# (noticias.GRUPOS_IMPACTO_GLOBAL ya busca por tipo), palabras del título (la
# razón de Gemini menciona riesgos genéricos y metía ruido) y al final la
# variable que asignó Gemini.
PATRONES_TIPO_NOTICIA = {
    "Geopolítico/conflicto": r"guerra|\bwar\b|sanci[oó]n|sanction|conflicto|conflict|ucrania|ukrain|israel|"
                             r"\bir[aá]n\b|mar rojo|red sea|hut[ií]es|houthi|militar|military|export controls?|"
                             r"controles? de exportaci",
    "Política comercial": r"arancel|tariff|antidumping|anti-dumping|cuota|quota|t-mec|usmca|secci[oó]n 232|"
                          r"section 232|salvaguarda|safeguard|export ban|prohibici[oó]n de export",
    "Energía": r"petr[oó]leo|crude oil|\boil price|opep|opec|gas natural|natural gas|"
               r"precios? de la (energ|electric|luz)|tarifas? el[eé]ctric|electricity price|energy price|"
               r"apag[oó]n|blackout|racionamiento|power (rationing|shortage|cuts?)",
    "Clima/desastre": r"hurac[aá]n|hurricane|tif[oó]n|typhoon|cicl[oó]n|cyclone|\bsismo|terremoto|earthquake|"
                      r"inundaci|flood|sequ[ií]a|drought|wildfire",
    "Logística": r"\bfletes?\b|freight|naviera|shipping|contenedor|container|ferrocarril|railway|transnet|"
                 r"congesti[oó]n portuaria|port congestion|bloqueo",
    "Macro/financiero": r"\bfed\b|reserva federal|federal reserve|tasas? de inter[eé]s|interest rates?|inflaci|"
                        r"recesi[oó]n|recession|\bpib\b|\bgdp\b|tipo de cambio|peso mexicano|superpeso|"
                        r"[ií]ndice del d[oó]lar|dollar index|banxico|\bpmi\b|est[ií]mulo|stimulus|"
                        r"desplome|selloff|sell-off|crash",
    "Oferta/producción": r"\bmina\b|\bminas\b|minera|\bmine\b|mining|producci[oó]n de|production cut|output|"
                         r"fundici[oó]n|smelter|cierre de (planta|mina|horno)|shutdown|recorte de producci",
}
# energia_electricidad no se mapea: Gemini la usa también para notas de
# sustentabilidad; las de precios de energía las atrapa el patrón.
VARIABLE_A_TIPO = {
    "aranceles_comercio": "Política comercial",
    "tipo_cambio": "Macro/financiero", "demanda_general": "Macro/financiero",
    "ferroaleaciones": "Oferta/producción", "mineral_hierro": "Oferta/producción",
    "chatarra_scrap": "Oferta/producción", "carbon_coquizable": "Oferta/producción",
    "china_sobrecapacidad": "Oferta/producción", "zinc_galvanizado": "Oferta/producción",
}
# Grupos de búsqueda anteriores (noticias.GRUPOS_INTERNACIONAL) con tipo claro
GRUPO_A_TIPO = {"Macroeconomía": "Macro/financiero", "Geopolítica y Logística": "Geopolítico/conflicto",
                "Defensa Comercial": "Política comercial", "Ferroaleaciones": "Oferta/producción"}
# Estudios de mercado y notas de empresas sin impacto en precios de insumos
PATRON_RUIDO_NOTICIA = r"tama[nñ]o del mercado|market size|informe de previsi|forecast report|crecimiento \[20"


def tipo_impacto_noticias(noticias: pd.DataFrame) -> pd.DataFrame:
    """Agrega 'tipo_impacto' (uno de TIPOS_IMPACTO o None si no aplica) a
    noticias de load_noticias_periodo y quita estudios de mercado."""
    if noticias.empty:
        return noticias.assign(tipo_impacto=pd.Series(dtype=object))
    out = noticias[~noticias["titulo"].fillna("").str.contains(PATRON_RUIDO_NOTICIA, case=False, regex=True)].copy()
    texto = out["titulo"].fillna("").str.lower()
    grupo = out["grupo_tematico"] if "grupo_tematico" in out else pd.Series(None, index=out.index)
    tipos = []
    for i in out.index:
        tipo = grupo[i] if grupo[i] in TIPOS_IMPACTO else None
        tipo = tipo or next((t for t, p in PATRONES_TIPO_NOTICIA.items() if re.search(p, texto[i])), None)
        tipos.append(tipo or GRUPO_A_TIPO.get(grupo[i]) or VARIABLE_A_TIPO.get(out.at[i, "variable_principal"]))
    out["tipo_impacto"] = tipos
    return out
