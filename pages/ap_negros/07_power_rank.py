"""
07_power_rank.py — Power Rank de Clientes — Aceros Planos Negros.
Ranking de clientes por toneladas en una ventana de tiempo, comparado contra la
misma ventana del año anterior: lugar, cambio de lugar, participación,
variación, tendencia, concentración y clientes ganados/perdidos.

DOM-STABLE: el HTML dinámico usa st.html().
"""

import os, sys
from html import escape

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
from config import COLORS

from aceros_planos.negros.loaders import load_serie_mensual_cliente
from core.components.kpi_cards import render_kpi_row, seccion_titulo
from core.components.charts import barras_divergentes, estructura_100, trayectoria_ranking

# Texto de "sube / baja": aquí sí es bueno o malo (son ventas de TYASA), así que
# verde/rojo, siempre acompañado de ▲▼ para no depender solo del color.
_TXT_SUBE, _TXT_BAJA = "#15803D", "#B91C1C"
_MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

VENTANAS = {
    "Últimos 12 meses": 12,
    "Acumulado del año": None,
    "Último trimestre": 3,
    "Último mes": 1,
}


def _mes_txt(ts: pd.Timestamp) -> str:
    return f"{_MESES[ts.month]} {ts.year}"


def _corto(nombre: str, n: int = 38) -> str:
    return nombre if len(nombre) <= n else nombre[: n - 1] + "…"


