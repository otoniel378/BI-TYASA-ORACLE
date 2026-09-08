"""
loaders.py — Carga de variables de mercado desde Oracle ADW.
"""

import pandas as pd
import streamlit as st
from core.db_connector import run_query, run_query_params, table_ref

T_VARIABLES   = table_ref("gold_variables_mercado")
T_QUIEBRES    = table_ref("gold_quiebres_detectados")
T_NOTICIAS    = table_ref("gold_noticias_vinculadas")
T_SENTIMIENTO = table_ref("gold_sentimiento_noticias")
T_EVENTOS     = table_ref("gold_eventos_historicos")


def _lc(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres de columnas a minúsculas para compatibilidad con las páginas."""
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=3600, show_spinner="Cargando variables de mercado...")
def load_variables_mercado(dias: int = 400) -> pd.DataFrame:
    sql = f"""
        SELECT FECHA, TICKER, NOMBRE, CATEGORIA, VALOR
        FROM {T_VARIABLES}
        WHERE FECHA >= SYSDATE - {dias}
        ORDER BY NOMBRE, FECHA
    """
    df = _lc(run_query(sql))
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner="Cargando quiebres detectados...")
def load_quiebres_activos() -> pd.DataFrame:
    sql = f"""
        SELECT *
        FROM {T_QUIEBRES}
        WHERE ACTIVO = 1
        ORDER BY ABS(CAMBIO_PCT) DESC
    """
    df = _lc(run_query(sql))
    if not df.empty:
        df["fecha_corte"]  = pd.to_datetime(df["fecha_corte"])
        df["fecha_detect"] = pd.to_datetime(df["fecha_detect"])
        for col in ["f_stat", "p_value", "sigma", "cambio_pct", "media_pre", "media_post"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner="Cargando noticias...")
def load_noticias(quiebre_ids: list | None = None) -> pd.DataFrame:
    if quiebre_ids:
        ids_str = ", ".join(f"'{i}'" for i in quiebre_ids)
        where = f"WHERE QUIEBRE_ID IN ({ids_str})"
    else:
        where = ""
    sql = f"""
        SELECT *
        FROM {T_NOTICIAS}
        {where}
        ORDER BY FECHA_PUB DESC
        FETCH FIRST 200 ROWS ONLY
    """
    df = _lc(run_query(sql))
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
    sql = f"""
        SELECT *
        FROM {T_SENTIMIENTO}
        WHERE FECHA_PUB >= SYSDATE - {dias}
        ORDER BY FECHA_PUB DESC, SCORE DESC
        FETCH FIRST 500 ROWS ONLY
    """
    df = _lc(run_query(sql))
    if not df.empty:
        df["fecha_pub"]      = pd.to_datetime(df["fecha_pub"],      errors="coerce")
        df["fecha_analisis"] = pd.to_datetime(df["fecha_analisis"],  errors="coerce")
        if "score" in df.columns:
            df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def load_sentimiento_historico(dias: int = 90) -> pd.DataFrame:
    sql = f"""
        SELECT
            FECHA_PUB,
            SENTIMIENTO,
            VARIABLE_PRINCIPAL,
            ALCANCE,
            GRUPO_TEMATICO,
            AVG(SCORE)  AS SCORE_AVG,
            COUNT(*)    AS N_NOTICIAS
        FROM {T_SENTIMIENTO}
        WHERE FECHA_PUB >= SYSDATE - {dias}
          AND FECHA_PUB IS NOT NULL
        GROUP BY FECHA_PUB, SENTIMIENTO, VARIABLE_PRINCIPAL, ALCANCE, GRUPO_TEMATICO
        ORDER BY FECHA_PUB DESC
    """
    df = _lc(run_query(sql))
    if not df.empty:
        df["fecha_pub"]  = pd.to_datetime(df["fecha_pub"],  errors="coerce")
        df["score_avg"]  = pd.to_numeric(df["score_avg"],   errors="coerce").fillna(0.0)
        df["n_noticias"] = pd.to_numeric(df["n_noticias"],  errors="coerce").fillna(0)
    return df


def pivot_variables_diario(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(
        index="fecha", columns="nombre", values="valor", aggfunc="mean"
    ).reset_index()


@st.cache_data(ttl=3600, show_spinner=False)
def load_eventos_cerca_de(fecha, dias_tolerancia: int = 15) -> pd.DataFrame:
    """Eventos curados (GOLD_EVENTOS_HISTORICOS, ver scripts/seed_eventos_historicos.py)
    cuyo rango [FECHA_INICIO, FECHA_FIN] cae dentro de <fecha> ± <dias_tolerancia>.
    Eventos puntuales (FECHA_FIN NULL) tratan FECHA_INICIO como ambos extremos."""
    sql = f"""
        SELECT ID, FECHA_INICIO, FECHA_FIN, NOMBRE, DESCRIPCION, VARIABLES_RELACIONADAS, FUENTE
        FROM {T_EVENTOS}
        WHERE FECHA_INICIO - :dias <= :fecha
          AND NVL(FECHA_FIN, FECHA_INICIO) + :dias >= :fecha
        ORDER BY FECHA_INICIO
    """
    fecha_dt = pd.Timestamp(fecha).to_pydatetime()
    df = _lc(run_query_params(sql, {"fecha": fecha_dt, "dias": dias_tolerancia}))
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_eventos_en_rango(fecha_inicio, fecha_fin) -> pd.DataFrame:
    """Eventos curados cuyo rango [FECHA_INICIO, FECHA_FIN] se traslapa con
    [<fecha_inicio>, <fecha_fin>] — para vistas de resumen anual/por rango,
    a diferencia de load_eventos_cerca_de() que busca alrededor de un punto."""
    sql = f"""
        SELECT ID, FECHA_INICIO, FECHA_FIN, NOMBRE, DESCRIPCION, VARIABLES_RELACIONADAS, FUENTE
        FROM {T_EVENTOS}
        WHERE FECHA_INICIO <= :fecha_fin
          AND NVL(FECHA_FIN, FECHA_INICIO) >= :fecha_inicio
        ORDER BY FECHA_INICIO
    """
    params = {
        "fecha_inicio": pd.Timestamp(fecha_inicio).to_pydatetime(),
        "fecha_fin": pd.Timestamp(fecha_fin).to_pydatetime(),
    }
    return _lc(run_query_params(sql, params))
