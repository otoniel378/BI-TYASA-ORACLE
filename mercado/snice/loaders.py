"""
mercado/snice/loaders.py — Carga de datos de Comercio Exterior Siderúrgico
(avisos automáticos de importación SNICE) desde Oracle ADW.

Tablas fuente:
  GOLD_SNICE_RESUMEN_MENSUAL / TOP_CATEGORIAS / TOP_PAISES / TOP_EMPRESAS
      — histórico completo, nunca se purga.
  BRONZE_SNICE_SIDERURGICO
      — detalle por aviso, solo conserva los últimos 2 periodos (ver
        scripts/load_snice_to_oracle.py). Por eso el drill-down de empresa y
        el detalle de avisos solo cubren los periodos más recientes.
"""

import pandas as pd
import streamlit as st
from core.db_connector import run_query, run_query_params, table_ref

T_RESUMEN     = table_ref("gold_snice_resumen_mensual")
T_CATEGORIAS  = table_ref("gold_snice_top_categorias")
T_PAISES      = table_ref("gold_snice_top_paises")
T_EMPRESAS    = table_ref("gold_snice_top_empresas")
T_BRONZE      = table_ref("bronze_snice_siderurgico")


def _lc(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=600, show_spinner=False)
def load_periodos_disponibles() -> list[str]:
    df = _lc(run_query(f"SELECT PERIODO FROM {T_RESUMEN} ORDER BY PERIODO DESC"))
    return df["periodo"].tolist() if not df.empty else []


@st.cache_data(ttl=600, show_spinner="Cargando resumen de comercio exterior...")
def load_resumen(periodo: str) -> dict:
    sql = f"""
        SELECT PERIODO, VOLUMEN_TOTAL, AVISOS_TOTAL, EMPRESAS_DISTINTAS,
               PAISES_DISTINTOS, FRACCIONES_DISTINTAS
        FROM {T_RESUMEN} WHERE PERIODO = :1
    """
    df = _lc(run_query_params(sql, [periodo]))
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=600, show_spinner="Cargando categorías...")
def load_top_categorias(periodo: str) -> pd.DataFrame:
    sql = f"""
        SELECT PARTIDA, CATEGORIA_PRODUCTO, SUBCATEGORIA, VOLUMEN_TOTAL, AVISOS, EMPRESAS_DISTINTAS
        FROM {T_CATEGORIAS} WHERE PERIODO = :1 ORDER BY VOLUMEN_TOTAL DESC
    """
    return _lc(run_query_params(sql, [periodo]))


@st.cache_data(ttl=600, show_spinner="Cargando países...")
def load_top_paises(periodo: str) -> pd.DataFrame:
    sql = f"""
        SELECT PAIS_ORIGEN, VOLUMEN_TOTAL, AVISOS, EMPRESAS_DISTINTAS
        FROM {T_PAISES} WHERE PERIODO = :1 ORDER BY VOLUMEN_TOTAL DESC
    """
    return _lc(run_query_params(sql, [periodo]))


@st.cache_data(ttl=600, show_spinner="Cargando empresas...")
def load_top_empresas(periodo: str, limite: int = 200) -> pd.DataFrame:
    """Ranking general (sin filtro de categoría/país) desde GOLD, rápido."""
    sql = f"""
        SELECT RAZON_SOCIAL, VOLUMEN_TOTAL, AVISOS, FRACCIONES_DISTINTAS, PAISES_DISTINTOS
        FROM {T_EMPRESAS} WHERE PERIODO = :1
        ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, [periodo]))


@st.cache_data(ttl=600, show_spinner="Filtrando empresas...")
def load_empresas_filtradas(
    periodo: str,
    partida: str | None = None,
    pais: str | None = None,
    busqueda: str | None = None,
    limite: int = 200,
) -> pd.DataFrame:
    """
    Ranking de empresas desde BRONZE (detalle), permite filtrar por
    categoría (partida) y/o país de origen y/o búsqueda de razón social.
    Solo disponible para los periodos que aún viven en BRONZE (retención 2 meses).
    """
    condiciones = ["PERIODO = :periodo"]
    params: dict = {"periodo": periodo}

    if partida:
        condiciones.append("SUBSTR(FRACCION_ARANCELARIA, 1, 4) = :partida")
        params["partida"] = partida
    if pais:
        condiciones.append("PAIS_ORIGEN = :pais")
        params["pais"] = pais
    if busqueda:
        condiciones.append("UPPER(RAZON_SOCIAL) LIKE :busqueda")
        params["busqueda"] = f"%{busqueda.upper()}%"

    where = " AND ".join(condiciones)
    sql = f"""
        SELECT RAZON_SOCIAL, SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS,
               COUNT(DISTINCT SUBSTR(FRACCION_ARANCELARIA,1,4)) AS CATEGORIAS_DISTINTAS,
               COUNT(DISTINCT PAIS_ORIGEN) AS PAISES_DISTINTOS
        FROM {T_BRONZE}
        WHERE {where} AND RAZON_SOCIAL IS NOT NULL
        GROUP BY RAZON_SOCIAL
        ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, params))


