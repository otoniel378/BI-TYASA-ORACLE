"""
loaders.py — Funciones de carga desde Oracle ADW para Aceros Planos Negros.
Usa cache de Streamlit para evitar re-consultas innecesarias.
"""

import pandas as pd
import streamlit as st
import logging

from core.db_connector import run_query, run_query_params, table_ref
from core.validators import validate_all

# Referencias de tablas
T_BRONZE   = table_ref("bronze_ventas_raw")
T_SILVER   = table_ref("silver_ventas_limpias")
T_CLIENTE  = table_ref("gold_demanda_cliente")
T_PRODUCTO = table_ref("gold_demanda_producto")
T_MENSUAL  = table_ref("gold_demanda_mensual")
T_CLI_PROD = table_ref("gold_cliente_producto")
T_PROCESO  = table_ref("gold_demanda_proceso")

AREA_FILTER = "NEGROS"


# ---------------------------------------------------------------------------
# Gold tables
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Cargando demanda por cliente...")
def load_gold_demanda_cliente() -> pd.DataFrame:
    sql = f"""
        SELECT CLIENTE, AREA, DIVISION,
               PESO_TON, N_EMBARQUES,
               PRIMERA_COMPRA, ULTIMA_COMPRA
        FROM {T_CLIENTE}
        WHERE AREA = '{AREA_FILTER}'
    """
    df = run_query(sql)
    if not df.empty:
        df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=600, show_spinner="Cargando demanda por producto...")
def load_gold_demanda_producto() -> pd.DataFrame:
    sql = f"""
        SELECT PRODUCTO_LIMPIO, AREA, DIVISION,
               PESO_TON, N_CLIENTES
        FROM {T_PRODUCTO}
        WHERE AREA = '{AREA_FILTER}'
    """
    df = run_query(sql)
    if not df.empty:
        df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=600, show_spinner="Cargando serie mensual total...")
def load_gold_demanda_mensual_total() -> pd.DataFrame:
    sql = f"""
        SELECT PERIODO, ANIO, MES,
               SUM(PESO_TON)    AS PESO_TON,
               SUM(N_CLIENTES)  AS N_CLIENTES,
               SUM(N_EMBARQUES) AS N_EMBARQUES
        FROM {T_MENSUAL}
        WHERE AREA = '{AREA_FILTER}'
        GROUP BY PERIODO, ANIO, MES
        ORDER BY PERIODO
    """
    df = run_query(sql)
    if df.empty:
        return df
    df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    df["PERIODO"]  = pd.to_datetime(df["PERIODO"], errors="coerce")
    df["ANIO"]     = df["ANIO"].astype(int)
    df["MES"]      = df["MES"].astype(int)
    return df


@st.cache_data(ttl=600, show_spinner="Cargando serie mensual...")
def load_gold_demanda_mensual() -> pd.DataFrame:
    sql = f"""
        SELECT PERIODO, ANIO, MES,
               PRODUCTO_LIMPIO,
               AREA, DIVISION,
               SUM(PESO_TON) AS PESO_TON
        FROM {T_SILVER}
        WHERE AREA = '{AREA_FILTER}'
        GROUP BY PERIODO, ANIO, MES, PRODUCTO_LIMPIO, AREA, DIVISION
        ORDER BY PERIODO
    """
    df = run_query(sql)
    if df.empty:
        return df
    df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    df["PERIODO"]  = pd.to_datetime(df["PERIODO"], errors="coerce")
    return df


@st.cache_data(ttl=600, show_spinner="Cargando matriz cliente-producto...")
def load_gold_cliente_producto() -> pd.DataFrame:
    sql = f"""
        SELECT CLIENTE, PRODUCTO_LIMPIO, AREA, DIVISION,
               PESO_TON, N_EMBARQUES
        FROM {T_CLI_PROD}
        WHERE AREA = '{AREA_FILTER}'
    """
    df = run_query(sql)
    if not df.empty:
        df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=600, show_spinner="Cargando demanda por proceso...")
def load_gold_demanda_proceso() -> pd.DataFrame:
    sql = f"""
        SELECT PROCESO, AREA, DIVISION,
               PESO_TON, N_CLIENTES, N_EMBARQUES
        FROM {T_PROCESO}
        WHERE AREA = '{AREA_FILTER}'
    """
    df = run_query(sql)
    if not df.empty:
        df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    return df


# ---------------------------------------------------------------------------
# Silver table
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Cargando ventas limpias...")
def load_ventas_limpias() -> pd.DataFrame:
    sql = f"""
        SELECT FECHAEMB, CLIENTE, PRODUCTO_ORIGINAL, PRODUCTO_LIMPIO,
               PROCESO, CALIBRE, ANCHO,
               PESO_KG, PESO_TON,
               ANIO, MES, PERIODO,
               AREA, DIVISION
        FROM {T_SILVER}
        WHERE AREA = '{AREA_FILTER}'
    """
    df = run_query(sql)
    if df.empty:
        return df
    df["FECHAEMB"] = pd.to_datetime(df["FECHAEMB"], errors="coerce")
    df["PERIODO"]  = pd.to_datetime(df["PERIODO"],  errors="coerce")
    for col in ["PESO_KG", "PESO_TON", "CALIBRE", "ANCHO"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Series temporales auxiliares
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Cargando serie mensual por proceso...")
def load_serie_mensual_proceso() -> pd.DataFrame:
    sql = f"""
        SELECT PERIODO, PROCESO,
               SUM(PESO_TON) AS PESO_TON
        FROM {T_SILVER}
        WHERE AREA = '{AREA_FILTER}'
        GROUP BY PERIODO, PROCESO
        ORDER BY PERIODO, PROCESO
    """
    df = run_query(sql)
    if df.empty:
        return df
    df["PERIODO"]  = pd.to_datetime(df["PERIODO"], errors="coerce")
    df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=600, show_spinner="Cargando serie mensual por cliente...")
