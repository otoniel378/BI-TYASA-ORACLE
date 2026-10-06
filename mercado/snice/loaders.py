"""
mercado/snice/loaders.py — Carga de datos de Comercio Exterior Siderúrgico
(avisos automáticos de importación SNICE) desde Oracle ADW, acotados al
catálogo de fracciones de TYASA (ver scripts/fracciones_tyasa.py).

Tablas fuente:
  GOLD_SNICE_RESUMEN_MENSUAL / TOP_FRACCIONES / TOP_PAISES / TOP_EMPRESAS
      — histórico completo, nunca se purga. TOP_FRACCIONES sí distingue
        fracción arancelaria (8 dígitos), por eso es la única que permite
        acotar volumen/avisos/categorías a TYASA con historial completo.
        TOP_EMPRESAS distingue empresa pero NO fracción, así que sirve para
        aislar a una empresa específica (ej. TYASA) con histórico completo,
        pero no para acotarla al catálogo TYASA a la vez — ver
        load_serie_empresa_gold.
  BRONZE_SNICE_SIDERURGICO
      — detalle por aviso, solo conserva los últimos PERIODOS_A_CONSERVAR
        periodos (ver scripts/load_snice_to_oracle.py — hoy 6, pensado para
        cubrir los 123 días de vigencia de un aviso). Es la única fuente con
        empresa Y fracción a la vez, así que el drill-down de empresa
        acotado a una fracción, país, y el detalle de avisos/vigencia solo
        cubren esa ventana.
"""

import pandas as pd
import streamlit as st
from core.db_connector import run_query, run_query_params, table_ref

T_RESUMEN     = table_ref("gold_snice_resumen_mensual")
T_PAISES      = table_ref("gold_snice_top_paises")
T_FRACCIONES  = table_ref("gold_snice_top_fracciones")
T_EMPRESAS    = table_ref("gold_snice_top_empresas")
T_BRONZE      = table_ref("bronze_snice_siderurgico")


def _lc(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower() for c in df.columns]
    return df


def _condicion_fracciones(
    fracciones_exactas: tuple[str, ...], fracciones_prefijo: tuple[str, ...] = (),
) -> str:
    """WHERE fragment que matchea FRACCION_ARANCELARIA contra un catálogo fijo de
    fracciones de 8 dígitos (match exacto) y/o subpartidas de 6 dígitos (match por
    prefijo, cubren TODAS sus fracciones hijas). Los valores vienen siempre de un
    catálogo interno fijo (ej. FRACCIONES_TYASA/FRACCIONES_TYASA_PREFIJO), nunca de
    input de usuario — por eso se concatenan directo al SQL sin bind params."""
    condiciones = []
    if fracciones_exactas:
        exactas = ",".join(f"'{f}'" for f in sorted(set(fracciones_exactas)))
        condiciones.append(f"SUBSTR(FRACCION_ARANCELARIA,1,8) IN ({exactas})")
    for prefijo in sorted(set(fracciones_prefijo)):
        condiciones.append(f"SUBSTR(FRACCION_ARANCELARIA,1,6) = '{prefijo}'")
    return "(" + " OR ".join(condiciones) + ")" if condiciones else "1=0"


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


@st.cache_data(ttl=600, show_spinner=False)
def load_periodos_bronze_disponibles() -> set[str]:
    """Periodos que todavía tienen detalle en BRONZE (ventana de retención —
    ver PERIODOS_A_CONSERVAR en scripts/load_snice_to_oracle.py). Fuera de esta
    ventana solo hay agregados GOLD, sin desglose por país/empresa."""
    df = _lc(run_query(f"SELECT DISTINCT PERIODO FROM {T_BRONZE}"))
    return set(df["periodo"].tolist()) if not df.empty else set()


