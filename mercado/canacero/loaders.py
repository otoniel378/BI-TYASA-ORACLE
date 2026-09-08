"""
mercado/canacero/loaders.py — Carga y consulta de comercio exterior nacional
(CANACERO SICEP, "Base de datos tradicional") desde Oracle ADW.

Tabla fuente: BRONZE_CANACERO_COMEX — 1 fila por (periodo_mes, movimiento,
fracción). Sin retención ni tablas GOLD (a diferencia de SNICE): el volumen
es chico (~5,000 filas por archivo anual subido), se agrega en vivo.

El filtrado a "fracciones de TYASA" usa scripts/fracciones_tyasa.py (lista
fija interna, no input de usuario — segura para interpolar en SQL).
"""

import os
import sys

_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import pandas as pd
import streamlit as st
from core.db_connector import run_query, run_query_params, run_write, run_executemany, table_ref
from fracciones_tyasa import FRACCIONES_TYASA, FRACCIONES_TYASA_PREFIJO
from mercado.canacero.parser import parse_csv_canacero

T_BRONZE = table_ref("bronze_canacero_comex")


def _lc(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower() for c in df.columns]
    return df


def _where_fracciones_tyasa(columna: str = "FRACCION_ARANCELARIA", fracciones: tuple[str, ...] | None = None) -> str:
    """Fragmento SQL que matchea FRACCION_ARANCELARIA.
    <fracciones>=None: catálogo completo de TYASA (exacto a 8 dígitos + prefijos
    de subpartida). <fracciones>=subconjunto: match exacto solo contra esos
    códigos (para cuando el usuario filtra a un subconjunto en la UI). En
    ambos casos los valores vienen de un catálogo interno fijo o de un
    multiselect restringido a ese catálogo, no de texto libre — seguro para
    interpolar en SQL."""
    if fracciones is not None:
        if not fracciones:
            return "1=0"
        exactas = ",".join(f"'{f}'" for f in sorted(set(fracciones)))
        return f"SUBSTR({columna},1,8) IN ({exactas})"
    exactas = ",".join(f"'{f}'" for f in sorted(FRACCIONES_TYASA))
    prefijos = " OR ".join(
        f"SUBSTR({columna},1,6) = '{p}'" for p in sorted(FRACCIONES_TYASA_PREFIJO)
    )
    return f"(SUBSTR({columna},1,8) IN ({exactas}) OR {prefijos})"


# ---------------------------------------------------------------------------
# Carga (escritura)
# ---------------------------------------------------------------------------

def cargar_csv_canacero(archivo, movimiento: str, nombre_archivo: str) -> dict:
    """
    Parsea <archivo> (lo que entrega st.file_uploader) y lo guarda en
    BRONZE_CANACERO_COMEX. Reemplaza por (año, movimiento): si ya había datos
    de ese año y movimiento, los borra antes de insertar (idempotente — subir
    el mismo archivo dos veces no duplica filas).
    """
    df = parse_csv_canacero(archivo, movimiento, nombre_archivo)
    if df.empty:
        return {"filas_insertadas": 0, "periodos": [], "anios": [], "movimiento": movimiento.strip().upper()}

    movimiento_norm = movimiento.strip().upper()
    anios = sorted(int(a) for a in df["anio"].unique().tolist())

    for anio in anios:
        run_write(f"DELETE FROM {T_BRONZE} WHERE ANIO = :1 AND MOVIMIENTO = :2", [anio, movimiento_norm])

    insert_sql = f"""
        INSERT INTO {T_BRONZE} (
            ANIO, MES, PERIODO_MES, MOVIMIENTO, FRACCION_ARANCELARIA,
            DESCRIPCION, CATEGORIA, VOLUMEN_TON, VALOR_USD, ARCHIVO_ORIGEN
        ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10)
    """
    columnas = [
        "anio", "mes", "periodo_mes", "movimiento", "fraccion_arancelaria",
        "descripcion", "categoria", "volumen_ton", "valor_usd", "archivo_origen",
    ]
    rows = [tuple(r) for r in df[columnas].itertuples(index=False, name=None)]
    n_insertadas = run_executemany(insert_sql, rows)

    for fn in (
        load_periodos_canacero, load_resumen_tyasa, load_serie_tiempo_tyasa,
        load_top_fracciones_tyasa,
    ):
        fn.clear()

    return {
        "filas_insertadas": n_insertadas,
        "periodos": sorted(df["periodo_mes"].unique().tolist()),
        "anios": anios,
        "movimiento": movimiento_norm,
    }


# ---------------------------------------------------------------------------
# Consulta (lectura)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def load_periodos_canacero(movimiento: str | None = None) -> list[str]:
    if movimiento:
        sql = f"SELECT DISTINCT PERIODO_MES FROM {T_BRONZE} WHERE MOVIMIENTO = :1 ORDER BY PERIODO_MES DESC"
        df = _lc(run_query_params(sql, [movimiento.strip().upper()]))
    else:
        df = _lc(run_query(f"SELECT DISTINCT PERIODO_MES FROM {T_BRONZE} ORDER BY PERIODO_MES DESC"))
    return df["periodo_mes"].tolist() if not df.empty else []