def load_serie_mensual_cliente() -> pd.DataFrame:
    sql = f"""
        SELECT PERIODO, CLIENTE,
               SUM(PESO_TON) AS PESO_TON
        FROM {T_SILVER}
        WHERE AREA = '{AREA_FILTER}'
        GROUP BY PERIODO, CLIENTE
        ORDER BY PERIODO, CLIENTE
    """
    df = run_query(sql)
    if df.empty:
        return df
    df["PERIODO"]  = pd.to_datetime(df["PERIODO"], errors="coerce")
    df["PESO_TON"] = pd.to_numeric(df["PESO_TON"], errors="coerce").fillna(0)
    return df


# ---------------------------------------------------------------------------
# Catalogos para filtros
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def get_catalogo_clientes() -> list[str]:
    df = load_gold_demanda_cliente()
    if df.empty or "CLIENTE" not in df.columns:
        return []
    return sorted(df["CLIENTE"].dropna().unique().tolist())


@st.cache_data(ttl=600, show_spinner=False)
def get_catalogo_productos() -> list[str]:
    df = load_gold_demanda_producto()
    if df.empty or "PRODUCTO_LIMPIO" not in df.columns:
        return []
    return sorted(df["PRODUCTO_LIMPIO"].dropna().unique().tolist())


@st.cache_data(ttl=600, show_spinner=False)
def get_catalogo_procesos() -> list[str]:
    df = load_gold_demanda_proceso()
    if df.empty or "PROCESO" not in df.columns:
        return []
    return sorted(df["PROCESO"].dropna().unique().tolist())


@st.cache_data(ttl=600, show_spinner=False)
def get_rango_fechas() -> tuple:
    df = load_gold_demanda_mensual_total()
    if df.empty or "PERIODO" not in df.columns:
        return (None, None)
    return df["PERIODO"].min(), df["PERIODO"].max()


@st.cache_data(ttl=600, show_spinner=False)
def get_catalogo_anios() -> list[int]:
    df = load_ventas_limpias()
    if df.empty or "ANIO" not in df.columns:
        return []
    return sorted(df["ANIO"].dropna().unique().astype(int).tolist(), reverse=True)


@st.cache_data(ttl=600, show_spinner=False)
def load_transacciones_cliente(cliente: str) -> pd.DataFrame:
    """Todas las transacciones históricas de un cliente — base para Inteligencia de Clientes."""
    sql = f"""
        SELECT FECHAEMB, PRODUCTO_ORIGINAL, PROCESO,
               PESO_TON, ANIO, MES, PERIODO
        FROM {T_SILVER}
        WHERE AREA = :area AND CLIENTE = :cliente
        ORDER BY FECHAEMB
    """
    df = run_query_params(sql, {"area": AREA_FILTER, "cliente": cliente})
    if df.empty:
        return df
    df["FECHAEMB"] = pd.to_datetime(df["FECHAEMB"], errors="coerce")
    df["PERIODO"]  = pd.to_datetime(df["PERIODO"],  errors="coerce")
    df["PESO_TON"] = pd.to_numeric(df["PESO_TON"],  errors="coerce").fillna(0)
    df["ANIO"]     = pd.to_numeric(df["ANIO"],       errors="coerce").fillna(0).astype(int)
    df["MES"]      = pd.to_numeric(df["MES"],        errors="coerce").fillna(0).astype(int)
    return df


# ---------------------------------------------------------------------------
# Fecha de corte de los datos y validaciones automáticas
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def get_fecha_corte() -> pd.Timestamp | None:
    """Última fecha de embarque cargada. Es la fecha de referencia para medir
    recencia (días sin comprar, clientes nuevos) y para detectar si el último mes
    de la serie está incompleto. Si los datos están al día, coincide con hoy."""
    df = run_query(f"SELECT MAX(FECHAEMB) AS F FROM {T_SILVER} WHERE AREA = '{AREA_FILTER}'")
    if df.empty or pd.isna(df.iloc[0, 0]):
        return None
    return pd.Timestamp(df.iloc[0, 0]).normalize()


_log = logging.getLogger("tyasa.validacion")


@st.cache_data(ttl=600, show_spinner=False)
def validar_datos() -> dict[str, dict]:
    """Ejecuta core.validators sobre las tablas del área y devuelve, por tabla,
    sus errores y avisos. Los avisos también se registran en el log."""
    resultados = validate_all({
        "ventas_limpias":        load_ventas_limpias(),
        "gold_demanda_cliente":  load_gold_demanda_cliente(),
        "gold_demanda_producto": load_gold_demanda_producto(),
        "gold_demanda_mensual":  load_gold_demanda_mensual_total(),
        "gold_cliente_producto": load_gold_cliente_producto(),
    })
    salida = {}
    for tabla, r in resultados.items():
        for msg in r.errors + r.warnings:
            _log.warning("%s: %s", tabla, msg)
        salida[tabla] = {"errores": list(r.errors), "avisos": list(r.warnings)}
    return salida