@st.cache_data(ttl=600, show_spinner="Cargando serie SNICE (todas las empresas)...")
def load_serie_tyasa_gold(
    fracciones_exactas: tuple[str, ...], fracciones_prefijo: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Serie mensual del volumen TOTAL reportado en avisos SNICE (todas las
    empresas juntas) para el catálogo de fracciones dado — histórico completo,
    desde GOLD_SNICE_TOP_FRACCIONES (nunca se purga). Para comparar contra la
    serie nacional de CANACERO en la misma gráfica."""
    cond = _condicion_fracciones(fracciones_exactas, fracciones_prefijo)
    sql = f"""
        SELECT PERIODO, SUM(VOLUMEN_TOTAL) AS VOLUMEN_TOTAL, SUM(AVISOS) AS AVISOS
        FROM {T_FRACCIONES} WHERE {cond}
        GROUP BY PERIODO ORDER BY PERIODO
    """
    return _lc(run_query(sql))


@st.cache_data(ttl=600, show_spinner="Cargando serie SNICE de una empresa...")
def load_serie_empresa_gold(razon_social: str) -> pd.DataFrame:
    """Serie mensual del volumen reportado en avisos SNICE para UNA empresa
    exacta (ej. TYASA — ver RAZON_SOCIAL_TYASA_SNICE en fracciones_tyasa.py),
    desde GOLD_SNICE_TOP_EMPRESAS — histórico completo (no se purga), pero SIN
    poder acotar a un subconjunto de fracciones (esa tabla no distingue
    fracción). En los meses donde sí se pudo comparar contra el detalle de
    BRONZE con el catálogo TYASA aplicado, el total coincidió exacto — TYASA
    no parece importar fuera de su propio catálogo — pero si algún mes no
    coincidiera, esta serie sería la más completa, no la más acotada."""
    sql = f"""
        SELECT PERIODO, VOLUMEN_TOTAL, AVISOS
        FROM {T_EMPRESAS}
        WHERE UPPER(RAZON_SOCIAL) = :razon_social
        ORDER BY PERIODO
    """
    return _lc(run_query_params(sql, {"razon_social": razon_social.upper()}))


@st.cache_data(ttl=600, show_spinner="Cargando serie SNICE de una empresa...")
def load_serie_empresa_bronze(
    razon_social: str, fracciones_exactas: tuple[str, ...], fracciones_prefijo: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Serie mensual del volumen reportado en avisos SNICE para UNA empresa
    exacta, acotado además al catálogo de fracciones dado — solo cubre los
    periodos que siguen en BRONZE (ventana de retención). Más preciso que
    load_serie_empresa_gold pero con mucho menos historial."""
    cond = _condicion_fracciones(fracciones_exactas, fracciones_prefijo)
    sql = f"""
        SELECT PERIODO, SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS
        FROM {T_BRONZE}
        WHERE UPPER(RAZON_SOCIAL) = :razon_social AND {cond}
        GROUP BY PERIODO ORDER BY PERIODO
    """
    return _lc(run_query_params(sql, {"razon_social": razon_social.upper()}))


@st.cache_data(ttl=600, show_spinner=False)
def load_rango_vigencia_disponible(
    fracciones_exactas: tuple[str, ...], fracciones_prefijo: tuple[str, ...] = (),
) -> tuple[str | None, str | None]:
    """Rango de meses (YYYY-MM) cubierto por INICIO_VIGENCIA/FIN_VIGENCIA en
    BRONZE, para poblar el selector de 'intención de importación'. Solo cubre
    lo que siga en BRONZE (ventana de retención)."""
    cond = _condicion_fracciones(fracciones_exactas, fracciones_prefijo)
    sql = f"""
        SELECT TO_CHAR(MIN(INICIO_VIGENCIA), 'YYYY-MM'), TO_CHAR(MAX(FIN_VIGENCIA), 'YYYY-MM')
        FROM {T_BRONZE} WHERE {cond}
    """
    df = _lc(run_query(sql))
    if df.empty:
        return None, None
    row = df.iloc[0]
    return row.iloc[0], row.iloc[1]


@st.cache_data(ttl=600, show_spinner="Cargando intención de importación...")
def load_resumen_vigentes_en_mes(
    mes: str, fracciones_exactas: tuple[str, ...], fracciones_prefijo: tuple[str, ...] = (),
) -> dict:
    """KPIs de avisos cuya VIGENCIA (no el periodo de reporte) cubre <mes>
    ('YYYY-MM') — es decir, avisos autorizados que en teoría siguen habilitando
    la importación durante ese mes, sin importar cuándo se hayan tramitado."""
    cond = _condicion_fracciones(fracciones_exactas, fracciones_prefijo)
    sql = f"""
        SELECT SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS,
               COUNT(DISTINCT RAZON_SOCIAL) AS EMPRESAS_DISTINTAS,
               COUNT(DISTINCT PAIS_ORIGEN) AS PAISES_DISTINTOS,
               COUNT(DISTINCT SUBSTR(FRACCION_ARANCELARIA,1,8)) AS FRACCIONES_DISTINTAS
        FROM {T_BRONZE}
        WHERE {cond}
          AND INICIO_VIGENCIA <= LAST_DAY(TO_DATE(:mes, 'YYYY-MM'))
          AND FIN_VIGENCIA >= TRUNC(TO_DATE(:mes, 'YYYY-MM'), 'MM')
    """
    df = _lc(run_query_params(sql, {"mes": mes}))
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=600, show_spinner="Cargando fracciones con vigencia en el mes...")
def load_fracciones_vigentes_en_mes(
    mes: str, fracciones_exactas: tuple[str, ...], fracciones_prefijo: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Igual que load_resumen_vigentes_en_mes, pero desglosado por fracción —
    para ver QUÉ va a estar llegando ese mes, no solo el total."""
    cond = _condicion_fracciones(fracciones_exactas, fracciones_prefijo)
    sql = f"""
        SELECT SUBSTR(FRACCION_ARANCELARIA,1,8) AS FRACCION_ARANCELARIA,
               SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS
        FROM {T_BRONZE}
        WHERE {cond}
          AND INICIO_VIGENCIA <= LAST_DAY(TO_DATE(:mes, 'YYYY-MM'))
          AND FIN_VIGENCIA >= TRUNC(TO_DATE(:mes, 'YYYY-MM'), 'MM')
        GROUP BY SUBSTR(FRACCION_ARANCELARIA,1,8)
        ORDER BY VOLUMEN_TOTAL DESC
    """
    return _lc(run_query_params(sql, {"mes": mes}))


@st.cache_data(ttl=600, show_spinner="Cargando avisos con vigencia en el mes...")
def load_avisos_vigentes_en_mes(
    mes: str,
    fracciones_exactas: tuple[str, ...],
    fracciones_prefijo: tuple[str, ...] = (),
    partida: str | None = None,
    pais: str | None = None,
    busqueda: str | None = None,
    limite: int = 500,
) -> pd.DataFrame:
    """Detalle por aviso (folio, empresa, fracción, país, vigencia) cuya
    vigencia cubre <mes> — para inspeccionar exactamente qué embarques se
    esperan ese mes según sus permisos, sin importar cuándo se tramitaron."""
    condiciones = [
        _condicion_fracciones(fracciones_exactas, fracciones_prefijo),
        "INICIO_VIGENCIA <= LAST_DAY(TO_DATE(:mes, 'YYYY-MM'))",
        "FIN_VIGENCIA >= TRUNC(TO_DATE(:mes, 'YYYY-MM'), 'MM')",
    ]
    params: dict = {"mes": mes}
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
        SELECT FOLIO_TRAMITE, RAZON_SOCIAL, SUBSTR(FRACCION_ARANCELARIA,1,8) AS FRACCION_ARANCELARIA,
               CATEGORIA_PRODUCTO, PAIS_ORIGEN, VOLUMEN_AVISO, FECHA_TRAMITE,
               INICIO_VIGENCIA, FIN_VIGENCIA
        FROM {T_BRONZE}
        WHERE {where}
        ORDER BY INICIO_VIGENCIA
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, params))


@st.cache_data(ttl=600, show_spinner=False)
def load_resumen_tyasa_bronze(
    periodo: str,
    fracciones_exactas: tuple[str, ...],
    fracciones_prefijo: tuple[str, ...] = (),
    partida: str | None = None,
    pais: str | None = None,
    busqueda: str | None = None,
) -> dict:
    """Empresas y países distintos filtrados al catálogo TYASA (y, opcionalmente,
    a partida/país/búsqueda encima) — solo disponible para periodos todavía en
    BRONZE (ver load_periodos_bronze_disponibles). Usa COUNT(DISTINCT ...) sin
    LIMIT, a diferencia de los rankings, para que el KPI no se recorte si hay
    más de 200 empresas o países."""
    condiciones = ["PERIODO = :periodo", _condicion_fracciones(fracciones_exactas, fracciones_prefijo)]
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
        SELECT COUNT(DISTINCT RAZON_SOCIAL) AS EMPRESAS_DISTINTAS,
               COUNT(DISTINCT PAIS_ORIGEN) AS PAISES_DISTINTOS
        FROM {T_BRONZE} WHERE {where}
    """
    df = _lc(run_query_params(sql, params))
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=600, show_spinner="Cargando fracciones TYASA...")
def load_top_fracciones_tyasa_gold(
    periodo: str, fracciones_exactas: tuple[str, ...], fracciones_prefijo: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Volumen/avisos por fracción (8 dígitos), filtrado al catálogo TYASA, desde
    GOLD_SNICE_TOP_FRACCIONES — historial completo. Se agrupa por partida del lado
    de Python (con tigie_partidas.categoria_de) para armar el ranking de categorías
    sin depender de BRONZE ni de su ventana de retención."""
    cond = _condicion_fracciones(fracciones_exactas, fracciones_prefijo)
    sql = f"""
        SELECT FRACCION_ARANCELARIA, VOLUMEN_TOTAL, AVISOS
        FROM {T_FRACCIONES} WHERE PERIODO = :periodo AND {cond}
    """
    return _lc(run_query_params(sql, {"periodo": periodo}))


@st.cache_data(ttl=600, show_spinner="Filtrando fracciones TYASA...")
def load_top_fracciones_tyasa_bronze(
    periodo: str,
    fracciones_exactas: tuple[str, ...],
    fracciones_prefijo: tuple[str, ...] = (),
    pais: str | None = None,
    busqueda: str | None = None,
) -> pd.DataFrame:
    """Igual que load_top_fracciones_tyasa_gold (mismas columnas), pero desde
    BRONZE — para cuando hay un filtro de país o empresa activo (esa dimensión
    no existe en GOLD_SNICE_TOP_FRACCIONES). Solo disponible para periodos que
    siguen en BRONZE."""
    condiciones = ["PERIODO = :periodo", _condicion_fracciones(fracciones_exactas, fracciones_prefijo)]
    params: dict = {"periodo": periodo}
    if pais:
        condiciones.append("PAIS_ORIGEN = :pais")
        params["pais"] = pais
    if busqueda:
        condiciones.append("UPPER(RAZON_SOCIAL) LIKE :busqueda")
        params["busqueda"] = f"%{busqueda.upper()}%"
    where = " AND ".join(condiciones)
    sql = f"""
        SELECT SUBSTR(FRACCION_ARANCELARIA,1,8) AS FRACCION_ARANCELARIA,
               SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS
        FROM {T_BRONZE}
        WHERE {where}
        GROUP BY SUBSTR(FRACCION_ARANCELARIA,1,8)
    """
    return _lc(run_query_params(sql, params))


@st.cache_data(ttl=600, show_spinner="Cargando países TYASA...")
def load_paises_fracciones(
    periodo: str,
    fracciones_exactas: tuple[str, ...],
    fracciones_prefijo: tuple[str, ...] = (),
    partida: str | None = None,
    busqueda: str | None = None,
    limite: int = 60,
) -> pd.DataFrame:
    """País de origen para el catálogo de fracciones de TYASA (o el subconjunto
    filtrado por partida/búsqueda). Solo disponible para periodos en BRONZE."""
    if not fracciones_exactas and not fracciones_prefijo:
        return pd.DataFrame()
    condiciones = ["PERIODO = :periodo", _condicion_fracciones(fracciones_exactas, fracciones_prefijo)]
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


@st.cache_data(ttl=600, show_spinner="Filtrando empresas por fracciones TYASA...")
def load_empresas_fracciones(
    periodo: str,
    fracciones_exactas: tuple[str, ...],
    fracciones_prefijo: tuple[str, ...] = (),
    partida: str | None = None,
    pais: str | None = None,
    busqueda: str | None = None,
    limite: int = 200,
) -> pd.DataFrame:
    """
    Como load_empresas_filtradas(), pero filtra por una LISTA de fracciones
    (ej. el catálogo de TYASA) en vez de una sola partida de 4 dígitos, con
    filtros opcionales adicionales de partida/país/búsqueda encima.
    <fracciones_exactas>: códigos completos de 8 dígitos, match exacto contra
    los primeros 8 dígitos de FRACCION_ARANCELARIA (que puede venir a 8 o 10).
    <fracciones_prefijo>: códigos de 6 dígitos (subpartida), match por prefijo.
    Los valores vienen de un catálogo interno fijo, no de input de usuario.
    """
    if not fracciones_exactas and not fracciones_prefijo:
        return pd.DataFrame()

    condiciones = ["PERIODO = :periodo", _condicion_fracciones(fracciones_exactas, fracciones_prefijo)]
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
               COUNT(DISTINCT SUBSTR(FRACCION_ARANCELARIA,1,8)) AS FRACCIONES_DISTINTAS,
               COUNT(DISTINCT PAIS_ORIGEN) AS PAISES_DISTINTOS
        FROM {T_BRONZE}
        WHERE {where} AND RAZON_SOCIAL IS NOT NULL
        GROUP BY RAZON_SOCIAL
        ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, params))


@st.cache_data(ttl=600, show_spinner="Cargando empresas para esta fracción...")
def load_empresas_fraccion_exacta(periodo: str, fraccion: str, limite: int = 50) -> pd.DataFrame:
    """Empresas SNICE para UNA fracción exacta (8 dígitos) — para el drill-down
    lado a lado con el volumen nacional CANACERO de esa misma fracción."""
    sql = f"""
        SELECT RAZON_SOCIAL, SUM(VOLUMEN_AVISO) AS VOLUMEN_TOTAL, COUNT(*) AS AVISOS,
               COUNT(DISTINCT PAIS_ORIGEN) AS PAISES_DISTINTOS
        FROM {T_BRONZE}
        WHERE PERIODO = :periodo AND SUBSTR(FRACCION_ARANCELARIA,1,8) = :fraccion AND RAZON_SOCIAL IS NOT NULL
        GROUP BY RAZON_SOCIAL
        ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, {"periodo": periodo, "fraccion": fraccion[:8]}))