@st.cache_data(ttl=600, show_spinner="Filtrando categorías...")
def load_categorias_filtradas(
    periodo: str, pais: str | None = None, busqueda: str | None = None, limite: int = 60
) -> pd.DataFrame:
    """Igual que load_top_categorias pero desde BRONZE, para cuando hay un
    filtro de país o empresa activo (GOLD_SNICE_TOP_CATEGORIAS no tiene esas
    dimensiones). Solo cubre los periodos que aún viven en BRONZE."""
    condiciones = ["PERIODO = :periodo"]
    params: dict = {"periodo": periodo}
    if pais:
        condiciones.append("PAIS_ORIGEN = :pais")
        params["pais"] = pais
    if busqueda:
        condiciones.append("UPPER(RAZON_SOCIAL) LIKE :busqueda")
        params["busqueda"] = f"%{busqueda.upper()}%"
    where = " AND ".join(condiciones)
    sql = f"""
        SELECT SUBSTR(FRACCION_ARANCELARIA,1,4) AS PARTIDA,
               MIN(CATEGORIA_PRODUCTO) AS CATEGORIA_PRODUCTO, MIN(SUBCATEGORIA) AS SUBCATEGORIA,
               SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS,
               COUNT(DISTINCT RAZON_SOCIAL) AS EMPRESAS_DISTINTAS
        FROM {T_BRONZE}
        WHERE {where} AND FRACCION_ARANCELARIA IS NOT NULL
        GROUP BY SUBSTR(FRACCION_ARANCELARIA,1,4)
        ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, params))


@st.cache_data(ttl=600, show_spinner="Filtrando países...")
def load_paises_filtrados(
    periodo: str, partida: str | None = None, busqueda: str | None = None, limite: int = 60
) -> pd.DataFrame:
    """Igual que load_top_paises pero desde BRONZE, para cuando hay un filtro
    de categoría o empresa activo."""
    condiciones = ["PERIODO = :periodo"]
    params: dict = {"periodo": periodo}
    if partida:
        condiciones.append("SUBSTR(FRACCION_ARANCELARIA, 1, 4) = :partida")
        params["partida"] = partida
    if busqueda:
        condiciones.append("UPPER(RAZON_SOCIAL) LIKE :busqueda")
        params["busqueda"] = f"%{busqueda.upper()}%"
    where = " AND ".join(condiciones)
    sql = f"""
        SELECT PAIS_ORIGEN, SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS,
               COUNT(DISTINCT RAZON_SOCIAL) AS EMPRESAS_DISTINTAS
        FROM {T_BRONZE}
        WHERE {where} AND PAIS_ORIGEN IS NOT NULL
        GROUP BY PAIS_ORIGEN
        ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, params))


