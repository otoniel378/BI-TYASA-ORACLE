"""
calidad_datos.py — Reglas deterministas de calidad y frescura de los datos de TYASA BI.

Dos tipos de revisión, ambas de solo lectura sobre Oracle:
  · Frescura: último dato de cada fuente contra lo que se espera según su
    actualización (diaria, mensual, manual). FUENTES es el catálogo único.
  · Reglas de contenido: que Oro cuadre con Plata y Plata con Bronce, toneladas
    válidas, meses atípicos o vacíos, variables de mercado que dejaron de llegar,
    saltos sospechosos, indicadores de INEGI rezagados y cargas que fallan en silencio.

Estados: ok | aviso | falla. Lo usan la página "Estado de los datos" (INICIO),
el indicador de la barra lateral (core/components/frescura.py) y la bandeja de
alertas (core/alertas.py), que también llega al resumen semanal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from core.db_connector import run_query_params, table_ref

ESTADOS = ("falla", "aviso", "ok")

# Reglas de contenido
TOLERANCIA_CUADRE = 0.005          # 0.5 % de diferencia entre capas
MESES_ATIPICOS = 24                # ventana para comparar cada mes de venta
FACTOR_ATIPICO = 3.0               # mes > 3× o < 1/3 de la mediana
DIAS_VARIABLE_SIN_DATO = 5         # una variable de mercado sin dato vs. el resto
SALTO_DIARIO_PCT = 30              # cambio diario sospechoso en precios
VARIABLES_VOLATILES = {"VIX", "Gas_TTF_Europa", "Gas_HenryHub_USD", "ZIM_Contenedor", "StarBulk", "Matson_Pacifico"}
MESES_INEGI_REZAGO = 3             # indicador con 3+ meses menos que el resto


@dataclass(frozen=True)
class Fuente:
    nombre: str
    grupo: str               # "Aceros Planos" | "Mercado Global" | "Sistema"
    sql: str                 # devuelve una columna F con la fecha del último dato
    formato: str             # fecha | periodo (YYYY-MM: cuenta desde el fin del mes)
    se_actualiza: str
    dias_aviso: int
    dias_falla: int
    prioridad: str = "media"     # prioridad en la bandeja cuando falla
    secciones: tuple = ()        # secciones de app.py donde se muestra en la barra lateral


def _t(n: str) -> str:
    return table_ref(n)


FUENTES = (
    Fuente("Ventas (SAP)", "Aceros Planos", f"SELECT MAX(FECHAEMB) F FROM {_t('SILVER_VENTAS_LIMPIAS')}",
           "fecha", "manual (exportación de SAP)", 45, 90, "alta", ("aceros_planos",)),
    Fuente("Variables de mercado", "Mercado Global", f"SELECT MAX(FECHA) F FROM {_t('GOLD_VARIABLES_MERCADO')}",
           "fecha", "diaria (L–V 8:45)", 4, 10, "media", ("mercado", "aceros_planos")),
    Fuente("Noticias", "Mercado Global", f"SELECT MAX(FECHA_PUB) F FROM {_t('GOLD_SENTIMIENTO_NOTICIAS')}",
           "fecha", "diaria", 3, 7, "media", ("mercado", "mas_info")),
    Fuente("Decretos del DOF", "Mercado Global", f"SELECT MAX(ANALIZADO_EN) F FROM {_t('GOLD_ALERTAS_DOF')}",
           "fecha", "diaria", 3, 7, "media", ("mercado",)),
    Fuente("Indicadores INEGI", "Mercado Global", f"SELECT MAX(FECHA) F FROM {_t('GOLD_INDICADORES_INEGI')}",
           "periodo", "mensual (día 10)", 75, 120, "media", ("mercado", "aceros_planos")),
    Fuente("Mercado mensual", "Mercado Global", f"SELECT MAX(FECHA) F FROM {_t('GOLD_MERCADO_MENSUAL')}",
           "fecha", "mensual", 45, 75, "media", ()),
    Fuente("Comercio exterior (SNICE)", "Mercado Global", f"SELECT MAX(PERIODO) F FROM {_t('GOLD_SNICE_RESUMEN_MENSUAL')}",
           "periodo", "mensual (día 5)", 70, 100, "media", ("mercado",)),
    Fuente("Comercio exterior (CANACERO)", "Mercado Global", f"SELECT MAX(PERIODO_MES) F FROM {_t('BRONZE_CANACERO_COMEX')}",
           "periodo", "manual", 120, 200, "media", ("mercado",)),
    Fuente("Precios de ferroaleaciones", "Mercado Global", f"SELECT MAX(FECHA) F FROM {_t('GOLD_PRECIOS_FASTMARKETS')}",
           "fecha", "manual (Fastmarkets)", 45, 90, "media", ("mercado",)),
    Fuente("Semáforo de ferroaleaciones", "Mercado Global", f"SELECT MAX(CARGADO_EN) F FROM {_t('GOLD_SEMAFORO_FERROS')}",
           "fecha", "mensual (día 5)", 40, 70, "media", ()),
    # PortWatch publica cada semana con ~10 días de retraso
    Fuente("Tráfico marítimo (PortWatch)", "Mercado Global", f"SELECT MAX(FECHA) F FROM {_t('GOLD_TRAFICO_PASOS')}",
           "fecha", "diaria (L–V 10:00; PortWatch publica semanal)", 21, 35, "media", ("mercado",)),
    Fuente("Selección de modelos", "Sistema", f"SELECT MAX(CALCULADO_EN) F FROM {_t('GOLD_SELECCION_MODELO')}",
           "fecha", "mensual (día 6)", 40, 70, "media", ()),
)


@dataclass
class Revision:
    grupo: str
    fuente: str
    regla: str
    estado: str              # ok | aviso | falla
    detalle: str = ""
    fecha: date | None = None
    tipo: str = "contenido"  # frescura | contenido
    prioridad: str = "media"


def _q(sql: str, params: dict | None = None) -> pd.DataFrame:
    df = run_query_params(sql, params or {})
    df.columns = [c.upper() for c in df.columns]
    return df


def _fecha(valor, formato: str) -> pd.Timestamp | None:
    if valor is None or pd.isna(valor):
        return None
    if formato == "periodo":      # el dato de un mes está completo al terminar el mes
        return pd.Timestamp(str(valor)[:7] + "-01") + pd.offsets.MonthBegin(1)
    return pd.Timestamp(valor).normalize()


_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _mes(valor) -> str:
    t = pd.Timestamp(str(valor)[:7] + "-01")
    return f"{_MESES[t.month - 1]} {t.year}"


def _fmt(f) -> str:
    return f"{pd.Timestamp(f):%d/%m/%Y}"


def _dias_txt(d: int) -> str:
    return "hoy" if d <= 0 else ("hace 1 día" if d == 1 else f"hace {d} días")


# ── Frescura ──────────────────────────────────────────────────────────────────
def revisar_frescura(hoy: date) -> list[Revision]:
    out = []
    for f in FUENTES:
        try:
            v = _q(f.sql)["F"].iloc[0]
        except Exception as e:
            out.append(Revision(f.grupo, f.nombre, "Se puede consultar", "falla", str(e)[:160],
                                tipo="frescura", prioridad=f.prioridad))
            continue
        ult = _fecha(v, f.formato)
        if ult is None:
            out.append(Revision(f.grupo, f.nombre, "Tiene datos", "falla", "La tabla está vacía.",
                                tipo="frescura", prioridad=f.prioridad))
            continue
        d = (pd.Timestamp(hoy) - ult).days
        estado = "falla" if d > f.dias_falla else ("aviso" if d > f.dias_aviso else "ok")
        dato = _mes(v) if f.formato == "periodo" else _fmt(v)
        out.append(Revision(f.grupo, f.nombre, "Al día", estado,
                            f"Último dato: {dato} ({_dias_txt(d)}). Se actualiza: {f.se_actualiza}.",
                            ult.date(), "frescura", f.prioridad))
    return out


# ── Reglas de contenido: ventas ───────────────────────────────────────────────
def reglas_ventas(hoy: date) -> list[Revision]:
    g, out = "Aceros Planos", []
    s = _q(f"""SELECT MAX(FECHAEMB) F, SUM(PESO_TON) T, COUNT(DISTINCT PRODUCTO_LIMPIO) P,
                      COUNT(DISTINCT CLIENTE) C, COUNT(*) N,
                      SUM(CASE WHEN PESO_TON IS NULL OR PESO_TON <= 0 THEN 1 ELSE 0 END) MAL,
                      SUM(CASE WHEN CLIENTE IS NULL OR PRODUCTO_LIMPIO IS NULL THEN 1 ELSE 0 END) SIN
               FROM {_t('SILVER_VENTAS_LIMPIAS')}""").iloc[0]
    b = _q(f"SELECT MAX(FECHAEMB) F FROM {_t('BRONZE_VENTAS_RAW')}").iloc[0]
    o = _q(f"""SELECT (SELECT MAX(PERIODO) FROM {_t('GOLD_DEMANDA_MENSUAL')}) F,
                      (SELECT SUM(PESO_TON) FROM {_t('GOLD_DEMANDA_MENSUAL')}) T,
                      (SELECT COUNT(*) FROM {_t('GOLD_DEMANDA_PRODUCTO')}) P,
                      (SELECT COUNT(*) FROM {_t('GOLD_DEMANDA_CLIENTE')}) C FROM DUAL""").iloc[0]

    # Las capas están al mismo corte (si Bronce es más nuevo, falta correr Plata / Oro).
    if pd.Timestamp(b["F"]) > pd.Timestamp(s["F"]):
        out.append(Revision(g, "Ventas (SAP)", "Plata al día con Bronce", "falla",
                            f"Bronce llega al {_fmt(b['F'])} y Plata al {_fmt(s['F'])}: falta correr transform_to_silver.",
                            prioridad="alta"))
    else:
        out.append(Revision(g, "Ventas (SAP)", "Plata al día con Bronce", "ok", f"Ambas al {_fmt(s['F'])}."))
    mes_plata = pd.Timestamp(s["F"]).to_period("M")
    if pd.Timestamp(o["F"]).to_period("M") < mes_plata:
        out.append(Revision(g, "Ventas (SAP)", "Oro al día con Plata", "falla",
                            f"Oro llega a {_mes(o['F'])} y Plata a {_mes(mes_plata)}: falta correr transform_to_gold.",
                            prioridad="alta"))
    else:
        out.append(Revision(g, "Ventas (SAP)", "Oro al día con Plata", "ok", f"Ambas a {_mes(mes_plata)}."))

    # Oro cuadra con Plata (toneladas, productos, clientes).
    dif = abs(float(o["T"] or 0) - float(s["T"] or 0)) / max(float(s["T"] or 0), 1)
    cuadra = dif <= TOLERANCIA_CUADRE and int(o["P"]) == int(s["P"]) and int(o["C"]) == int(s["C"])
    out.append(Revision(g, "Ventas (SAP)", "Oro cuadra con Plata", "ok" if cuadra else "falla",
                        f"Toneladas: Plata {float(s['T']):,.0f} · Oro {float(o['T']):,.0f}. "
                        f"Productos: {int(s['P'])} · {int(o['P'])}. Clientes: {int(s['C'])} · {int(o['C'])}.",
                        prioridad="alta"))

    # Registros válidos.
    mal, sin = int(s["MAL"]), int(s["SIN"])
    out.append(Revision(g, "Ventas (SAP)", "Toneladas, cliente y producto válidos",
                        "ok" if mal + sin == 0 else ("falla" if (mal + sin) / max(int(s["N"]), 1) > 0.01 else "aviso"),
                        f"{int(s['N']):,} embarques; {mal} sin peso o con peso ≤ 0; {sin} sin cliente o producto."))

    # Meses vacíos o atípicos (sin el mes en curso, que suele estar incompleto).
    m = _q(f"""SELECT TRUNC(FECHAEMB, 'MM') MES, SUM(PESO_TON) T FROM {_t('SILVER_VENTAS_LIMPIAS')}
               GROUP BY TRUNC(FECHAEMB, 'MM') ORDER BY 1""")
    serie = m.set_index(pd.to_datetime(m["MES"]))["T"].astype(float).asfreq("MS").fillna(0.0)
    serie = serie[serie.index < mes_plata.to_timestamp()]
    vacios = [f"{d:%m/%Y}" for d, v in serie.items() if v == 0]
    out.append(Revision(g, "Ventas (SAP)", "Sin meses vacíos", "aviso" if vacios else "ok",
                        ("Meses sin embarques: " + ", ".join(vacios)) if vacios else "Todos los meses tienen embarques."))
    rec = serie.tail(MESES_ATIPICOS)
    med = rec.median()
    raros = rec[(rec > FACTOR_ATIPICO * med) | ((rec < med / FACTOR_ATIPICO) & (rec > 0))]
    out.append(Revision(g, "Ventas (SAP)", "Sin meses atípicos", "aviso" if not raros.empty else "ok",
                        ("Revisar: " + ", ".join(f"{d:%m/%Y} ({v:,.0f} t)" for d, v in raros.items())
                         + f" vs. mediana de {med:,.0f} t.") if not raros.empty
                        else f"Últimos {len(rec)} meses dentro de 1/3 y 3× la mediana ({med:,.0f} t)."))
    return out


# ── Reglas de contenido: mercado e INEGI ─────────────────────────────────────
def reglas_mercado(hoy: date) -> list[Revision]:
    g, out = "Mercado Global", []
    desde = (pd.Timestamp(hoy) - pd.Timedelta(days=40)).to_pydatetime()
    df = _q(f"SELECT NOMBRE, FECHA, VALOR FROM {_t('GOLD_VARIABLES_MERCADO')} WHERE FECHA >= :desde", {"desde": desde})
    if df.empty:
        return [Revision(g, "Variables de mercado", "Variables completas", "falla", "Sin datos en los últimos 40 días.")]
    df["FECHA"] = pd.to_datetime(df["FECHA"])
    ult = df.groupby("NOMBRE")["FECHA"].max()
    atras = ult[ult < ult.max() - pd.Timedelta(days=DIAS_VARIABLE_SIN_DATO)]
    out.append(Revision(g, "Variables de mercado", "Todas las variables llegan", "aviso" if not atras.empty else "ok",
                        ("Dejaron de llegar: " + ", ".join(f"{n} (último {_fmt(f)})" for n, f in atras.items()))
                        if not atras.empty else f"Las {len(ult)} variables tienen dato reciente."))

    df = df.sort_values(["NOMBRE", "FECHA"])
    df["PCT"] = df.groupby("NOMBRE")["VALOR"].pct_change() * 100
    saltos = df[(df["PCT"].abs() > SALTO_DIARIO_PCT) & ~df["NOMBRE"].isin(VARIABLES_VOLATILES)]
    out.append(Revision(g, "Variables de mercado", "Sin saltos sospechosos", "aviso" if not saltos.empty else "ok",
                        ("Revisar: " + ", ".join(f"{r.NOMBRE} {r.PCT:+.0f} % el {_fmt(r.FECHA)}"
                                                 for r in saltos.head(5).itertuples()))
                        if not saltos.empty else f"Ningún cambio diario mayor a {SALTO_DIARIO_PCT} % en 40 días."))
    return out


def reglas_inegi(hoy: date) -> list[Revision]:
    g, out = "Mercado Global", []
    df = _q(f"""SELECT NOMBRE, MAX(FECHA) F FROM {_t('GOLD_INDICADORES_INEGI')}
                WHERE NOMBRE NOT LIKE '%Anual%' GROUP BY NOMBRE""")
    df["F"] = pd.to_datetime(df["F"].astype(str).str[:7] + "-01", errors="coerce")
    tope = df["F"].max()
    atras = df[df["F"] <= tope - pd.DateOffset(months=MESES_INEGI_REZAGO)].sort_values("F")
    out.append(Revision(g, "Indicadores INEGI", "Indicadores al mismo mes", "aviso" if not atras.empty else "ok",
                        (f"{len(atras)} indicadores con {MESES_INEGI_REZAGO}+ meses de atraso: "
                         + ", ".join(f"{r.NOMBRE} ({r.F:%m/%Y})" for r in atras.head(6).itertuples())
                         + ("…" if len(atras) > 6 else ""))
                        if not atras.empty else f"Los {len(df)} indicadores mensuales llegan a {tope:%m/%Y} o casi."))

    # La carga de contexto de Planos ya falló en silencio (columna 'Clave'): se revisa explícitamente.
    try:
        from aceros_planos.negros.loaders_contexto import CLAVES_INEGI_PLANOS, load_alertas_inegi_planos
        ctx = load_alertas_inegi_planos()
        faltan = sorted(set(CLAVES_INEGI_PLANOS) - set(ctx.get("Clave", pd.Series(dtype=str)).astype(str)))
        out.append(Revision("Aceros Planos", "Indicadores INEGI", "Contexto de mercado de Planos completo",
                            "falla" if len(faltan) == len(CLAVES_INEGI_PLANOS) else ("aviso" if faltan else "ok"),
                            (f"Faltan {len(faltan)} de {len(CLAVES_INEGI_PLANOS)} indicadores (claves {', '.join(faltan)})."
                             if faltan else f"Los {len(CLAVES_INEGI_PLANOS)} indicadores de Planos cargan bien.")))
    except Exception as e:
        out.append(Revision("Aceros Planos", "Indicadores INEGI", "Contexto de mercado de Planos completo",
                            "falla", str(e)[:160]))
    return out


REGLAS = {"Ventas": reglas_ventas, "Mercado": reglas_mercado, "INEGI": reglas_inegi}


def revisar(hoy: date | None = None) -> list[Revision]:
    """Frescura + reglas de contenido. Una regla que truena se reporta como falla, no rompe el resto."""
    hoy = hoy or date.today()
    out = revisar_frescura(hoy)
    for nombre, fn in REGLAS.items():
        try:
            out += fn(hoy)
        except Exception as e:
            out.append(Revision("Sistema", nombre, f"Revisión de {nombre.lower()}", "falla", str(e)[:200]))
    orden = {e: i for i, e in enumerate(ESTADOS)}
    return sorted(out, key=lambda r: (orden[r.estado], r.grupo, r.fuente))


def a_dataframe(revisiones: list[Revision]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in revisiones],
                        columns=["grupo", "fuente", "regla", "estado", "detalle", "fecha", "tipo", "prioridad"])


@st.cache_data(ttl=600, show_spinner="Revisando calidad de datos...")
def estado_datos() -> pd.DataFrame:
    return a_dataframe(revisar())
