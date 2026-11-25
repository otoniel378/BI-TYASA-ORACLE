"""
mercado_rutas/datos.py — Cargadores de la página Rutas y puertos (con caché).

El tráfico de PortWatch se lee de Oracle (GOLD_TRAFICO_PASOS, GOLD_TRAFICO_PUERTOS,
que llena scripts/update_trafico_maritimo.py cada día). Si esas tablas todavía
no existen o están vacías, se descarga directo de HDX (~45 s la primera vez,
luego queda en caché 12 h) y la página lo indica.
"""

import pandas as pd
import streamlit as st

from core.db_connector import run_query, table_ref
from mercado_noticias.analytics.rutas_alertas import DIAS_VIGENCIA, alertas_rutas
from mercado_noticias.loaders import load_noticias_periodo
from mercado_rutas import fuentes


def _de_oracle(tabla: str, columnas: str) -> pd.DataFrame:
    try:
        df = run_query(f"SELECT {columnas} FROM {table_ref(tabla)}")
    except Exception:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data(ttl=12 * 3600, show_spinner="Descargando tráfico marítimo de IMF PortWatch (~45 s)...")
def _descarga_directa() -> tuple[pd.DataFrame, pd.DataFrame]:
    return fuentes.descargar_pasos(), fuentes.descargar_puertos()


@st.cache_data(ttl=3600, show_spinner=False)
def load_trafico() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """(pasos, puertos, origen). pasos: fecha, paso, transitos, granel ·
    puertos: fecha, puerto, llamadas, granel · origen: 'oracle' | 'descarga'."""
    pasos = _de_oracle("GOLD_TRAFICO_PASOS", "FECHA, PASO, TRANSITOS, GRANEL")
    puertos = _de_oracle("GOLD_TRAFICO_PUERTOS", "FECHA, PUERTO, LLAMADAS, GRANEL")
    if not pasos.empty and not puertos.empty:
        return pasos, puertos, "oracle"
    try:
        pasos, puertos = _descarga_directa()
        return pasos, puertos, "descarga"
    except Exception:
        return pd.DataFrame(columns=["fecha", "paso", "transitos", "granel"]), \
            pd.DataFrame(columns=["fecha", "puerto", "llamadas", "granel"]), "sin datos"


@st.cache_data(ttl=1800, show_spinner=False)
def load_avisos(dias: int = DIAS_VIGENCIA) -> pd.DataFrame:
    """Noticias de los últimos <dias> ligadas a pasos, países y puertos
    (rutas_alertas): nodo, lugar, titulo, url, fuente, fecha, severidad, tipo_impacto, razon."""
    hoy = pd.Timestamp.now()
    noticias = load_noticias_periodo(hoy - pd.Timedelta(days=dias), hoy)
    return alertas_rutas(noticias, dias=dias, max_por_lugar=12)


NIVEL_SEMAFORO = {"Verde": "normal", "Amarillo": "vigilar", "Rojo": "riesgo"}


@st.cache_data(ttl=3600, show_spinner=False)
def load_precios_materiales() -> dict:
    """Por material (red.MATERIALES): último precio y fecha, cambio a 3 meses,
    semáforo de alza (nivel, texto, confiable), si el precio está arriba de su
    rango normal y el quiebre en formación, si hay. Precios de
    mercado_fastmarkets; semáforo de GOLD_SEMAFORO_FERROS."""
    from mercado_fastmarkets.loaders import load_ferroaleaciones, load_semaforo_ferros
    from mercado_noticias.analytics.rupturas import bandas_normales, normalizar_mensual, quiebre_en_formacion
    from mercado_rutas.red import SERIE_PRECIO

    try:
        ancho = normalizar_mensual(load_ferroaleaciones())
        prob, met = load_semaforo_ferros()
    except Exception:
        return {}
    actual = prob[prob["tipo"] == "actual"].set_index("serie") if not prob.empty else pd.DataFrame()
    confiable = dict(zip(met["serie"], met["confiable"].astype(int).astype(bool))) if not met.empty else {}
    out = {}
    for mat, serie in SERIE_PRECIO.items():
        if serie not in ancho.columns:
            continue
        p = ancho[serie].dropna()
        if p.empty:
            continue
        b = bandas_normales(p).iloc[-1]
        sem = actual.loc[serie, "semaforo"] if serie in actual.index else None
        out[mat] = {
            "serie": serie, "precio": float(p.iloc[-1]), "fecha": p.index[-1],
            "cambio_3m": float(p.iloc[-1] / p.iloc[-4] - 1) if len(p) > 3 else None,
            "semaforo": sem, "nivel": NIVEL_SEMAFORO.get(sem, "sin datos"), "confiable": confiable.get(serie, False),
            "arriba": bool(pd.notna(b["banda_sup"]) and b["precio"] > b["banda_sup"]),
            "formacion": quiebre_en_formacion(p),
        }
    out.update(_precios_mercado())
    return out


def _precios_mercado() -> dict:
    """Insumos con precio diario en GOLD_VARIABLES_MERCADO (aluminio, zinc): último
    precio y cambio a 3 meses, sin semáforo de alza."""
    from mercado_noticias.loaders import load_variables_mercado
    from mercado_rutas.red import PRECIO_MERCADO

    try:
        v = load_variables_mercado(dias=200)
    except Exception:
        return {}
    out = {}
    for mat, nombre in PRECIO_MERCADO.items():
        s = v[v["nombre"] == nombre].dropna(subset=["valor"]).set_index("fecha")["valor"].sort_index()
        if s.empty:
            continue
        hace3 = s[s.index <= s.index[-1] - pd.DateOffset(months=3)]
        out[mat] = {"serie": nombre, "precio": float(s.iloc[-1]), "fecha": s.index[-1],
                    "cambio_3m": float(s.iloc[-1] / hace3.iloc[-1] - 1) if not hace3.empty else None,
                    "semaforo": None, "nivel": "sin datos", "confiable": False, "arriba": False, "formacion": None}
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def load_tormentas() -> pd.DataFrame:
    try:
        return fuentes.tormentas_activas()
    except Exception:
        return pd.DataFrame(columns=["nombre", "tipo", "viento_kt", "lat", "lon", "puerto", "km"])


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def load_oleaje() -> pd.DataFrame:
    try:
        return fuentes.oleaje_puertos()
    except Exception:
        return pd.DataFrame(columns=["puerto", "oleaje_max_m", "dia"])
