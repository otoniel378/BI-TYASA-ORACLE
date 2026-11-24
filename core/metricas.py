"""
metricas.py — Catálogo único de métricas de ventas de TYASA BI.

Cada métrica se define una sola vez (nombre, qué significa, unidad y fórmula)
y la usan las páginas y el asistente IA (herramienta consultar_metrica), para
que la misma cifra salga igual en todas partes.

Reglas del catálogo:
- Fuente: SILVER_VENTAS_LIMPIAS (una fila por bobina o paquete embarcado).
- "Hoy" es la fecha de corte (última FECHAEMB cargada), no la fecha del sistema.
- Las comparaciones entre periodos usan solo meses completos (un mes a medio
  cargar contra uno completo siempre "cae").
- Estado del cliente por días sin compra a la fecha de corte: Activo ≤ 90,
  En riesgo ≤ 180, Inactivo > 180. La alerta temprana de fuga es a los 60 días.
"""

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from core.db_connector import run_query_params, table_ref

T_VENTAS = table_ref("SILVER_VENTAS_LIMPIAS")

DIAS_CLIENTE_ACTIVO = 90
DIAS_CLIENTE_EN_RIESGO = 180
DIAS_ALERTA_SIN_COMPRA = 60


@dataclass(frozen=True)
class Metrica:
    id: str
    nombre: str
    descripcion: str
    unidad: str
    sql: str  # agregación sobre SILVER_VENTAS_LIMPIAS


METRICAS = {m.id: m for m in [
    Metrica("toneladas", "Toneladas vendidas", "Peso total embarcado en el periodo.", "t", "SUM(PESO_TON)"),
    Metrica("clientes_con_compra", "Clientes con compra", "Clientes distintos que compraron en el periodo.",
            "clientes", "COUNT(DISTINCT CLIENTE)"),
    Metrica("productos_vendidos", "Productos vendidos", "Productos distintos vendidos en el periodo.",
            "productos", "COUNT(DISTINCT PRODUCTO_LIMPIO)"),
    Metrica("piezas_embarcadas", "Piezas embarcadas", "Bobinas o paquetes embarcados (registros de venta).",
            "piezas", "COUNT(*)"),
    Metrica("ton_por_cliente", "Toneladas por cliente", "Toneladas vendidas ÷ clientes con compra.",
            "t/cliente", "SUM(PESO_TON) / NULLIF(COUNT(DISTINCT CLIENTE), 0)"),
]}

# Dimensiones permitidas para desglosar o filtrar (lista fija: nunca texto del usuario en el SQL)
DIMENSIONES = {
    "cliente":  "CLIENTE",
    "producto": "PRODUCTO_LIMPIO",
    "proceso":  "PROCESO",
    "mes":      "TRUNC(FECHAEMB, 'MM')",
    "anio":     "EXTRACT(YEAR FROM FECHAEMB)",
}
_DIM_TEMPORAL = {"mes", "anio"}


@st.cache_data(ttl=600, show_spinner=False)
def _consulta(sql: str, params: tuple) -> pd.DataFrame:
    return run_query_params(sql, dict(params))


def fecha_corte(area: str = "NEGROS") -> pd.Timestamp:
    """Última fecha de embarque cargada: el "hoy" de las métricas."""
    df = _consulta(f"SELECT MAX(FECHAEMB) AS CORTE FROM {T_VENTAS} WHERE AREA = :area", (("area", area),))
    return pd.Timestamp(df["CORTE"].iloc[0]).normalize()


def ultimo_mes_completo(corte: pd.Timestamp) -> pd.Timestamp:
    """Primer día del último mes con datos completos a la fecha de corte."""
    corte = pd.Timestamp(corte).normalize()
    mes = corte.to_period("M").to_timestamp()
    return mes if corte == corte + pd.offsets.MonthEnd(0) else mes - pd.DateOffset(months=1)


def calcular(metrica: str, desde=None, hasta=None, por: str | None = None, area: str = "NEGROS",
             filtros: dict | None = None, top: int | None = None) -> pd.DataFrame:
    """Valor de <metrica> entre <desde> y <hasta> (fechas de embarque, ambas
    incluidas), opcionalmente desglosado <por> una dimensión de DIMENSIONES y
    filtrado con <filtros> {dimensión: valor}. Columnas: [<por> en mayúsculas], VALOR."""
    m = METRICAS[metrica]
    where, params = ["AREA = :area"], {"area": area}
    if desde is not None:
        where.append("FECHAEMB >= :desde")
        params["desde"] = pd.Timestamp(desde).to_pydatetime()
    if hasta is not None:
        where.append("FECHAEMB < :hasta")
        params["hasta"] = (pd.Timestamp(hasta).normalize() + pd.Timedelta(days=1)).to_pydatetime()
    for i, (dim, valor) in enumerate((filtros or {}).items()):
        where.append(f"{DIMENSIONES[dim]} = :f{i}")
        params[f"f{i}"] = valor
    if por:
        col = DIMENSIONES[por]
        orden = "1" if por in _DIM_TEMPORAL else "VALOR DESC NULLS LAST"
        sql = (f"SELECT {col} AS {por.upper()}, {m.sql} AS VALOR FROM {T_VENTAS} "
               f"WHERE {' AND '.join(where)} GROUP BY {col} ORDER BY {orden}")
        if top:
            sql += f" FETCH FIRST {int(top)} ROWS ONLY"
    else:
        sql = f"SELECT {m.sql} AS VALOR FROM {T_VENTAS} WHERE {' AND '.join(where)}"
    df = _consulta(sql, tuple(sorted(params.items())))
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce").fillna(0.0)
    if por == "mes":
        df["MES"] = pd.to_datetime(df["MES"])
    return df


