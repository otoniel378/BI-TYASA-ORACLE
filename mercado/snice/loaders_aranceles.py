"""
mercado/snice/loaders_aranceles.py — Carga de datos de la pestaña "Aranceles"
de Comercio Exterior (pages/mercado/07_comercio_exterior.py): arancel base
por fracción (capa 1, SNICE/TIGIE) y las medidas arancelarias concretas que
el DOF le ha aplicado desde entonces (capa 2, monitor_dof.py), ambas
restringidas al catálogo de fracciones de TYASA.

Tablas fuente:
  GOLD_TIGIE_BASE          — arancel general IGI/IGE por fracción (capítulos
                              72/73), foto de la última edición completa de
                              la TIGIE cargada (scripts/cargar_tigie_base_oracle.py,
                              manual — ver scripts/check_actualizacion_tigie.py).
  GOLD_MEDIDAS_ARANCELARIAS — una fila por fracción+medida detectada en el DOF
                              (cuota compensatoria, Regla 8a, TLC, cambio de
                              arancel general) desde que existe el monitor.
  GOLD_ALERTAS_DOF          — publicaciones del DOF que el monitor marcó como
                              relevantes para TYASA (no siempre atadas a una
                              fracción específica).
"""

import pandas as pd
import streamlit as st

from core.db_connector import run_query, table_ref

T_TIGIE   = table_ref("gold_tigie_base")
T_MEDIDAS = table_ref("gold_medidas_arancelarias")
T_ALERTAS = table_ref("gold_alertas_dof")


def _lc(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=600, show_spinner="Cargando arancel base por fracción...")
def load_tigie_tyasa() -> pd.DataFrame:
    """Arancel base (IGI/IGE) de las fracciones propias de TYASA, con su línea
    (Aceros Planos/Largos/SBQ) y la fecha de la edición TIGIE de la que viene."""
    sql = f"""
        SELECT FRACCION, DESCRIPCION, UNIDAD_MEDIDA, IGI, IGE, LINEA_TYASA, FUENTE_FECHA
        FROM {T_TIGIE}
        WHERE ES_FRACCION_TYASA = 1
        ORDER BY LINEA_TYASA, FRACCION
    """
    return _lc(run_query(sql))


@st.cache_data(ttl=600, show_spinner=False)
def load_fuente_tigie() -> str | None:
    """Fecha (DD/MM/YYYY) de la edición de la TIGIE cargada actualmente."""
    df = _lc(run_query(f"SELECT MAX(FUENTE_FECHA) AS F FROM {T_TIGIE}"))
    valor = df.iloc[0]["f"] if not df.empty else None
    return valor if valor else None


@st.cache_data(ttl=600, show_spinner="Cargando medidas arancelarias del DOF...")
def load_medidas_tyasa() -> pd.DataFrame:
    """Historial de medidas (cuotas compensatorias, Regla 8a, TLC, cambios de
    arancel general) que el DOF le ha aplicado a fracciones propias de TYASA,
    más reciente primero."""
    sql = f"""
        SELECT FRACCION, TIPO_MEDIDA, VALOR, PAIS_ORIGEN, VIGENCIA_DESDE,
               VIGENCIA_HASTA, FECHA_DOF, URL, CODIGO_DOF
        FROM {T_MEDIDAS}
        WHERE ES_FRACCION_TYASA = 1
        ORDER BY TO_DATE(FECHA_DOF, 'DD/MM/YYYY') DESC
    """
    df = _lc(run_query(sql))
    if not df.empty:
        df[["pais_origen", "vigencia_desde", "vigencia_hasta"]] = (
            df[["pais_origen", "vigencia_desde", "vigencia_hasta"]].fillna("")
        )
    return df


@st.cache_data(ttl=600, show_spinner="Cargando alertas del DOF...")
def load_alertas_dof_relevantes(limite: int = 15) -> pd.DataFrame:
    """Publicaciones del DOF marcadas relevantes para TYASA por el monitor,
    más recientes primero (no todas están atadas a una fracción concreta —
    ver load_medidas_tyasa para las que sí)."""
    sql = f"""
        SELECT CODIGO, FECHA_DOF, DEPENDENCIA, IMPACTO, DIRECCION, RESUMEN,
               FRACCIONES_TYASA, URL
        FROM {T_ALERTAS}
        WHERE RELEVANTE = 1
        ORDER BY TO_DATE(FECHA_DOF, 'DD/MM/YYYY') DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    df = _lc(run_query(sql))
    if not df.empty:
        df["fracciones_tyasa"] = df["fracciones_tyasa"].fillna("")
    return df
