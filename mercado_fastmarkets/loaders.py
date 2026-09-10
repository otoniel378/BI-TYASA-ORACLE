"""
mercado_fastmarkets/loaders.py — Funciones de carga de BRONZE_FASTMARKETS_PRECIOS
para alimentar el pronóstico de comercio exterior (variable exógena) y el
panel de benchmark visual (pages/mercado/08_pronostico_comercio.py).

Mapeo símbolo↔familia curado a mano contra las 63 series cargadas y las
familias de producto de CANACERO (mercado/canacero/loaders.py::load_descripciones_tyasa).
Ajustable a futuro si algún benchmark no resulta representativo.
"""

import pandas as pd
import streamlit as st
from core.db_connector import run_query_params, table_ref

T_PRECIOS = table_ref("bronze_fastmarkets_precios")

# Insumos que aplican a CUALQUIER familia (costo de materia prima de horno
# eléctrico — el proceso productivo de TYASA).
SIMBOLOS_INSUMOS_GLOBALES = {
    "MB-STE-0230": "Scrap_Bundles_Chicago",
    "MB-FEM-0003": "FerroManganeso",
    "MB-SIM-0003": "SilicoManganeso",
}

# Benchmark de precio específico por familia (nombre exacto tal como lo
# devuelve load_descripciones_tyasa()).
SIMBOLOS_POR_FAMILIA = {
    "LINGOTES, PALANQUILLAS, ETC.": {"MB-STE-0117": "Billete_Export_Turquia"},
    "PLANCHON":                     {"MB-STE-0117": "Billete_Export_Turquia"},
    "LAMINA EN CALIENTE":           {"MB-STE-0184": "HRC_FobMillUS"},
    "PLACA EN HOJA":                {"MB-STE-0172": "Placa_FobMillUS"},
    "PLACA EN ROLLO":               {"MB-STE-0172": "Placa_FobMillUS"},
    "LAMINA EN FRIO":               {"MB-STE-0185": "CRC_FobMillUS"},
    "LAMINA GALVANIZADA":           {"MB-STE-0104": "HDG_Import_SurAmerica", "XL-ZS-FRC.O": "LME_Zinc_Cash"},
    "PLANOS CON OTROS RECUBIERTOS Y TRABAJOS": {"MB-STE-0104": "HDG_Import_SurAmerica"},
    "ALAMBRON AL CARBONO":          {"MB-STE-0192": "Alambron_FobMillUS"},
    "ALAMBRON ALEADO":              {"MB-STE-0192": "Alambron_FobMillUS"},
    "BARRAS":                       {"MB-STE-0170": "Varilla_FobMillUS"},
    "VARILLA CORRUGADA":            {"MB-STE-0170": "Varilla_FobMillUS"},
    "PERFILES ESTRUCTURALES FORMADOS EN FRIO": {"MB-STE-0209": "Viga_FobMillUS"},
    "ALAMBRE":              {"MB-STE-0192": "Alambron_FobMillUS"},  # proxy insumo, sin serie propia
    "DERIVADOS DE ALAMBRE": {"MB-STE-0192": "Alambron_FobMillUS"},
}

NOMBRES_FASTMARKETS = {v for m in SIMBOLOS_POR_FAMILIA.values() for v in m.values()} | set(
    SIMBOLOS_INSUMOS_GLOBALES.values()
)


def _mapa_familia(familia: str | None) -> dict:
    mapa = dict(SIMBOLOS_INSUMOS_GLOBALES)
    mapa.update(SIMBOLOS_POR_FAMILIA.get(familia, {}))
    return mapa


