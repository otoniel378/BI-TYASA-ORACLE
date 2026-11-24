"""
alertas.py — Bandeja única de alertas de TYASA BI.

Reúne en una sola lista las señales que hoy viven en distintas páginas y
correos: ventas de Aceros Planos (clientes que dejaron de comprar, caída del
mes), ferroaleaciones (semáforo de alza), quiebres de mercado, decretos del
DOF, sentimiento de noticias y calidad / frescura de los datos (core/calidad_datos.py). La usan la página
pages/alertas_bandeja.py, el contador del Hub y el resumen semanal por correo
(scripts/enviar_resumen_semanal.py).

Las alertas no se guardan: se calculan con lo vigente en Oracle; una alerta
desaparece cuando deja de cumplirse. Si una fuente falla, aparece una alerta
informativa en lugar de romper la bandeja.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import streamlit as st

from core import metricas
from core.db_connector import run_query_params, table_ref

PRIORIDADES = ("alta", "media", "info")

# Umbrales (los de datos desactualizados viven en core/calidad_datos.FUENTES)
CAIDA_MES_MEDIA, CAIDA_MES_ALTA = -10, -25      # % vs mismo mes del año anterior
TOP_CLIENTES_PRIORITARIOS = 20                  # por toneladas de los últimos 12 meses
DIAS_DOF = 30
DIAS_QUIEBRE_RECIENTE = 45
MIN_NOTICIAS_SENTIMIENTO, PCT_NEGATIVAS = 5, 50

# Destinos de navegación de app.py (nav_seccion, nav_subseccion, nav_modulo_planos)
DESTINO_ALERTAS_NEGROS = ("aceros_planos", "negros", "apn_alertas")
DESTINO_CLIENTES_NEGROS = ("aceros_planos", "negros", "apn_intel")
DESTINO_FERROS = ("mercado", "mkt_ferros", None)
DESTINO_MONITOR = ("mercado", "mkt_monitor", None)
DESTINO_COMERCIO = ("mercado", "mkt_comercio", None)
DESTINO_SENTIMIENTO = ("mas_info", "mi_sentimiento", None)
DESTINO_ESTADO_DATOS = ("inicio", "datos", None)


@dataclass
class Alerta:
    prioridad: str          # alta | media | info
    area: str               # "Aceros Planos" | "Mercado Global" | "Sistema"
    fuente: str
    titulo: str
    detalle: str = ""
    fecha: date | None = None
    destino: tuple | None = None
    clave: str = field(default="")   # para quitar duplicados


def _q(sql: str, params: dict | None = None) -> pd.DataFrame:
    df = run_query_params(sql, params or {})
    df.columns = [c.upper() for c in df.columns]
    return df


def _dias(fecha, hoy: date) -> int:
    return (pd.Timestamp(hoy) - pd.Timestamp(fecha).normalize()).days


def _fmt_fecha(fecha) -> str:
    return f"{pd.Timestamp(fecha):%d/%m/%Y}"


# ── Sistema: datos desactualizados ───────────────────────────────────────────
def alertas_calidad(hoy: date) -> list[Alerta]:
    """Fuentes desactualizadas y reglas de calidad (core/calidad_datos.py).
    Falla → la prioridad de la fuente (ventas = alta); aviso → informativa."""
    from core import calidad_datos
    out = []
    for r in calidad_datos.revisar(hoy):
        if r.estado == "ok":
            continue
        prioridad = r.prioridad if r.estado == "falla" else "info"
        if r.tipo == "frescura":
            titulo = f"{r.fuente}: datos sin actualizar" if r.estado == "falla" else f"{r.fuente}: actualización atrasada"
        else:
            titulo = f"{r.fuente}: {r.regla.lower()} — no se cumple"
        out.append(Alerta(prioridad, "Sistema", "Calidad de datos", titulo, r.detalle, r.fecha,
                          DESTINO_ESTADO_DATOS, clave=f"calidad_{r.fuente}_{r.regla}"))
    return out


# ── Aceros Planos: clientes y volumen ────────────────────────────────────────
def alertas_clientes(hoy: date) -> list[Alerta]:
    cli = metricas.ultima_compra_por_cliente()
    top = set(cli.head(TOP_CLIENTES_PRIORITARIOS)["CLIENTE"])
    fuga = cli[(cli["DIAS_SIN_COMPRA"] > metricas.DIAS_ALERTA_SIN_COMPRA)
               & (cli["DIAS_SIN_COMPRA"] <= metricas.DIAS_CLIENTE_EN_RIESGO) & (cli["TON_RECIENTE"] > 0)]
    out = []
    for _, r in fuga[fuga["CLIENTE"].isin(top)].iterrows():
        out.append(Alerta("alta", "Aceros Planos", "Clientes",
                          f"{r['CLIENTE']} lleva {r['DIAS_SIN_COMPRA']} días sin comprar",
                          f"Cliente top: {r['TON_RECIENTE']:,.0f} t en los últimos 12 meses. "
                          f"Última compra {_fmt_fecha(r['ULTIMA_COMPRA'])}.",
                          r["ULTIMA_COMPRA"], DESTINO_CLIENTES_NEGROS, clave=f"fuga_{r['CLIENTE']}"))
    resto = fuga[~fuga["CLIENTE"].isin(top)]
    if not resto.empty:
        out.append(Alerta("media", "Aceros Planos", "Clientes",
                          f"{len(resto)} clientes más llevan más de {metricas.DIAS_ALERTA_SIN_COMPRA} días sin comprar",
                          "Suman " + f"{resto['TON_RECIENTE'].sum():,.0f} t en los últimos 12 meses: "
                          + ", ".join(resto["CLIENTE"].head(5)) + ("…" if len(resto) > 5 else ""),
                          None, DESTINO_ALERTAS_NEGROS, clave="fuga_resto"))
    return out


def alertas_volumen(hoy: date) -> list[Alerta]:
    v = metricas.variacion("toneladas", "anio_anterior")
    if v["pct"] is None:
        return []
    mes = f"{v['mes']:%m/%Y}"
    if v["pct"] <= CAIDA_MES_MEDIA:
        prioridad = "alta" if v["pct"] <= CAIDA_MES_ALTA else "media"
        return [Alerta(prioridad, "Aceros Planos", "Ventas", f"Ventas de {mes}: {v['pct']:+.0f} % vs el año anterior",
                       f"{v['actual']:,.0f} t contra {v['base']:,.0f} t en {v['mes_base']:%m/%Y} (último mes completo).",
                       v["mes"], DESTINO_ALERTAS_NEGROS, clave="volumen_mes")]
    if v["pct"] >= -CAIDA_MES_ALTA:
        return [Alerta("info", "Aceros Planos", "Ventas", f"Ventas de {mes}: {v['pct']:+.0f} % vs el año anterior",
                       f"{v['actual']:,.0f} t contra {v['base']:,.0f} t.", v["mes"], DESTINO_ALERTAS_NEGROS,
                       clave="volumen_mes")]
    return []


# ── Mercado Global ───────────────────────────────────────────────────────────
def alertas_dof(hoy: date) -> list[Alerta]:
    # FECHA_DOF es texto dd/mm/aaaa (así lo publica el DOF)
    df = _q(f"""SELECT TO_DATE(FECHA_DOF, 'DD/MM/YYYY') FECHA_DOF, IMPACTO, DIRECCION, RESUMEN, DESCRIPCION,
                       FRACCIONES_TYASA, CODIGO
                FROM {table_ref('GOLD_ALERTAS_DOF')}
                WHERE RELEVANTE = 1 AND TO_DATE(FECHA_DOF, 'DD/MM/YYYY') >= :desde
                ORDER BY 1 DESC""",
            {"desde": (pd.Timestamp(hoy) - pd.Timedelta(days=DIAS_DOF)).to_pydatetime()})
    out = []
    for _, r in df.iterrows():
        prioridad = "alta" if str(r["IMPACTO"]).lower() == "alto" else "media"
        fracc = f" Fracciones TYASA: {r['FRACCIONES_TYASA']}." if pd.notna(r["FRACCIONES_TYASA"]) else ""
        out.append(Alerta(prioridad, "Mercado Global", "DOF", f"Decreto del DOF ({_fmt_fecha(r['FECHA_DOF'])}): "
                          f"impacto {str(r['IMPACTO']).lower()}", f"{r['RESUMEN'] or r['DESCRIPCION']}{fracc}",
                          r["FECHA_DOF"], DESTINO_COMERCIO, clave=f"dof_{r['CODIGO']}"))
    return out


def alertas_semaforo(hoy: date) -> list[Alerta]:
    df = _q(f"""SELECT s.SERIE, s.FECHA, s.SEMAFORO, s.PROB, NVL(m.CONFIABLE, 0) CONFIABLE
                FROM {table_ref('GOLD_SEMAFORO_FERROS')} s
                LEFT JOIN {table_ref('GOLD_SEMAFORO_METRICAS')} m ON m.SERIE = s.SERIE
                WHERE s.TIPO = 'actual' AND s.SEMAFORO IN ('Rojo', 'Amarillo')""")
    out = []
    for _, r in df.iterrows():
        confiable = bool(r["CONFIABLE"])
        prioridad = ({"Rojo": "alta", "Amarillo": "media"} if confiable else {"Rojo": "media", "Amarillo": "info"})[r["SEMAFORO"]]
        out.append(Alerta(prioridad, "Mercado Global", "Ferroaleaciones",
                          f"{r['SERIE']} en {r['SEMAFORO'].lower()}: riesgo de alza en los próximos 3 meses",
                          f"Probabilidad {float(r['PROB']):.0%}." + ("" if confiable else " Señal débil: solo referencia."),
                          r["FECHA"], DESTINO_FERROS, clave=f"semaforo_{r['SERIE']}"))
    return out


def alertas_quiebres(hoy: date) -> list[Alerta]:
    df = _q(f"""SELECT VARIABLE, FECHA_CORTE, CAMBIO_PCT, SEVERIDAD
                FROM {table_ref('GOLD_QUIEBRES_DETECTADOS')}
                WHERE ACTIVO = 1 AND SEVERIDAD IN ('Critico', 'Alto')""")
    if df.empty:
        return []
    ult = df["FECHA_CORTE"].max()
    recientes = df[(df["SEVERIDAD"] == "Critico")
                   & (df["FECHA_CORTE"] >= ult - pd.Timedelta(days=DIAS_QUIEBRE_RECIENTE))]
    out = [Alerta("media", "Mercado Global", "Quiebres de mercado",
                  f"Cambio brusco en {r['VARIABLE']} ({float(r['CAMBIO_PCT']):+.0f} %)",
                  f"Quiebre crítico detectado al {_fmt_fecha(r['FECHA_CORTE'])}.", r["FECHA_CORTE"],
                  DESTINO_MONITOR, clave=f"quiebre_{r['VARIABLE']}")
           for _, r in recientes.sort_values("FECHA_CORTE", ascending=False).iterrows()]
    resto = df[~df["VARIABLE"].isin(recientes["VARIABLE"])]["VARIABLE"].drop_duplicates()
    if not resto.empty:
        out.append(Alerta("info", "Mercado Global", "Quiebres de mercado",
                          f"{len(resto)} variables más con quiebres altos o críticos activos",
                          ", ".join(resto.head(8)) + ("…" if len(resto) > 8 else ""),
                          None, DESTINO_MONITOR, clave="quiebres_resto"))
    return out


def alertas_sentimiento(hoy: date) -> list[Alerta]:
    df = _q(f"""SELECT SENTIMIENTO, COUNT(*) N FROM {table_ref('GOLD_SENTIMIENTO_NOTICIAS')}
                WHERE FECHA_PUB >= :desde GROUP BY SENTIMIENTO""",
            {"desde": (pd.Timestamp(hoy) - pd.Timedelta(days=7)).to_pydatetime()})
    total = int(df["N"].sum()) if not df.empty else 0
    neg = int(df.loc[df["SENTIMIENTO"].str.lower() == "negativo", "N"].sum()) if total else 0
    if total >= MIN_NOTICIAS_SENTIMIENTO and neg / total * 100 > PCT_NEGATIVAS:
        return [Alerta("media", "Mercado Global", "Noticias",
                       f"Semana con noticias mayormente negativas ({neg} de {total})",
                       "Revisar los temas que las provocan.", hoy, DESTINO_SENTIMIENTO, clave="sentimiento")]
    return []


FUENTES = {
    "Calidad de datos": alertas_calidad,
    "Clientes": alertas_clientes,
    "Ventas": alertas_volumen,
    "DOF": alertas_dof,
    "Ferroaleaciones": alertas_semaforo,
    "Quiebres de mercado": alertas_quiebres,
    "Noticias": alertas_sentimiento,
}
_AREA_FUENTE = {"Clientes": "Aceros Planos", "Ventas": "Aceros Planos"}


def recolectar(hoy: date | None = None, areas_permitidas: list[str] | None = None) -> list[Alerta]:
    """Todas las alertas vigentes, de mayor a menor prioridad y más recientes
    primero. <areas_permitidas>: como Usuario.areas_permitidas (vacío = todo);
    Mercado Global y Sistema se muestran a todos."""
    hoy = hoy or date.today()
    out: list[Alerta] = []
    for nombre, fn in FUENTES.items():
        if areas_permitidas and _AREA_FUENTE.get(nombre) == "Aceros Planos" and "aceros_planos" not in areas_permitidas:
            continue
        try:
            out += fn(hoy)
        except Exception as e:  # una fuente caída no tumba la bandeja
            out.append(Alerta("info", "Sistema", nombre, f"No se pudo revisar: {nombre}", str(e)[:200],
                              clave=f"error_{nombre}"))
    vistos, unicas = set(), []
    for a in out:
        if a.clave and a.clave in vistos:
            continue
        vistos.add(a.clave)
        unicas.append(a)
    orden = {p: i for i, p in enumerate(PRIORIDADES)}
    return sorted(unicas, key=lambda a: (orden[a.prioridad], -(pd.Timestamp(a.fecha).value if a.fecha is not None else 0)))


def a_dataframe(alertas: list[Alerta]) -> pd.DataFrame:
    return pd.DataFrame([a.__dict__ for a in alertas],
                        columns=["prioridad", "area", "fuente", "titulo", "detalle", "fecha", "destino", "clave"])


@st.cache_data(ttl=600, show_spinner="Revisando alertas...")
def alertas_vigentes(areas_permitidas: tuple = ()) -> pd.DataFrame:
    """recolectar() con caché para la app (bandeja y contador del Hub)."""
    return a_dataframe(recolectar(areas_permitidas=list(areas_permitidas)))