def _rango(corte: pd.Timestamp, ventana: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    meses = VENTANAS[ventana]
    inicio = pd.Timestamp(corte.year, 1, 1) if meses is None else corte - pd.DateOffset(months=meses - 1)
    return inicio, corte


def _ranking(serie: pd.DataFrame, inicio: pd.Timestamp, fin: pd.Timestamp) -> pd.DataFrame:
    sub = serie[(serie["PERIODO"] >= inicio) & (serie["PERIODO"] <= fin)]
    r = sub.groupby("CLIENTE", as_index=False)["PESO_TON"].sum()
    r = r[r["PESO_TON"] > 0].sort_values("PESO_TON", ascending=False)
    r["LUGAR"] = range(1, len(r) + 1)
    return r


def _sparkline(valores: list[float], ancho: int = 92, alto: int = 24) -> str:
    mx = max(valores) or 1
    paso = ancho / max(len(valores) - 1, 1)
    pts = " ".join(f"{i * paso:.1f},{alto - 2 - v / mx * (alto - 4):.1f}" for i, v in enumerate(valores))
    ux, uy = pts.split(" ")[-1].split(",")
    return (
        f"<svg width='{ancho}' height='{alto}' viewBox='-2 0 {ancho + 4} {alto}'>"
        f"<polyline points='{pts}' fill='none' stroke='{COLORS['primary']}' stroke-width='1.5' "
        f"stroke-linejoin='round'/><circle cx='{ux}' cy='{uy}' r='2.2' fill='{COLORS['primary']}'/></svg>"
    )


def _movimiento(lugar: int, lugar_ant) -> str:
    if pd.isna(lugar_ant):
        return (f"<span style='font-size:0.66rem;font-weight:700;color:{COLORS['primary']};"
                f"background:#E8EFF5;padding:1px 6px;border-radius:10px;'>NUEVO</span>")
    dif = int(lugar_ant) - lugar
    if dif == 0:
        return f"<span style='color:{COLORS['text_light']};font-weight:600;'>=</span>"
    color, flecha = (_TXT_SUBE, "▲") if dif > 0 else (_TXT_BAJA, "▼")
    return f"<span style='color:{color};font-weight:700;'>{flecha} {abs(dif)}</span>"


def _variacion(actual: float, anterior: float) -> str:
    if not anterior:
        return f"<span style='color:{COLORS['text_light']};'>—</span>"
    var = (actual - anterior) / anterior * 100
    color, flecha = (_TXT_SUBE, "▲") if var >= 0 else (_TXT_BAJA, "▼")
    return f"<span style='color:{color};font-weight:600;'>{flecha} {abs(var):.0f}%</span>"


def _tabla_power_rank(rank: pd.DataFrame, total: float, sparks: dict, n: int) -> str:
    top = rank.head(n)
    max_vol = top["PESO_TON"].max() or 1
    cols = "34px 58px minmax(160px,1fr) 150px 64px 74px 100px"
    th = (f"font-size:0.68rem;font-weight:700;color:{COLORS['text_light']};text-transform:uppercase;"
          "letter-spacing:.05em;")
    filas = [f"""
    <div style="display:grid;grid-template-columns:{cols};gap:10px;padding:0 0 8px;border-bottom:2px solid #E2E8F0;">
      <div style="{th}text-align:center;">#</div><div style="{th}">Mov.</div><div style="{th}">Cliente</div>
      <div style="{th}text-align:right;">Toneladas</div><div style="{th}text-align:right;">Part.</div>
      <div style="{th}text-align:right;">vs año ant.</div><div style="{th}text-align:center;">Últimos 12 m</div>
    </div>"""]
    for r in top.itertuples():
        nombre = escape(r.CLIENTE)
        filas.append(f"""
    <div style="display:grid;grid-template-columns:{cols};gap:10px;align-items:center;padding:7px 0;
                border-bottom:1px solid #F1F5F9;">
      <div style="font-size:0.95rem;font-weight:800;color:{COLORS['primary']};text-align:center;">{r.LUGAR}</div>
      <div style="font-size:0.78rem;">{_movimiento(r.LUGAR, r.LUGAR_ANT)}</div>
      <div title="{nombre}" style="font-size:0.84rem;font-weight:600;color:{COLORS['text']};white-space:nowrap;
                  overflow:hidden;text-overflow:ellipsis;">{escape(_corto(r.CLIENTE))}</div>
      <div>
        <div style="font-size:0.82rem;font-weight:700;color:{COLORS['text']};text-align:right;">{r.PESO_TON:,.0f} t</div>
        <div style="height:5px;background:{COLORS['background']};border-radius:3px;margin-top:3px;overflow:hidden;">
          <div style="height:100%;width:{max(r.PESO_TON / max_vol * 100, 2):.0f}%;background:{COLORS['primary']};
                      border-radius:3px;"></div>
        </div>
      </div>
      <div style="font-size:0.8rem;color:{COLORS['text']};text-align:right;">{r.PESO_TON / total * 100:.1f}%</div>
      <div style="font-size:0.8rem;text-align:right;">{_variacion(r.PESO_TON, r.PESO_ANT)}</div>
      <div style="text-align:center;">{sparks.get(r.CLIENTE, '')}</div>
    </div>""")
    return (f"<div style='background:{COLORS['surface']};border:1px solid #E5E7EB;border-radius:14px;"
            f"padding:16px 20px;overflow-x:auto;'><div style='min-width:640px;'>{''.join(filas)}</div></div>")


def _lista_clientes(titulo: str, subtitulo: str, df: pd.DataFrame, col: str, color: str) -> str:
    if df.empty:
        cuerpo = f"<p style='color:{COLORS['text_light']};font-size:0.82rem;margin:0;'>Ninguno.</p>"
    else:
        cuerpo = "".join(
            f"<div style='display:flex;justify-content:space-between;gap:10px;padding:5px 0;"
            f"border-bottom:1px solid #F1F5F9;font-size:0.82rem;'>"
            f"<span title='{escape(r.CLIENTE)}' style='color:{COLORS['text']};white-space:nowrap;overflow:hidden;"
            f"text-overflow:ellipsis;'>{escape(_corto(r.CLIENTE, 34))}</span>"
            f"<span style='font-weight:700;color:{color};white-space:nowrap;'>{getattr(r, col):,.0f} t</span></div>"
            for r in df.itertuples()
        )
    return (f"<div style='background:{COLORS['surface']};border:1px solid #E5E7EB;border-radius:14px;"
            f"padding:16px 20px;height:100%;'>"
            f"<p style='margin:0 0 2px;font-size:0.95rem;font-weight:700;color:{COLORS['primary']};'>{titulo}</p>"
            f"<p style='margin:0 0 10px;font-size:0.78rem;color:{COLORS['text_light']};'>{subtitulo}</p>"
            f"{cuerpo}</div>")


# ---------------------------------------------------------------------------
# Encabezado y datos
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <h2 style='color:{COLORS["primary"]};margin-bottom:0;'>Power Rank de Clientes</h2>
    <p style='color:{COLORS["text_light"]};'>Quién compra más, quién sube y quién baja — contra el mismo periodo del año anterior</p>
    """,
    unsafe_allow_html=True,
)

with st.spinner("Cargando ventas por cliente..."):
    serie = load_serie_mensual_cliente()

if serie.empty:
    st.info("Sin ventas por cliente disponibles.")
    st.stop()

serie = serie.dropna(subset=["PERIODO"])
meses_disp = sorted(serie["PERIODO"].unique(), reverse=True)

c1, c2, c3, _ = st.columns([1.3, 1, 0.8, 2])
with c1:
    ventana = st.selectbox("Ventana", list(VENTANAS), key="pr_ventana")
with c2:
    corte = pd.Timestamp(st.selectbox(
        "Hasta el mes", meses_disp, format_func=lambda m: _mes_txt(pd.Timestamp(m)), key="pr_corte",
    ))
with c3:
    top_n = st.selectbox("Mostrar", [10, 20, 30, 50], index=1, format_func=lambda n: f"Top {n}", key="pr_top")

inicio, fin = _rango(corte, ventana)
inicio_ant, fin_ant = inicio - pd.DateOffset(years=1), fin - pd.DateOffset(years=1)
etq_act = _mes_txt(fin) if inicio == fin else f"{_mes_txt(inicio)} – {_mes_txt(fin)}"
etq_ant = _mes_txt(fin_ant) if inicio_ant == fin_ant else f"{_mes_txt(inicio_ant)} – {_mes_txt(fin_ant)}"

rank_act = _ranking(serie, inicio, fin)
rank_ant = _ranking(serie, inicio_ant, fin_ant)

if rank_act.empty:
    st.info(f"Sin ventas en {etq_act}.")
    st.stop()

rank = rank_act.merge(
    rank_ant.rename(columns={"PESO_TON": "PESO_ANT", "LUGAR": "LUGAR_ANT"}), on="CLIENTE", how="left",
)
rank["PESO_ANT"] = rank["PESO_ANT"].fillna(0)
total_act = rank_act["PESO_TON"].sum()
total_ant = rank_ant["PESO_TON"].sum()

st.caption(f"{etq_act} contra {etq_ant}.")

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
top10_act = rank_act.head(10)["PESO_TON"].sum() / total_act * 100
top10_ant = rank_ant.head(10)["PESO_TON"].sum() / total_ant * 100 if total_ant else None
nuevos = rank_act[~rank_act["CLIENTE"].isin(rank_ant["CLIENTE"])]
perdidos = rank_ant[~rank_ant["CLIENTE"].isin(rank_act["CLIENTE"])]

render_kpi_row([
    {"label": "Toneladas", "value": round(total_act), "suffix": " t",
     "delta": (total_act / total_ant - 1) * 100 if total_ant else None, "delta_label": "vs año anterior"},
    {"label": "Clientes que compraron", "value": len(rank_act),
     "delta": (len(rank_act) / len(rank_ant) - 1) * 100 if len(rank_ant) else None, "delta_label": "vs año anterior"},
    {"label": "Peso del Top 10", "value": round(top10_act, 1), "suffix": "%",
     "delta": None if top10_ant is None else f"{top10_act - top10_ant:+.1f} pp vs año anterior",
     "help_text": "Qué parte de las toneladas compraron los 10 primeros clientes."},
    {"label": "Nuevos / perdidos", "value": f"{len(nuevos)} / {len(perdidos)}",
     "help_text": "Nuevos: compraron ahora y no en el mismo periodo del año anterior. Perdidos: al revés."},
])

# ---------------------------------------------------------------------------
# Power Rank
# ---------------------------------------------------------------------------
seccion_titulo("Power Rank", "Mov.: lugares que subió o bajó contra el mismo periodo del año anterior")

hace_12 = corte - pd.DateOffset(months=11)
meses_12 = pd.date_range(hace_12, corte, freq="MS")
ult12 = (
    serie[(serie["PERIODO"] >= hace_12) & (serie["PERIODO"] <= corte)
          & serie["CLIENTE"].isin(rank.head(top_n)["CLIENTE"])]
    .pivot_table(index="CLIENTE", columns="PERIODO", values="PESO_TON", aggfunc="sum")
    .reindex(columns=meses_12).fillna(0)
)
sparks = {c: _sparkline(fila.tolist()) for c, fila in ult12.iterrows()}

st.html(_tabla_power_rank(rank, total_act, sparks, top_n))

# ---------------------------------------------------------------------------
# Quién empujó el cambio + concentración
# ---------------------------------------------------------------------------
seccion_titulo("Quién movió el volumen", f"Cambio en toneladas: {etq_act} vs. {etq_ant}")

cambio = rank_act.merge(rank_ant, on="CLIENTE", how="outer", suffixes=("_act", "_ant")).fillna(0)
cambio = cambio.rename(columns={"PESO_TON_act": "actual", "PESO_TON_ant": "anterior"})
cambio["delta"] = cambio["actual"] - cambio["anterior"]
cambio["cliente"] = cambio["CLIENTE"].map(lambda c: _corto(c, 34))
movers = pd.concat([
    cambio[cambio["delta"] > 0].nlargest(8, "delta"),
    cambio[cambio["delta"] < 0].nsmallest(8, "delta"),
])

col_m, col_c = st.columns([1.15, 1])
with col_m:
    st.plotly_chart(
        barras_divergentes(movers, x="delta", y="cliente", titulo="Los 8 que más crecieron y los 8 que más cayeron"),
        width="stretch",
    )
    neto = total_act - total_ant
    st.caption(f"Cambio total: {'+' if neto >= 0 else '−'}{abs(neto):,.0f} t.")

with col_c:
    # Concentración por año calendario: cada año con su propio ranking.
    anual = serie.assign(ANIO=serie["PERIODO"].dt.year).groupby(["ANIO", "CLIENTE"], as_index=False)["PESO_TON"].sum()
    anual["LUGAR"] = anual.groupby("ANIO")["PESO_TON"].rank(ascending=False, method="first")
    anual["GRUPO"] = pd.cut(anual["LUGAR"], [0, 5, 10, 20, float("inf")],
                            labels=["Top 5", "Lugares 6–10", "Lugares 11–20", "Otros"]).astype(str)
    ultimo_anio = int(serie["PERIODO"].max().year)
    mes_max = int(serie[serie["PERIODO"].dt.year == ultimo_anio]["PERIODO"].max().month)
    anual["FILA"] = anual["ANIO"].map(
        lambda a: f"{a} (a {_MESES[mes_max].lower()})" if a == ultimo_anio and mes_max < 12 else str(a)
    )
    anios = sorted(anual["ANIO"].unique())[-6:]
    # Ordenado por lugar para que los grupos se apilen Top 5 → Otros.
    anual = anual[anual["ANIO"].isin(anios)].sort_values(["ANIO", "LUGAR"])
    orden_filas = [anual.loc[anual["ANIO"] == a, "FILA"].iloc[0] for a in reversed(anios)]
    st.plotly_chart(
        estructura_100(anual, fila="FILA", categoria="GRUPO", valor="PESO_TON",
                       titulo="Qué tan concentrada está la venta", orden_filas=orden_filas, height=330),
        width="stretch",
    )
    st.caption("Parte de las toneladas de cada año que compraron los primeros lugares de ese año.")

# ---------------------------------------------------------------------------
# Trayectoria de lugares
# ---------------------------------------------------------------------------
seccion_titulo("Cómo han cambiado de lugar", "Lugar de cada cliente por año (los primeros 10 de hoy)")

top10_hoy = rank_act.head(10)["CLIENTE"].tolist()
tray = anual[anual["CLIENTE"].isin(top10_hoy)].copy()
tray = tray[tray["LUGAR"] <= 30]
tray["cliente"] = tray["CLIENTE"].map(lambda c: _corto(c, 30))
c_sel, _ = st.columns([1.3, 3])
with c_sel:
    resaltar = st.selectbox("Resaltar cliente", top10_hoy, format_func=lambda c: _corto(c, 40), key="pr_resaltar")
st.plotly_chart(
    trayectoria_ranking(tray, x="FILA", entidad="cliente", rank="LUGAR", resaltar=_corto(resaltar, 30),
                        titulo="Lugar en el ranking anual (solo se muestran lugares 1 a 30)"),
    width="stretch",
)
fila_final = tray.loc[tray["ANIO"] == tray["ANIO"].max(), "FILA"].iloc[0] if not tray.empty else ""
sin_final = sorted(set(tray["CLIENTE"]) - set(tray.loc[tray["FILA"] == fila_final, "CLIENTE"]))
if sin_final:
    st.caption(f"Sin lugar en {fila_final} (no compraron o quedaron fuera del top 30): "
               + ", ".join(_corto(c, 30) for c in sin_final) + ".")

# ---------------------------------------------------------------------------
# Ganados / perdidos
# ---------------------------------------------------------------------------
col_n, col_p = st.columns(2)
with col_n:
    st.html(_lista_clientes(
        f"Clientes nuevos ({len(nuevos)})", f"Compraron en {etq_act} y no en {etq_ant}",
        nuevos.head(10), "PESO_TON", _TXT_SUBE,
    ))
with col_p:
    st.html(_lista_clientes(
        f"Clientes que dejaron de comprar ({len(perdidos)})",
        f"Compraron en {etq_ant} y no en {etq_act} — lo que compraban entonces",
        perdidos.head(10), "PESO_TON", _TXT_BAJA,
    ))

st.caption(f"Aceros Planos Negros · Power Rank de Clientes · datos hasta {_mes_txt(serie['PERIODO'].max())}")