def valor(metrica: str, desde=None, hasta=None, area: str = "NEGROS", filtros: dict | None = None) -> float:
    return float(calcular(metrica, desde, hasta, area=area, filtros=filtros)["VALOR"].iloc[0])


def variacion(metrica: str, contra: str = "mes_anterior", mes=None, area: str = "NEGROS") -> dict:
    """Compara <metrica> de un mes completo (default: el último) contra el mes
    anterior o el mismo mes del año anterior. Regresa mes, actual, base y pct."""
    mes = pd.Timestamp(mes) if mes is not None else ultimo_mes_completo(fecha_corte(area))
    base_mes = mes - pd.DateOffset(months=1 if contra == "mes_anterior" else 12)
    fin = lambda inicio: inicio + pd.offsets.MonthEnd(0)  # noqa: E731
    actual = valor(metrica, mes, fin(mes), area)
    base = valor(metrica, base_mes, fin(base_mes), area)
    return {"mes": mes, "mes_base": base_mes, "actual": actual, "base": base,
            "pct": (actual - base) / base * 100 if base else None}


def estado_cliente(dias_sin_compra: float) -> str:
    if pd.isna(dias_sin_compra):
        return "Sin datos"
    if dias_sin_compra <= DIAS_CLIENTE_ACTIVO:
        return "Activo"
    return "En riesgo" if dias_sin_compra <= DIAS_CLIENTE_EN_RIESGO else "Inactivo"


def clientes_activos(area: str = "NEGROS", dias: int = DIAS_CLIENTE_ACTIVO) -> int:
    """Clientes con compra en los últimos <dias> a la fecha de corte."""
    corte = fecha_corte(area)
    return int(valor("clientes_con_compra", corte - pd.Timedelta(days=dias - 1), corte, area))


def ultima_compra_por_cliente(area: str = "NEGROS", meses_volumen: int = 12) -> pd.DataFrame:
    """Por cliente: última compra, días sin compra y estado a la fecha de corte,
    y toneladas de los últimos <meses_volumen> meses (para priorizar)."""
    corte = fecha_corte(area)
    desde = (corte - pd.DateOffset(months=meses_volumen)).to_pydatetime()
    df = _consulta(f"""
        SELECT CLIENTE, MAX(FECHAEMB) AS ULTIMA_COMPRA,
               SUM(CASE WHEN FECHAEMB > :desde THEN PESO_TON ELSE 0 END) AS TON_RECIENTE
        FROM {T_VENTAS} WHERE AREA = :area GROUP BY CLIENTE
    """, (("area", area), ("desde", desde)))
    df["ULTIMA_COMPRA"] = pd.to_datetime(df["ULTIMA_COMPRA"])
    df["TON_RECIENTE"] = pd.to_numeric(df["TON_RECIENTE"], errors="coerce").fillna(0.0)
    df["DIAS_SIN_COMPRA"] = (corte - df["ULTIMA_COMPRA"].dt.normalize()).dt.days
    df["ESTADO"] = df["DIAS_SIN_COMPRA"].map(estado_cliente)
    return df.sort_values("TON_RECIENTE", ascending=False).reset_index(drop=True)


def glosario() -> pd.DataFrame:
    """Definiciones para mostrar en la app y dar al asistente IA."""
    filas = [{"Métrica": m.nombre, "Clave": m.id, "Qué significa": m.descripcion, "Unidad": m.unidad}
             for m in METRICAS.values()]
    filas.append({"Métrica": "Clientes activos", "Clave": "clientes_activos",
                  "Qué significa": f"Clientes con compra en los últimos {DIAS_CLIENTE_ACTIVO} días a la fecha de corte.",
                  "Unidad": "clientes"})
    filas.append({"Métrica": "Estado del cliente", "Clave": "estado_cliente",
                  "Qué significa": f"Activo ≤ {DIAS_CLIENTE_ACTIVO} días sin compra · En riesgo ≤ "
                                   f"{DIAS_CLIENTE_EN_RIESGO} · Inactivo > {DIAS_CLIENTE_EN_RIESGO}. "
                                   f"Alerta de fuga a los {DIAS_ALERTA_SIN_COMPRA} días.",
                  "Unidad": "—"})
    return pd.DataFrame(filas)
