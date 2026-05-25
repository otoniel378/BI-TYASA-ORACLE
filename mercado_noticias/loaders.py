"""
loaders.py — Carga de variables de mercado desde BigQuery.
Módulo: mercado_noticias
"""

import pandas as pd
import streamlit as st
from core.db_connector import run_query, table_ref

T_VARIABLES  = table_ref("gold_variables_mercado")
T_QUIEBRES   = table_ref("gold_quiebres_detectados")
T_NOTICIAS   = table_ref("gold_noticias_vinculadas")
T_SENTIMIENTO = table_ref("gold_sentimiento_noticias")


@st.cache_data(ttl=3600, show_spinner="Cargando variables de mercado...")
def load_variables_mercado(dias: int = 400) -> pd.DataFrame:
    sql = f"""
        SELECT fecha, ticker, nombre, categoria, valor
        FROM {T_VARIABLES}
        WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL {dias} DAY)
        ORDER BY nombre, fecha
    """
    df = run_query(sql)
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner="Cargando quiebres detectados...")
def load_quiebres_activos() -> pd.DataFrame:
    sql = f"""
        SELECT *
        FROM {T_QUIEBRES}
        WHERE activo = TRUE
        ORDER BY ABS(cambio_pct) DESC
    """
    df = run_query(sql)
    if not df.empty:
        df["fecha_corte"]  = pd.to_datetime(df["fecha_corte"])
        df["fecha_detect"] = pd.to_datetime(df["fecha_detect"])
        for col in ["F_stat", "p_value", "sigma", "cambio_pct", "media_pre", "media_post"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner="Cargando noticias...")
def load_noticias(quiebre_ids: list | None = None) -> pd.DataFrame:
    if quiebre_ids:
        ids_str = ", ".join(f"'{i}'" for i in quiebre_ids)
        where = f"WHERE quiebre_id IN ({ids_str})"
    else:
        where = ""
    sql = f"""
        SELECT *
        FROM {T_NOTICIAS}
        {where}
        ORDER BY fecha_pub DESC
        LIMIT 200
    """
    df = run_query(sql)
    if not df.empty:
        df["fecha_pub"]   = pd.to_datetime(df["fecha_pub"],   errors="coerce")
        df["fecha_carga"] = pd.to_datetime(df["fecha_carga"], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def get_categorias_disponibles() -> list[str]:
    df = load_quiebres_activos()
    if df.empty or "categoria" not in df.columns:
        return []
    return sorted(df["categoria"].dropna().unique().tolist())


@st.cache_data(ttl=1800, show_spinner="Cargando sentimiento de noticias...")
def load_sentimiento_noticias(dias: int = 30) -> pd.DataFrame:
    """Noticias clasificadas con sentimiento — últimos N días."""
    sql = f"""
        SELECT *
        FROM {T_SENTIMIENTO}
        WHERE fecha_pub >= DATE_SUB(CURRENT_DATE(), INTERVAL {dias} DAY)
        ORDER BY fecha_pub DESC, score DESC
        LIMIT 500
    """
    df = run_query(sql)
    if not df.empty:
        df["fecha_pub"]      = pd.to_datetime(df["fecha_pub"],      errors="coerce")
        df["fecha_analisis"] = pd.to_datetime(df["fecha_analisis"],  errors="coerce")
        if "score" in df.columns:
            df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def load_sentimiento_historico(dias: int = 90) -> pd.DataFrame:
    """Serie histórica de sentimiento agregado por día para tendencia."""
    sql = f"""
        SELECT
            fecha_pub,
            sentimiento,
            variable_principal,
            alcance,
            grupo_tematico,
            AVG(score)  AS score_avg,
            COUNT(*)    AS n_noticias
        FROM {T_SENTIMIENTO}
        WHERE fecha_pub >= DATE_SUB(CURRENT_DATE(), INTERVAL {dias} DAY)
          AND fecha_pub IS NOT NULL
        GROUP BY fecha_pub, sentimiento, variable_principal, alcance, grupo_tematico
        ORDER BY fecha_pub DESC
    """
    df = run_query(sql)
    if not df.empty:
        df["fecha_pub"]  = pd.to_datetime(df["fecha_pub"],  errors="coerce")
        df["score_avg"]  = pd.to_numeric(df["score_avg"],   errors="coerce").fillna(0.0)
        df["n_noticias"] = pd.to_numeric(df["n_noticias"],  errors="coerce").fillna(0)
    return df


def pivot_variables_diario(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte la tabla long a wide: filas=fechas, columnas=variables."""
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(
        index="fecha", columns="nombre", values="valor", aggfunc="mean"
    ).reset_index()
