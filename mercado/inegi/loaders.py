"""
loaders.py — Funciones de carga para indicadores INEGI desde Oracle ADW.
"""

import pandas as pd
import streamlit as st
from core.db_connector import run_query, table_ref

T_INDICADORES = table_ref("gold_indicadores_inegi")


def _lc(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas a minúsculas para compatibilidad con las páginas."""
    df.columns = [c.lower() for c in df.columns]
    return df

# ── Catálogo de indicadores ──────────────────────────────────────────────────
INDICADORES_CONFIG = {
    # ── ACTIVIDAD INDUSTRIAL (IMAI) ───────────────────────────────────────────
    "736407": "IMAI_ActividadIndustrial_Indice",
    "736418": "IMAI_Manufactureras_Indice",
    "736414": "IMAI_Construccion_Indice",
    "736475": "IMAI_MetalicasBasicas_331_Indice",
    "736476": "IMAI_HierroAcero_3311_Indice",
    "736481": "IMAI_ProductosMetalicos_332_Indice",
    "736491": "IMAI_MaquinariaEquipo_333_Indice",
    "736526": "IMAI_ActividadIndustrial_VarAnual",
    "736533": "IMAI_Construccion_VarAnual",
    "736594": "IMAI_MetalicasBasicas_331_VarAnual",
    # ── EMIM ─────────────────────────────────────────────────────────────────
    "910468": "EMIM_VolFisico_Desest_Indice",
    "910470": "EMIM_VolFisico_Desest_VarAnual",
    # ── ENEC ─────────────────────────────────────────────────────────────────
    "720332": "ENEC_ValorProd_ObraTotal",
    "720334": "ENEC_ValorProd_Edificacion",
    "720340": "ENEC_ValorProd_Transporte_Urb",
    # ── EMEC ─────────────────────────────────────────────────────────────────
    "718504": "EMEC_Ingresos_ComercioMayor_43",
    "718506": "EMEC_Ingresos_ComercioMenor_46",
    # ── IGAE ─────────────────────────────────────────────────────────────────
    "737173": "IGAE_Secundario_Indice",
    "737149": "IGAE_Secundario_VarAnual",
    # ── BALANZA COMERCIAL SIDERURGIA ──────────────────────────────────────────
    "133094": "BC_Siderurgia_Importaciones",
    "133031": "BC_Siderurgia_Exportaciones",
    # ── INPP ─────────────────────────────────────────────────────────────────
    "910503": "INPP_Manufactura_3133",
    "910502": "INPP_Construccion_23",
    "910501": "INPP_Energia_22",
    "910500": "INPP_Mineria_SinPetroleo",
    "910499": "INPP_Mineria_ConPetroleo",
    "910491": "INPP_SinPetroleo_ConServicios",
    # ── INPC ─────────────────────────────────────────────────────────────────
    "910396": "INPC_Total_Mensual",
    "909294": "INPC_Energeticos_NoSubyacente",
    "910398": "INPC_Energeticos_Gobierno",
    "910393": "INPC_Subyacente_Total",
    # ── IFB ──────────────────────────────────────────────────────────────────
    "741034": "IFB_Construccion",
    "741030": "IFB_Maquinaria_Importada",
    "741025": "IFB_Maquinaria_Nacional",
    # ── CONFIANZA ─────────────────────────────────────────────────────────────
    "701407": "ICE_Construccion",
    "701401": "ICE_Global",
    "334497": "ICC_Confianza_Consumidor",
}

# ── Etiquetas cortas legibles ────────────────────────────────────────────────
INDICADORES_LABEL = {
    "736407": "IMAI Act. Industrial (idx)",
    "736418": "IMAI Manufactura (idx)",
    "736414": "IMAI Construcción (idx)",
    "736475": "IMAI Met. Básicas 331 (idx)",
    "736476": "IMAI Hierro y Acero 3311 (idx)",
    "736481": "IMAI Prod. Metálicos 332 (idx)",
    "736491": "IMAI Maquinaria 333 (idx)",
    "736526": "IMAI Act. Industrial (var%)",
    "736533": "IMAI Construcción (var%)",
    "736594": "IMAI Met. Básicas 331 (var%)",
    "910468": "EMIM Vol. Físico (idx)",
    "910470": "EMIM Var. Anual (%)",
    "720332": "ENEC Obra Total",
    "720334": "ENEC Edificación",
    "720340": "ENEC Transporte Urb.",
    "718504": "EMEC Com. Mayoreo",
    "718506": "EMEC Com. Menudeo",
    "737173": "IGAE Secundario (idx)",
    "737149": "IGAE Sec. Var. Anual",
    "133094": "Bal. Importaciones",
    "133031": "Bal. Exportaciones",
    "910503": "INPP Manufactura",
    "910502": "INPP Construcción",
    "910501": "INPP Energía",
    "910500": "INPP Minería s/Pet.",
    "910499": "INPP Minería c/Pet.",
    "910491": "INPP s/Pet. c/Serv.",
    "910396": "INPC Total",
    "909294": "INPC Energéticos (NS)",
    "910398": "INPC Energía Gobierno",
    "910393": "INPC Subyacente",
    "741034": "IFB Construcción",
    "741030": "IFB Maq. Importada",
    "741025": "IFB Maq. Nacional",
    "701407": "ICE Construcción",
    "701401": "ICE Global",
    "334497": "ICC Consumidor",
}

# ── Grupos con metadatos ─────────────────────────────────────────────────────
GRUPOS_INEGI = {
    "IMAI": {
        "label": "Actividad Industrial",
        "desc": "Señal principal de los sectores que compran acero — Hierro & Acero (736476) y Met. Básicas 331 (736475) son los indicadores más directos para TYASA",
        "claves": ["736407","736418","736414","736475","736476","736481","736491","736526","736533","736594"],
        "color": "#5B8DB8",
        "icon": "🏭",
    },
    "EMIM": {
        "label": "Manufactura",
        "desc": "Termómetro mensual de manufactura desestacionalizado — refleja capacidad productiva instalada",
        "claves": ["910468","910470"],
        "color": "#64B5F6",
        "icon": "⚙️",
    },
    "ENEC": {
        "label": "Construcción",
        "desc": "Valor de producción desglosada por tipo de obra — Transporte Urbano (720340) útil para demanda de perfiles",
        "claves": ["720332","720334","720340"],
        "color": "#81C784",
        "icon": "🏗️",
    },
    "EMEC": {
        "label": "Comercio",
        "desc": "Canal distribuidor TYASA — si el comercio mayoreo cae, los distribuidores de acero venden menos",
        "claves": ["718504","718506"],
        "color": "#CE93D8",
        "icon": "🛒",
    },
    "IGAE": {
        "label": "Actividad Económica",
        "desc": "Macro-termómetro del sector industrial — anticipa tendencias de demanda con 1-2 meses",
        "claves": ["737173","737149"],
        "color": "#4DD0E1",
        "icon": "📈",
    },
    "Balanza": {
        "label": "Balanza Siderúrgica",
        "desc": "Críticos para competitividad TYASA — importaciones altas presionan precios a la baja",
        "claves": ["133094","133031"],
        "color": "#FFB74D",
        "icon": "⚖️",
    },
    "INPP": {
        "label": "Precios Productor",
        "desc": "Corazón del modelo de margen — INPP Manufactura (910503) vs Minería (910500/910501) define spread",
        "claves": ["910503","910502","910501","910500","910499","910491"],
        "color": "#EF9A9A",
        "icon": "💰",
    },
    "INPC": {
        "label": "Precios Consumidor",
        "desc": "Contexto macro — INPC Total, Subyacente, Energía NS y Gobierno",
        "claves": ["910396","909294","910398","910393"],
        "color": "#F48FB1",
        "icon": "🏪",
    },
    "IFB": {
        "label": "Inversión Fija Bruta",
        "desc": "Predictor de demanda futura con 3-6 meses de anticipación — Maquinaria Importada (741030) señala capex industrial",
        "claves": ["741034","741030","741025"],
        "color": "#7986CB",
        "icon": "🏦",
    },
    "EMOE": {
        "label": "Confianza Empresarial",
        "desc": "Expectativas forward-looking del sector industrial y consumidor — lidera el ciclo real 1-3 meses",
        "claves": ["701407","701401","334497"],
        "color": "#E05C2D",
        "icon": "💡",
    },
}


# ── Funciones de carga ───────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Cargando indicadores INEGI...")
def load_todos_indicadores() -> pd.DataFrame:
    sql = f"""
        SELECT CLAVE, NOMBRE, FECHA, VALOR
        FROM {T_INDICADORES}
        ORDER BY CLAVE, FECHA DESC
    """
    return _lc(run_query(sql))


@st.cache_data(ttl=3600, show_spinner="Cargando indicador...")
def load_indicador(clave: str) -> pd.DataFrame:
    sql = f"""
        SELECT FECHA, VALOR, NOMBRE
        FROM {T_INDICADORES}
        WHERE CLAVE = '{clave}'
        ORDER BY FECHA DESC
        FETCH FIRST 500 ROWS ONLY
    """
    df = _lc(run_query(sql))
    if not df.empty and "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m", errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_indicadores_por_grupo(grupo: str) -> pd.DataFrame:
    clves = [c for c, n in INDICADORES_CONFIG.items() if grupo.upper() in n.upper()]
    if not clves:
        return pd.DataFrame()
    sql = f"""
        SELECT CLAVE, NOMBRE, FECHA, VALOR
        FROM {T_INDICADORES}
        WHERE CLAVE IN ({','.join([f"'{c}'" for c in clves])})
        ORDER BY CLAVE, FECHA DESC
    """
    return _lc(run_query(sql))


@st.cache_data(ttl=3600)
def load_serie(clave: str, periodos: int = 24) -> pd.DataFrame:
    sql = f"""
        SELECT FECHA, VALOR
        FROM {T_INDICADORES}
        WHERE CLAVE = '{clave}'
        ORDER BY FECHA DESC
        FETCH FIRST {periodos} ROWS ONLY
    """
    df = _lc(run_query(sql))
    if not df.empty and "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m", errors="coerce")
        df = df.sort_values("fecha")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_alertas(periodos_hist: int = 24) -> pd.DataFrame:
    """
    Z-score de cada indicador vs su propia distribución histórica.
    Niveles: Crítico |z|>2.5 · Alto |z|>1.5 · Moderado |z|>1.0 · Normal.
    """
    sql = f"""
        WITH hist AS (
            SELECT CLAVE, NOMBRE, VALOR, FECHA,
                   ROW_NUMBER() OVER (PARTITION BY CLAVE ORDER BY FECHA DESC) AS rn
            FROM {T_INDICADORES}
        ),
        stats AS (
            SELECT CLAVE,
                   MAX(CASE WHEN rn = 1 THEN NOMBRE END) AS NOMBRE,
                   MAX(CASE WHEN rn = 1 THEN FECHA  END) AS ULT_FECHA,
                   MAX(CASE WHEN rn = 1 THEN VALOR  END) AS ULT_VALOR,
                   MAX(CASE WHEN rn = 2 THEN VALOR  END) AS ANT_VALOR,
                   AVG(VALOR)    AS MEDIA,
                   STDDEV(VALOR) AS STD
            FROM hist
            WHERE rn <= {periodos_hist}
            GROUP BY CLAVE
        )
        SELECT CLAVE, NOMBRE, ULT_FECHA, ULT_VALOR, ANT_VALOR, MEDIA, STD,
               CASE WHEN STD != 0 THEN (ULT_VALOR - MEDIA) / STD ELSE NULL END AS Z_SCORE
        FROM stats
    """
    df = _lc(run_query(sql))
    if df.empty:
        return df

    df["clave"] = df["clave"].astype(str)

    def _nivel(z):
        try:
            az = abs(float(z))
            if az > 2.5:
                return "Critico"
            if az > 1.5:
                return "Alto"
            if az > 1.0:
                return "Moderado"
        except Exception:
            pass
        return "Normal"

    df["z_score"] = pd.to_numeric(df["z_score"], errors="coerce")
    df["alerta"]  = df["z_score"].apply(_nivel)
    ult = pd.to_numeric(df["ult_valor"], errors="coerce")
    ant = pd.to_numeric(df["ant_valor"], errors="coerce")
    df["var_mom"] = (ult - ant).div(ant.abs()).mul(100).round(1)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_sparklines(n_periodos: int = 12) -> dict:
    """Últimos N periodos de todos los indicadores (cronológico asc) para sparklines."""
    sql = f"""
        WITH ranked AS (
            SELECT CLAVE, VALOR,
                   ROW_NUMBER() OVER (PARTITION BY CLAVE ORDER BY FECHA DESC) AS rn
            FROM {T_INDICADORES}
        )
        SELECT CLAVE, VALOR
        FROM ranked
        WHERE rn <= {n_periodos}
        ORDER BY CLAVE, rn DESC
    """
    df = _lc(run_query(sql))
    result: dict = {}
    if not df.empty:
        df["clave"] = df["clave"].astype(str)
        for clave, grp in df.groupby("clave"):
            vals = pd.to_numeric(grp["valor"], errors="coerce").dropna().tolist()
            if vals:
                result[clave] = vals
    return result