@st.cache_data(ttl=600, show_spinner="Cargando ficha de empresa...")
def load_empresa_detalle(razon_social: str, periodo: str) -> dict:
    """Resumen + desglose por categoría/país + avisos recientes de una empresa."""
    resumen_sql = f"""
        SELECT SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS,
               COUNT(DISTINCT SUBSTR(FRACCION_ARANCELARIA,1,4)) AS CATEGORIAS,
               COUNT(DISTINCT PAIS_ORIGEN) AS PAISES
        FROM {T_BRONZE} WHERE PERIODO = :1 AND RAZON_SOCIAL = :2
    """
    resumen = _lc(run_query_params(resumen_sql, [periodo, razon_social]))

    categorias_sql = f"""
        SELECT CATEGORIA_PRODUCTO, SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS
        FROM {T_BRONZE} WHERE PERIODO = :1 AND RAZON_SOCIAL = :2
        GROUP BY CATEGORIA_PRODUCTO ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST 8 ROWS ONLY
    """
    categorias = _lc(run_query_params(categorias_sql, [periodo, razon_social]))

    paises_sql = f"""
        SELECT PAIS_ORIGEN, SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS
        FROM {T_BRONZE} WHERE PERIODO = :1 AND RAZON_SOCIAL = :2
        GROUP BY PAIS_ORIGEN ORDER BY VOLUMEN_TOTAL DESC
    """
    paises = _lc(run_query_params(paises_sql, [periodo, razon_social]))

    avisos_sql = f"""
        SELECT FOLIO_TRAMITE, FECHA_TRAMITE, VOLUMEN_AVISO, FRACCION_ARANCELARIA,
               CATEGORIA_PRODUCTO, PAIS_ORIGEN, INICIO_VIGENCIA, FIN_VIGENCIA
        FROM {T_BRONZE} WHERE PERIODO = :1 AND RAZON_SOCIAL = :2
        ORDER BY FECHA_TRAMITE DESC
        FETCH FIRST 15 ROWS ONLY
    """
    avisos = _lc(run_query_params(avisos_sql, [periodo, razon_social]))

    return {
        "resumen": resumen.iloc[0].to_dict() if not resumen.empty else {},
        "categorias": categorias,
        "paises": paises,
        "avisos_recientes": avisos,
    }


@st.cache_data(ttl=600, show_spinner=False)
def load_categorias_disponibles(periodo: str) -> pd.DataFrame:
    sql = f"""
        SELECT PARTIDA, CATEGORIA_PRODUCTO
        FROM {T_CATEGORIAS} WHERE PERIODO = :1
        ORDER BY CATEGORIA_PRODUCTO
    """
    return _lc(run_query_params(sql, [periodo]))


@st.cache_data(ttl=600, show_spinner=False)
def load_paises_disponibles(periodo: str) -> list[str]:
    sql = f"SELECT PAIS_ORIGEN FROM {T_PAISES} WHERE PERIODO = :1 ORDER BY PAIS_ORIGEN"
    df = _lc(run_query_params(sql, [periodo]))
    return df["pais_origen"].tolist() if not df.empty else []


@st.cache_data(ttl=600, show_spinner="Cargando detalle de avisos...")
def load_avisos_detalle(
    periodo: str,
    partida: str | None = None,
    pais: str | None = None,
    busqueda_empresa: str | None = None,
    pagina: int = 1,
    tam_pagina: int = 25,
) -> tuple[pd.DataFrame, int]:
    """Detalle de avisos paginado (solo disponible para periodos en BRONZE)."""
    condiciones = ["PERIODO = :periodo"]
    params: dict = {"periodo": periodo}

    if partida:
        condiciones.append("SUBSTR(FRACCION_ARANCELARIA, 1, 4) = :partida")
        params["partida"] = partida
    if pais:
        condiciones.append("PAIS_ORIGEN = :pais")
        params["pais"] = pais
    if busqueda_empresa:
        condiciones.append("UPPER(RAZON_SOCIAL) LIKE :busqueda")
        params["busqueda"] = f"%{busqueda_empresa.upper()}%"

    where = " AND ".join(condiciones)

    total = _lc(run_query_params(
        f"SELECT COUNT(*) AS N FROM {T_BRONZE} WHERE {where}", params
    ))
    total_registros = int(total.iloc[0]["n"]) if not total.empty else 0

    offset = max(0, (pagina - 1) * tam_pagina)
    detalle_sql = f"""
        SELECT FOLIO_TRAMITE, RAZON_SOCIAL, FRACCION_ARANCELARIA, CATEGORIA_PRODUCTO,
               PAIS_ORIGEN, VOLUMEN_AVISO, FECHA_TRAMITE
        FROM {T_BRONZE}
        WHERE {where}
        ORDER BY FECHA_TRAMITE DESC
        OFFSET {offset} ROWS FETCH NEXT {tam_pagina} ROWS ONLY
    """
    df = _lc(run_query_params(detalle_sql, params))
    return df, total_registros


@st.cache_data(ttl=600, show_spinner="Preparando exportación...")
def load_avisos_para_exportar(
    periodo: str,
    partida: str | None = None,
    pais: str | None = None,
    busqueda_empresa: str | None = None,
    limite: int = 20_000,
) -> pd.DataFrame:
    """Detalle filtrado completo (sin paginar) para el botón de exportar Excel."""
    df, _ = load_avisos_detalle(
        periodo, partida=partida, pais=pais, busqueda_empresa=busqueda_empresa,
        pagina=1, tam_pagina=limite,
    )
    return df