@st.cache_data(ttl=600, show_spinner="Cargando avisos de esta fracción...")
def load_avisos_fraccion_exacta(periodo: str, fraccion: str, limite: int = 100) -> pd.DataFrame:
    """Detalle por aviso (una fila por trámite, no agregado) para UNA fracción
    exacta — incluye país e inicio/fin de vigencia, para 'Consulta por fracción
    específica'. Solo cubre los periodos que aún viven en BRONZE (~2 meses)."""
    sql = f"""
        SELECT RAZON_SOCIAL, PAIS_ORIGEN, VOLUMEN_AVISO, FECHA_TRAMITE,
               INICIO_VIGENCIA, FIN_VIGENCIA
        FROM {T_BRONZE}
        WHERE PERIODO = :periodo AND SUBSTR(FRACCION_ARANCELARIA,1,8) = :fraccion
        ORDER BY FECHA_TRAMITE DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, {"periodo": periodo, "fraccion": fraccion[:8]}))


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
def load_paises_disponibles(periodo: str) -> list[str]:
    sql = f"SELECT PAIS_ORIGEN FROM {T_PAISES} WHERE PERIODO = :1 ORDER BY PAIS_ORIGEN"
    df = _lc(run_query_params(sql, [periodo]))
    return df["pais_origen"].tolist() if not df.empty else []


@st.cache_data(ttl=600, show_spinner="Cargando detalle de avisos...")
def load_avisos_detalle(
    periodo: str,
    fracciones_exactas: tuple[str, ...] = (),
    fracciones_prefijo: tuple[str, ...] = (),
    partida: str | None = None,
    pais: str | None = None,
    busqueda_empresa: str | None = None,
    pagina: int = 1,
    tam_pagina: int = 25,
) -> tuple[pd.DataFrame, int]:
    """Detalle de avisos paginado (solo disponible para periodos en BRONZE).
    Si se pasan fracciones_exactas/fracciones_prefijo, restringe al catálogo
    correspondiente (ej. TYASA) además de los demás filtros."""
    condiciones = ["PERIODO = :periodo"]
    params: dict = {"periodo": periodo}

    if fracciones_exactas or fracciones_prefijo:
        condiciones.append(_condicion_fracciones(fracciones_exactas, fracciones_prefijo))
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
    fracciones_exactas: tuple[str, ...] = (),
    fracciones_prefijo: tuple[str, ...] = (),
    partida: str | None = None,
    pais: str | None = None,
    busqueda_empresa: str | None = None,
    limite: int = 20_000,
) -> pd.DataFrame:
    """Detalle filtrado completo (sin paginar) para el botón de exportar Excel."""
    df, _ = load_avisos_detalle(
        periodo, fracciones_exactas=fracciones_exactas, fracciones_prefijo=fracciones_prefijo,
        partida=partida, pais=pais, busqueda_empresa=busqueda_empresa,
        pagina=1, tam_pagina=limite,
    )
    return df