@st.cache_data(ttl=600, show_spinner="Cargando total nacional CANACERO...")
def load_resumen_tyasa(periodo_mes: str, movimiento: str, fracciones: tuple[str, ...] | None = None) -> dict:
    """Total nacional (CANACERO) para las fracciones de TYASA en un periodo.
    <fracciones>=None usa el catálogo completo; si se pasa un subconjunto
    (desde el filtro de la UI), solo suma esas fracciones exactas."""
    sql = f"""
        SELECT SUM(VOLUMEN_TON) AS VOLUMEN_TOTAL, SUM(VALOR_USD) AS VALOR_TOTAL,
               COUNT(DISTINCT SUBSTR(FRACCION_ARANCELARIA,1,8)) AS FRACCIONES_DISTINTAS
        FROM {T_BRONZE}
        WHERE PERIODO_MES = :1 AND MOVIMIENTO = :2 AND {_where_fracciones_tyasa(fracciones=fracciones)}
    """
    df = _lc(run_query_params(sql, [periodo_mes, movimiento.strip().upper()]))
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=600, show_spinner="Cargando serie de tiempo CANACERO...")
def load_serie_tiempo_tyasa(movimiento: str, fracciones: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Serie mensual nacional (fracciones TYASA sumadas, o el subconjunto filtrado), para tendencia."""
    sql = f"""
        SELECT PERIODO_MES, SUM(VOLUMEN_TON) AS VOLUMEN_TOTAL, SUM(VALOR_USD) AS VALOR_TOTAL
        FROM {T_BRONZE}
        WHERE MOVIMIENTO = :1 AND {_where_fracciones_tyasa(fracciones=fracciones)}
        GROUP BY PERIODO_MES
        ORDER BY PERIODO_MES
    """
    return _lc(run_query_params(sql, [movimiento.strip().upper()]))


@st.cache_data(ttl=600, show_spinner="Cargando series por fracción...")
def load_series_fracciones_tyasa(movimiento: str) -> pd.DataFrame:
    """PERIODO_MES, FRACCION (8 dígitos), VOLUMEN_TOTAL — una fila por
    fracción TYASA y mes, para pronóstico por dimensión
    (generar_forecast_multiple(df, col_dim="FRACCION", ...))."""
    sql = f"""
        SELECT PERIODO_MES, SUBSTR(FRACCION_ARANCELARIA,1,8) AS FRACCION,
               SUM(VOLUMEN_TON) AS VOLUMEN_TOTAL
        FROM {T_BRONZE}
        WHERE MOVIMIENTO = :1 AND {_where_fracciones_tyasa()}
        GROUP BY PERIODO_MES, SUBSTR(FRACCION_ARANCELARIA,1,8)
        ORDER BY PERIODO_MES
    """
    return _lc(run_query_params(sql, [movimiento.strip().upper()]))


@st.cache_data(ttl=600, show_spinner="Cargando fracciones CANACERO...")
def load_top_fracciones_tyasa(
    periodo_mes: str, movimiento: str, limite: int = 30, fracciones: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Ranking de fracciones de TYASA (o el subconjunto filtrado) por volumen nacional en un periodo."""
    sql = f"""
        SELECT SUBSTR(FRACCION_ARANCELARIA,1,8) AS FRACCION, MIN(DESCRIPCION) AS DESCRIPCION,
               SUM(VOLUMEN_TON) AS VOLUMEN_TOTAL, SUM(VALOR_USD) AS VALOR_TOTAL
        FROM {T_BRONZE}
        WHERE PERIODO_MES = :1 AND MOVIMIENTO = :2 AND {_where_fracciones_tyasa(fracciones=fracciones)}
        GROUP BY SUBSTR(FRACCION_ARANCELARIA,1,8)
        ORDER BY VOLUMEN_TOTAL DESC
        FETCH FIRST {int(limite)} ROWS ONLY
    """
    return _lc(run_query_params(sql, [periodo_mes, movimiento.strip().upper()]))


@st.cache_data(ttl=600, show_spinner="Cargando serie de la fracción...")
def load_serie_fraccion(fraccion: str, movimiento: str) -> pd.DataFrame:
    """Serie mensual nacional para UNA fracción específica (8 dígitos)."""
    sql = f"""
        SELECT PERIODO_MES, SUM(VOLUMEN_TON) AS VOLUMEN_TOTAL, SUM(VALOR_USD) AS VALOR_TOTAL
        FROM {T_BRONZE}
        WHERE MOVIMIENTO = :1 AND SUBSTR(FRACCION_ARANCELARIA,1,8) = :2
        GROUP BY PERIODO_MES
        ORDER BY PERIODO_MES
    """
    return _lc(run_query_params(sql, [movimiento.strip().upper(), fraccion[:8]]))


@st.cache_data(ttl=600, show_spinner=False)
def load_descripciones_tyasa() -> dict:
    """DESCRIPCION conocida por fracción (catálogo interno de CANACERO), para
    etiquetar el selector de fracciones. Nota: algunas fracciones de 8 dígitos
    traen más de una DESCRIPCION distinta según el NICO (10° dígito) — aquí se
    queda con una sola (MAX) solo para la etiqueta, no afecta las sumas."""
    sql = f"""
        SELECT SUBSTR(FRACCION_ARANCELARIA,1,8) AS FRACCION, MAX(DESCRIPCION) AS DESCRIPCION
        FROM {T_BRONZE}
        WHERE {_where_fracciones_tyasa()} AND DESCRIPCION IS NOT NULL
        GROUP BY SUBSTR(FRACCION_ARANCELARIA,1,8)
    """
    df = _lc(run_query(sql))
    return dict(zip(df["fraccion"], df["descripcion"])) if not df.empty else {}
