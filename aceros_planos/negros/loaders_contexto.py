"""
loaders_contexto.py — Loaders de contexto externo para Aceros Planos Negros.
Importa y cachea datos de INEGI, mercado global y quiebres para los módulos
de contexto de mercado. TTL más largo (3600) porque estas fuentes cambian menos.
"""

import pandas as pd
import streamlit as st

from mercado.inegi.loaders import calcular_alertas, load_sparklines
from mercado_noticias.loaders import load_variables_mercado, load_quiebres_activos

# ── Catálogos de relevancia ───────────────────────────────────────────────────
CLAVES_INEGI_PLANOS = [
    "736418",  # IMAI Manufactureras
    "736476",  # IMAI Hierro y Acero
    "736481",  # IMAI Productos Metálicos
    "736491",  # IMAI Maquinaria
    "737173",  # IGAE Secundario Índice
    "737149",  # IGAE Secundario Var Anual
    "718504",  # EMEC Comercio Mayor
    "910503",  # INPP Manufactura
    "910396",  # INPC Total
    "741034",  # IFB Construcción
    "741030",  # IFB Maquinaria Importada
]

VARS_MERCADO_PLANOS = [
    "ETF_Acero_Global",
    "Ternium_MX",
    "ArcelorMittal",
    "Cobre_USD",
    "Aluminio_USD",
    "USD_MXN",
    "VIX",
    "SP500",
]


# ── Loaders cacheados ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner="Cargando alertas INEGI...")
def load_alertas_inegi_planos() -> pd.DataFrame:
    """Alertas Z-score de INEGI filtradas para indicadores relevantes de Aceros Planos."""
    try:
        df = calcular_alertas()
        if df.empty:
            return pd.DataFrame()
        return df[df["Clave"].isin(CLAVES_INEGI_PLANOS)].copy()
    except Exception as e:
        print(f"[loaders_contexto] load_alertas_inegi_planos: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner="Cargando variables de mercado...")
def load_vars_mercado_planos(dias: int = 400) -> pd.DataFrame:
    """Variables de mercado filtradas para Aceros Planos (long format)."""
    try:
        df = load_variables_mercado(dias=dias)
        if df.empty:
            return pd.DataFrame()
        return df[df["nombre"].isin(VARS_MERCADO_PLANOS)].copy()
    except Exception as e:
        print(f"[loaders_contexto] load_vars_mercado_planos: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def load_sparklines_inegi_planos() -> dict:
    """Sparklines de últimos 12 meses para indicadores relevantes de Aceros Planos."""
    try:
        all_spk = load_sparklines(12)
        return {k: v for k, v in all_spk.items() if k in CLAVES_INEGI_PLANOS}
    except Exception as e:
        print(f"[loaders_contexto] load_sparklines_inegi_planos: {e}")
        return {}


@st.cache_data(ttl=3600, show_spinner="Cargando indicadores para escenarios...")
def load_indicadores_escenarios() -> pd.DataFrame:
    """Indicadores del simulador de escenarios (analytics/escenarios.VARIABLES):
    índice = mes, una columna por indicador."""
    from aceros_planos.negros.analytics.escenarios import VARIABLES
    from mercado.inegi.loaders import load_serie_por_nombre
    partes = []
    for v in VARIABLES:
        s = load_serie_por_nombre(v.clave)
        if not s.empty:
            partes.append(s.dropna(subset=["fecha"]).set_index("fecha")["valor"].astype(float).rename(v.clave))
    return pd.concat(partes, axis=1).sort_index() if partes else pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def load_quiebres_relevantes_planos() -> pd.DataFrame:
    """Quiebres activos en variables de mercado relevantes para Aceros Planos."""
    try:
        df = load_quiebres_activos()
        if df.empty:
            return pd.DataFrame()
        vars_rel = set(VARS_MERCADO_PLANOS)
        if "variable" in df.columns:
            return df[df["variable"].isin(vars_rel)].copy()
        return pd.DataFrame()
    except Exception as e:
        print(f"[loaders_contexto] load_quiebres_relevantes_planos: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def load_noticias_acero_plano() -> list[dict]:
    """Noticias recientes sobre HRC, lámina galvanizada y acero plano."""
    from mercado_noticias.analytics.noticias import _buscar_google_news
    queries = [
        "HRC hot rolled coil acero laminado caliente precio",
        "lámina galvanizada zinc precio mercado México",
        "acero plano México manufactura automotriz demanda",
    ]
    todos: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        try:
            for n in _buscar_google_news(q, max_resultados=5):
                url = n.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    todos.append(n)
        except Exception:
            continue
    return sorted(todos, key=lambda x: x.get("fecha_pub", ""), reverse=True)[:15]