@st.cache_data(ttl=3600, show_spinner="Cargando precios Fastmarkets...")
def load_precios_wide(symbols: tuple, medida: str = "Mid") -> pd.DataFrame:
    """fecha + una columna por símbolo (VALOR de <medida>), mensualizada
    (último valor disponible por mes calendario, mismo patrón que
    _construir_contexto_visual en la página). Junta filas HISTORICO y
    FORECAST sin distinguir — para el modelo, ambas son "lo que Fastmarkets
    dice del precio a esa fecha", pasada o futura."""
    if not symbols:
        return pd.DataFrame()
    placeholders = ",".join(f":s{i}" for i in range(len(symbols)))
    sql = f"""
        SELECT SYMBOL, FECHA, VALOR
        FROM {T_PRECIOS}
        WHERE MEDIDA = :medida AND SYMBOL IN ({placeholders})
        ORDER BY FECHA
    """
    params = {"medida": medida, **{f"s{i}": s for i, s in enumerate(symbols)}}
    df = run_query_params(sql, params)
    if df.empty:
        return df
    df.columns = [c.lower() for c in df.columns]
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.to_period("M").dt.to_timestamp()
    return (
        df.sort_values("fecha").groupby(["fecha", "symbol"])["valor"].last()
        .unstack("symbol").reset_index()
    )


def load_precios_familia(familia: str | None) -> pd.DataFrame:
    """Insumos globales + benchmark de <familia> (si se reconoce), columnas
    ya renombradas a su alias legible. familia=None -> solo insumos
    globales (pestaña 'Total', que abarca todas las familias a la vez)."""
    mapa = _mapa_familia(familia)
    ancho = load_precios_wide(tuple(sorted(mapa.keys())))
    if ancho.empty:
        return ancho
    return ancho.rename(columns=mapa)


@st.cache_data(ttl=3600, show_spinner=False)
def load_detalle_simbolos(symbols: tuple, medida: str = "Mid") -> pd.DataFrame:
    """fecha, symbol, descripcion, valor, tipo — crudo (con TIPO), para el
    panel de benchmark (último histórico vs. último pronóstico Fastmarkets
    por símbolo)."""
    if not symbols:
        return pd.DataFrame()
    placeholders = ",".join(f":s{i}" for i in range(len(symbols)))
    sql = f"""
        SELECT SYMBOL, DESCRIPCION, FECHA, VALOR, TIPO
        FROM {T_PRECIOS}
        WHERE MEDIDA = :medida AND SYMBOL IN ({placeholders})
        ORDER BY FECHA
    """
    params = {"medida": medida, **{f"s{i}": s for i, s in enumerate(symbols)}}
    df = run_query_params(sql, params)
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def load_resumen_benchmark(familia: str | None, horizonte_meses: int) -> pd.DataFrame:
    """Por símbolo relevante a <familia>: descripción, último valor
    histórico (fecha, valor) y valor pronosticado por Fastmarkets al final
    del horizonte pedido (fecha, valor) si ese símbolo trae FORECAST —
    columnas de pronóstico en None si no. Precio ($/ton) y volumen
    (toneladas) no son comparables directamente: esto es benchmark de
    tendencia, no de magnitud."""
    mapa = _mapa_familia(familia)
    detalle = load_detalle_simbolos(tuple(sorted(mapa.keys())))
    if detalle.empty:
        return pd.DataFrame()

    hoy = pd.Timestamp.now().normalize()
    limite = hoy + pd.DateOffset(months=horizonte_meses)
    filas = []
    for symbol, grp in detalle.groupby("symbol"):
        nombre = mapa.get(symbol, symbol)
        descripcion = grp["descripcion"].dropna().iloc[0] if grp["descripcion"].notna().any() else symbol
        hist = grp[grp["tipo"] == "HISTORICO"].sort_values("fecha")
        fc = grp[(grp["tipo"] == "FORECAST") & (grp["fecha"] <= limite)].sort_values("fecha")

        if hist.empty:
            continue
        ult_hist = hist.iloc[-1]
        fila = {
            "Serie": nombre, "Descripción": descripcion,
            "Último histórico": ult_hist["fecha"].strftime("%b %Y"),
            "Valor histórico": round(float(ult_hist["valor"]), 1),
        }
        if not fc.empty:
            ult_fc = fc.iloc[-1]
            fila["Pronóstico Fastmarkets"] = ult_fc["fecha"].strftime("%b %Y")
            fila["Valor pronosticado"] = round(float(ult_fc["valor"]), 1)
            if ult_hist["valor"]:
                fila["Variación %"] = round(
                    (float(ult_fc["valor"]) - float(ult_hist["valor"])) / abs(float(ult_hist["valor"])) * 100, 1
                )
        filas.append(fila)

    return pd.DataFrame(filas)
