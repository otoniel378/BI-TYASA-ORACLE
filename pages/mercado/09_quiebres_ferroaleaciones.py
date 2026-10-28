"""
pages/mercado/09_quiebres_ferroaleaciones.py — Monitor de quiebres de ferroaleaciones

Una ferroaleación a la vez: precio normalizado (mercado_fastmarkets/loaders.py::
FERROALEACIONES), rango normal sombreado de cada régimen, quiebres detectados y
validados estadísticamente (mercado_noticias/analytics/rupturas.py) y su vínculo
con los eventos curados de GOLD_EVENTOS_HISTORICOS (scripts/seed_eventos_historicos.py).
Un clic en un quiebre de la gráfica abre su detalle; para quiebres recientes se
agrega contexto de las noticias clasificadas del sistema.
"""

import os
import re
import sys
import urllib.parse

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config import COLORS, COLOR_SEQUENCE

from mercado_fastmarkets.alerta_alzas import AMARILLO, UMBRAL_ALZA
from mercado_fastmarkets.loaders import FERROALEACIONES, load_ferroaleaciones, load_semaforo_ferros
from mercado_noticias.loaders import load_eventos_todos, load_mercado_mensual, load_noticias_periodo
from mercado_noticias.analytics.rupturas import (
    HORIZONTES_MESES, TIPOS_IMPACTO, agregar_desempeno_posterior, bandas_normales, detectar_rupturas,
    huella_impacto, normalizar_mensual, quiebre_en_formacion, rupturas_a_dataframe, tipo_impacto_noticias,
    vincular_eventos,
)
from core.components.kpi_cards import render_kpi_row, seccion_titulo

# Las noticias clasificadas del sistema empiezan en nov 2024; antes no hay con qué cruzar.
INICIO_NOTICIAS = pd.Timestamp("2024-11-01")
DIAS_CONTEXTO = 45
# Búsqueda en Google del periodo de un quiebre: metal base en inglés y búsqueda
# web con rango de fechas (con "ferromolybdenum price" y el filtro de noticias
# Google no devolvía nada para 2014).
TERMINO_GOOGLE = {
    "FerroManganeso": "manganese", "SilicoManganeso": "manganese", "FerroSilicio": "ferrosilicon",
    "FerroCromo": "ferrochrome", "FerroVanadio": "vanadium", "FerroMolibdeno": "molybdenum",
    "FerroTitanio": "titanium", "FerroNiobio": "niobium", "Niquel": "nickel",
}
# Palabras en el título que ligan una noticia de ferroaleaciones con una serie en particular
PATRON_SERIE = {
    "FerroManganeso": r"mangan", "SilicoManganeso": r"silico|mangan", "FerroSilicio": r"silic",
    "FerroCromo": r"chrom|cromo", "FerroVanadio": r"vanad", "FerroMolibdeno": r"molyb|molib",
    "FerroTitanio": r"titan", "FerroNiobio": r"niob", "Niquel": r"nickel|n[ií]quel",
}
PATRON_GENERAL = r"ferroalloy|ferro-alloy|ferroaleac"
DIAS_NOTICIAS_RECIENTES = 60
COLOR_SERIE = {nombre: COLOR_SEQUENCE[i] for i, (nombre, _) in enumerate(FERROALEACIONES.values())}
DESCRIPCION_SERIE = dict(FERROALEACIONES.values())
EVIDENCIAS = ["Fuerte", "Moderada", "Débil"]
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _mes(fecha) -> str:
    f = pd.Timestamp(fecha)
    return f"{_MESES[f.month - 1]} {f.year}"


def _url_en(texto: str | None) -> str | None:
    m = re.search(r"https?://\S+", texto or "")
    return m.group(0) if m else None


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


@st.cache_data(ttl=3600, show_spinner="Detectando quiebres...")
def _calcular_todo(desde_anio: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(precios mensuales de todas las series, quiebres de todas las series con
    evento vinculado y desempeño posterior). Se calculan todas a la vez porque
    el tipo de impacto cuenta cuántas aleaciones quebraron al mismo tiempo."""
    crudo = load_ferroaleaciones()
    if crudo.empty:
        return pd.DataFrame(), pd.DataFrame()
    desde = pd.Timestamp(f"{desde_anio}-01-01")
    ancho = normalizar_mensual(crudo)
    ancho = ancho[ancho.index >= desde]
    todas = []
    for s in ancho.columns:
        todas += detectar_rupturas(ancho[s], s)
    rupturas = vincular_eventos(rupturas_a_dataframe(todas), load_eventos_todos())
    rupturas = huella_impacto(rupturas, load_mercado_mensual())
    return ancho, agregar_desempeno_posterior(rupturas, ancho)


def _noticias_por_tipo(serie: str, desde, hasta) -> pd.DataFrame:
    """Noticias del periodo con tipo de impacto; 'de_serie' marca las que
    mencionan esta ferroaleación."""
    noticias = tipo_impacto_noticias(load_noticias_periodo(desde, hasta))
    if noticias.empty:
        return noticias
    patron = f"{PATRON_SERIE.get(serie, serie)}|{PATRON_GENERAL}"
    noticias = noticias.assign(de_serie=noticias["titulo"].str.contains(patron, case=False, regex=True, na=False))
    return noticias[noticias["tipo_impacto"].notna() | noticias["de_serie"]]


def _pestanas_noticias(noticias: pd.DataFrame, serie: str) -> None:
    """Una pestaña por tipo de impacto con noticias, más una de la propia serie."""
    grupos = [(f"De {serie}", noticias[noticias["de_serie"]])]
    grupos += [(t, noticias[noticias["tipo_impacto"] == t]) for t in TIPOS_IMPACTO]
    grupos = [(nombre, g) for nombre, g in grupos if not g.empty]
    for (nombre, g), tab in zip(grupos, st.tabs([f"{nombre} ({len(g)})" for nombre, g in grupos])):
        with tab:
            _tabla_noticias(g)


def _cambios_desde(precio: pd.Series, fecha) -> dict:
    """Cambio % del precio desde <fecha> a +3, +6 y +12 meses (NaN si aún no pasa)."""
    base = precio.get(fecha)
    out = {}
    for h in HORIZONTES_MESES:
        fut = precio.get(pd.Timestamp(fecha) + pd.DateOffset(months=h))
        out[h] = (fut / base - 1) * 100 if pd.notna(base) and pd.notna(fut) and base else float("nan")
    return out


def _pct(v) -> str:
    return f"{v:+.0f}%" if pd.notna(v) else "—"


def _tabla_noticias(noticias: pd.DataFrame, n: int = 15) -> None:
    st.dataframe(
        noticias.head(n).assign(Fecha=lambda d: d["fecha_pub"].dt.strftime("%Y-%m-%d"))[
            ["Fecha", "titulo", "razon", "fuente", "url"]],
        hide_index=True, width="stretch",
        column_config={
            "titulo": "Noticia", "razon": "Impacto para TYASA", "fuente": "Fuente",
            "url": st.column_config.LinkColumn("Liga", display_text="Abrir"),
        },
    )


def _html_historia_serie(rupturas_serie: pd.DataFrame, q: pd.Series, serie: str) -> str:
    """Tarjeta: qué hizo el precio de ESTA ferroaleación las otras veces que
    entró al mismo régimen (Alza, Baja o Estable), medido desde que cada quiebre
    se confirmó (6 meses después), que es cuando se habría sabido."""
    nuevo = q["regimen"].split(" → ")[-1]
    casos = rupturas_serie[(rupturas_serie["regimen"].str.split(" → ").str[-1] == nuevo)
                           & (rupturas_serie["fecha"] != q["fecha"])].sort_values("fecha")
    caja = (f"<div style='font-size:13px;line-height:1.5;color:{COLORS['text']};background:{COLORS['surface']};"
            f"border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'>"
            f"<div style='font-weight:700;color:{COLORS['primary']};'>Otras veces que {serie} pasó a {nuevo}</div>")
    if casos.empty:
        return (f"{caja}<div style='color:{COLORS['text_light']};margin-top:4px;'>"
                f"No había pasado desde {desde_anio}: no hay historia propia con qué comparar.</div></div>")

    def celda(v):
        if pd.isna(v):
            return f"<td style='padding:3px 8px;color:{COLORS['text_light']};text-align:right;'>—</td>"
        c = COLORS["danger"] if v > 0 else COLORS["success"]
        return f"<td style='padding:3px 8px;font-weight:600;color:{c};text-align:right;'>{v:+.0f}%</td>"

    cab = (f"<tr style='color:{COLORS['text_light']};font-size:11px;'><td style='padding:3px 8px 3px 0;'>Quiebre</td>"
           + "".join(f"<td style='padding:3px 8px;text-align:right;'>{h} meses</td>" for h in HORIZONTES_MESES)
           + "</tr>")
    filas = "".join(
        f"<tr><td style='padding:3px 8px 3px 0;'>{_mes(r['fecha'])} · {r['regimen']}</td>"
        + "".join(celda(r[f"despues_{h}m"]) for h in HORIZONTES_MESES) + "</tr>"
        for _, r in casos.iterrows()
    )
    v12 = casos["despues_12m"].dropna()
    resumen = (f"<div style='margin-top:6px;'>A 12 meses subió en <b>{int((v12 > 0).sum())} de {len(v12)}</b> "
               f"(mediana {v12.median():+.0f}%)</div>" if len(v12) else "")
    return (f"{caja}<div style='font-size:11px;color:{COLORS['text_light']};margin-bottom:6px;'>"
            f"Cambio del precio desde que cada quiebre se confirmó (6 meses después)</div>"
            f"<table style='font-size:13px;border-collapse:collapse;'>{cab}{filas}</table>{resumen}</div>")


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------
seccion_titulo("Quiebres en ferroaleaciones", "Cambios de régimen en el precio y qué los provocó")

nombres = [n for n, _ in FERROALEACIONES.values()]
c1, c2, c3 = st.columns([2, 1, 2])
with c1:
    serie = st.selectbox("Ferroaleación", nombres, key="qf_serie")
with c2:
    desde_anio = st.selectbox("Desde", [2000, 2005, 2010, 2015, 2020], index=0, key="qf_desde")
with c3:
    evid_sel = st.multiselect("Evidencia estadística", EVIDENCIAS, default=["Fuerte", "Moderada"], key="qf_evid")

precios, rupturas_todas = _calcular_todo(desde_anio)
if precios.empty or serie not in precios.columns or precios[serie].dropna().empty:
    st.warning("Sin precios de esta ferroaleación en Oracle.")
    st.stop()
bandas = bandas_normales(precios[serie].dropna())
rupturas = (rupturas_todas[rupturas_todas["serie"] == serie].reset_index(drop=True)
            if not rupturas_todas.empty else rupturas_todas)

vista = (rupturas[rupturas["evidencia"].isin(evid_sel)].sort_values("fecha", ascending=False).reset_index(drop=True)
         if not rupturas.empty else rupturas)
ultimo = bandas.iloc[-1]
formacion = quiebre_en_formacion(precios[serie])
tend_actual = rupturas.sort_values("fecha").iloc[-1]["tendencia_post_anual"] if not rupturas.empty else None
fuera_12m = int(bandas["fuera"].iloc[-12:].sum())

render_kpi_row([
    {"label": "Quiebres", "value": len(vista)},
    {"label": "Explicados por evento", "value": int(vista["evento_id"].notna().sum()) if not vista.empty else 0},
    {"label": "Tendencia actual", "value": f"{tend_actual:+.0f}% anual" if tend_actual is not None else "—",
     "help_text": "Ritmo al que se mueve el precio en el régimen actual"},
    {"label": "Meses fuera de lo normal", "value": f"{fuera_12m} de 12",
     "help_text": "Últimos 12 meses con el precio fuera de la banda sombreada"},
])

# ---------------------------------------------------------------------------
# Semáforo de alza (scripts/update_semaforo_ferros.py)
# ---------------------------------------------------------------------------
sem_prob, sem_met = load_semaforo_ferros()
COLOR_SEMAFORO = {"Verde": COLORS["success"], "Amarillo": COLORS["warning"], "Rojo": COLORS["danger"]}
confiable = (dict(zip(sem_met["serie"], sem_met["confiable"].astype(int).astype(bool)))
             if not sem_met.empty else {})
NIVEL_SEMAFORO = {"Verde": "Riesgo bajo", "Amarillo": "Riesgo elevado", "Rojo": "Riesgo alto"}
if not sem_prob.empty:
    sem_actual = sem_prob[sem_prob["tipo"] == "actual"].set_index("serie")
    # Qué tan seguido subió de verdad en los meses de cada color (9 series, fuera de muestra)
    bt = sem_prob[(sem_prob["tipo"] == "backtest") & sem_prob["y"].notna() & sem_prob["semaforo"].notna()]
    frecuencia = bt.groupby("semaforo")["y"].mean().to_dict()
    seccion_titulo("Semáforo de alza", f"Riesgo de que el precio suba más de {UMBRAL_ALZA:.0%} en los próximos "
                                       f"3 meses · datos al {_mes(sem_actual['fecha'].max())}")
    chips = []
    for nombre in nombres:
        if nombre not in sem_actual.index:
            continue
        r = sem_actual.loc[nombre]
        c = COLOR_SEMAFORO.get(r["semaforo"], COLORS["neutral"])
        debil = not confiable.get(nombre, False)
        borde = f"2px solid {COLORS['primary']}" if nombre == serie else "1px solid #E5E7EB"
        nota_debil = (f"<div style='font-size:10px;color:{COLORS['text_light']};'>señal débil</div>"
                      if debil else "")
        chips.append(
            f"<div style='border:{borde};border-radius:8px;padding:8px 10px;background:{COLORS['surface']};"
            f"min-width:120px;opacity:{0.6 if debil else 1};'>"
            f"<div style='font-size:11px;color:{COLORS['text_light']};'>{nombre}</div>"
            f"<div style='display:flex;align-items:center;gap:6px;margin-top:2px;'>"
            f"<span style='width:12px;height:12px;border-radius:50%;background:{c};display:inline-block;'></span>"
            f"<span style='font-size:13px;font-weight:700;color:{c};'>{NIVEL_SEMAFORO.get(r['semaforo'], '—')}</span>"
            f"</div>{nota_debil}</div>"
        )
    st.html(f"<div style='display:flex;flex-wrap:wrap;gap:8px;'>{''.join(chips)}</div>")
    if frecuencia:
        partes = " · ".join(f"{NIVEL_SEMAFORO[k]}: subió en {frecuencia[k]:.0%} de los casos"
                            for k in ("Verde", "Amarillo", "Rojo") if k in frecuencia)
        st.caption(f"Desde 2008, cuando el semáforo estuvo así, el precio subió más de {UMBRAL_ALZA:.0%} en 3 meses: "
                   f"{partes} (un mes cualquiera: {bt['y'].mean():.0%}) · Rojo = el modelo ve riesgo y el precio ya "
                   f"está arriba de su rango normal · Señal débil: el modelo no ha demostrado acierto en esa serie")

# ---------------------------------------------------------------------------
# Gráfica interactiva
# ---------------------------------------------------------------------------
color = COLOR_SERIE[serie]
fig = go.Figure()
fig.add_trace(go.Scatter(x=bandas.index, y=bandas["banda_sup"], mode="lines", line=dict(width=0),
                         showlegend=False, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=bandas.index, y=bandas["banda_inf"], mode="lines", line=dict(width=0),
                         fill="tonexty", fillcolor=_hex_rgba(color, 0.18), hoverinfo="skip", name="Rango normal"))
fig.add_trace(go.Scatter(
    x=bandas.index, y=bandas["precio"], name="Precio", mode="lines", line=dict(color=color, width=2),
    customdata=bandas[["banda_inf", "banda_sup"]].values,
    hovertemplate="%{x|%b %Y}: %{y:,.2f}<br>Normal: %{customdata[0]:,.2f} – %{customdata[1]:,.2f}<extra></extra>",
))
fuera = bandas[bandas["fuera"]]
fig.add_trace(go.Scatter(
    x=fuera.index, y=fuera["precio"], name="Fuera de lo normal", mode="markers",
    marker=dict(size=6, color=COLORS["warning"]), hovertemplate="Fuera de lo normal · %{x|%b %Y}<extra></extra>",
))
if not vista.empty:
    y_q = bandas["precio"].reindex(vista["fecha"]).values
    for _, q in vista.iterrows():
        fig.add_vline(x=q["fecha"], line=dict(color=COLORS["neutral"], dash="dot", width=1))
    fig.add_trace(go.Scatter(
        x=vista["fecha"], y=y_q, name="Quiebre", mode="markers",
        marker=dict(
            size=14, line=dict(width=1.5, color="white"),
            color=[COLORS["danger"] if d == "Sube" else COLORS["success"] for d in vista["direccion"]],
            symbol=["star" if e else "diamond" for e in vista["evento_id"].notna()],
        ),
        customdata=pd.DataFrame({
            "i": vista.index, "regimen": vista["regimen"], "evidencia": vista["evidencia"],
            "evento": vista["evento_nombre"].fillna("Sin evento verificado"),
        }).values,
        hovertemplate=("<b>Quiebre · %{x|%b %Y}</b><br>%{customdata[1]}<br>Evidencia: %{customdata[2]}"
                       "<br>%{customdata[3]}<br><i>Clic para ver detalle</i><extra></extra>"),
    ))
if formacion:
    fig.add_vline(x=formacion["desde"], line=dict(color=COLORS["warning"], dash="dash", width=1.5))
    fig.add_trace(go.Scatter(
        x=[formacion["desde"]], y=[bandas["precio"].get(formacion["desde"])], name="Quiebre en formación",
        mode="markers", marker=dict(size=15, symbol="diamond-open", color=COLORS["warning"], line=dict(width=3)),
        hovertemplate=(f"<b>Posible quiebre en formación · %{{x|%b %Y}}</b><br>{formacion['regimen']}<br>"
                       f"Se confirma o descarta en {formacion['meses_para_confirmar']} mes(es)<extra></extra>"),
    ))
fig.update_layout(
    paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
    font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
    margin=dict(l=40, r=20, t=105, b=20), height=560, hovermode="closest", clickmode="event+select",
    yaxis=dict(gridcolor="#E5E7EB", title="USD/t"),
    xaxis=dict(
        showgrid=False, rangeslider=dict(visible=True, thickness=0.06),
        rangeselector=dict(buttons=[
            dict(count=2, label="2A", step="year", stepmode="backward"),
            dict(count=5, label="5A", step="year", stepmode="backward"),
            dict(count=10, label="10A", step="year", stepmode="backward"),
            dict(step="all", label="Todo"),
        ]),
    ),
    legend=dict(orientation="h", y=1.2, x=1, xanchor="right"),
    title=dict(text=f"{serie}: precio, rango normal y quiebres<br><span style='font-size:11px;color:{COLORS['text_light']}'>"
                    f"{DESCRIPCION_SERIE[serie]} · precio medio (Mid)</span>",
               font=dict(size=14, color=COLORS["primary"]), x=0, y=0.98, yanchor="top"),
    # Escala normal / logarítmica en el navegador (sin rerun): en log las subidas y
    # bajadas se ven proporcionales y la sombra ancha después de un pico se aplana.
    updatemenus=[dict(
        type="buttons", direction="right", x=0.24, xanchor="left", y=1.0, yanchor="bottom",
        pad=dict(t=0, b=4), showactive=True, active=0,
        bgcolor=COLORS["surface"], bordercolor="#E5E7EB", font=dict(size=11),
        buttons=[
            dict(label="Escala normal", method="relayout", args=[{"yaxis.type": "linear"}]),
            dict(label="Escala log", method="relayout", args=[{"yaxis.type": "log"}]),
        ],
    )],
)
evento_grafica = st.plotly_chart(fig, width="stretch", key="qf_chart", on_select="rerun", selection_mode="points")
st.caption("Sombra: rango normal según el año anterior · Naranja: precio fuera de lo normal · "
           "Rombo/estrella: quiebre, cuando cambia la tendencia o la volatilidad; puede pasar dentro del rango "
           "(estrella = explicado por un evento) · Rombo hueco: posible quiebre en formación · "
           "Clic en un quiebre para ver su detalle")

# ---------------------------------------------------------------------------
# Situación actual
# ---------------------------------------------------------------------------
seccion_titulo("Situación actual", f"Datos al {_mes(bandas.index[-1])}")
if formacion:
    st.html(
        f"<div style='border-left:3px solid {COLORS['warning']};background:#FFF8EE;padding:10px 14px;"
        f"border-radius:0 8px 8px 0;font-size:13px;line-height:1.6;margin-bottom:10px;'>"
        f"<b>Posible quiebre en formación desde {_mes(formacion['desde'])}:</b> {formacion['regimen']} · "
        f"tendencia {formacion['tendencia_pre_anual']:+.0f}% → {formacion['tendencia_post_anual']:+.0f}% anual · "
        f"volatilidad {formacion['vol_pre_anual']:.0f}% → {formacion['vol_post_anual']:.0f}% anual. "
        f"Lleva {formacion['meses']} meses; se confirma o descarta en {formacion['meses_para_confirmar']} mes(es)."
        f"<div style='font-size:11px;color:{COLORS['text_light']};'>Probado 2004–2026: adelanta la detección de "
        f"7 a 3 meses en promedio · un aviso falso cada 2 años por ferroaleación</div></div>"
    )
col_s, col_c = st.columns([1, 1])
if not rupturas.empty:
    actual = rupturas.sort_values("fecha").iloc[-1]
    estado_mes = ("fuera de lo normal" if bandas["fuera"].iloc[-1] else "dentro de lo normal")
    with col_s:
        st.html(
            f"<div style='font-size:13px;line-height:1.7;color:{COLORS['text']};background:{COLORS['surface']};"
            f"border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'>"
            f"<div><b>Régimen actual:</b> {actual['regimen'].split(' → ')[-1]} "
            f"({actual['tendencia_post_anual']:+.0f}% anual), desde {_mes(actual['fecha'])}</div>"
            f"<div><b>Último quiebre confirmado:</b> {actual['regimen']} · evidencia {actual['evidencia'].lower()}</div>"
            f"<div><b>Último mes:</b> {estado_mes}</div>"
            f"<div><b>Causa:</b> {actual['evento_nombre'] or 'sin evento verificado'}</div></div>"
        )
    with col_c:
        st.html(_html_historia_serie(rupturas, actual, serie))
else:
    st.info("Sin quiebres detectados en este periodo.")

# ---------------------------------------------------------------------------
# Alarma de la serie: cómo le ha ido al semáforo (walk-forward desde 2008)
# ---------------------------------------------------------------------------
hist = sem_prob[(sem_prob["serie"] == serie) & (sem_prob["tipo"] == "backtest")].sort_values("fecha") \
    if not sem_prob.empty else pd.DataFrame()
m = sem_met[sem_met["serie"] == serie] if not sem_met.empty else pd.DataFrame()
if not hist.empty and not m.empty:
    m = m.iloc[0]
    hist = hist.assign(
        alerta=hist["semaforo"] != "Verde",
        # Mismo criterio que alerta_alzas.metricas: acierta si hay alza en ese mes o los 2 siguientes
        alza_cerca=hist["y"][::-1].rolling(3, min_periods=1).max()[::-1] == 1,
    )
    debil = "" if confiable.get(serie, False) else " · señal débil: tómalo solo como referencia"
    seccion_titulo(f"Alarma de {serie}", f"Cómo ha avisado desde 2008 · cada año se calculó solo con "
                                         f"información anterior{debil}")
    aciertan = float(m["aciertan"]) if pd.notna(m["aciertan"]) else 0.0
    render_kpi_row([
        {"label": f"Alzas de +{UMBRAL_ALZA:.0%} en 3 meses", "value": int(m["episodios"]), "help_text": "Desde 2008"},
        {"label": "Avisadas a tiempo", "value": f"{int(m['detectados'])} de {int(m['episodios'])}",
         "help_text": "Amarillo o rojo hasta 2 meses antes de que empezara el alza"},
        {"label": "Falsas alarmas al año", "value": f"{float(m['falsas_por_anio']):.1f}",
         "help_text": "Avisos sin alza en los 3 meses siguientes"},
        {"label": "Cuando avisa, acierta", "value": f"{aciertan:.0%}",
         "help_text": f"Sin aviso, la probabilidad de alza en un mes cualquiera es {float(m['prob_base']):.0%}"},
    ])
    fh = go.Figure()
    for f in hist.loc[hist["y"] == 1, "fecha"]:
        fh.add_vrect(x0=f, x1=f + pd.DateOffset(months=1), fillcolor=COLORS["danger"], opacity=0.12, line_width=0)
    fh.add_trace(go.Scatter(x=hist["fecha"], y=hist["prob"], mode="lines", name="Señal del modelo",
                            line=dict(color=COLORS["primary"], width=1.6),
                            hovertemplate="%{x|%b %Y}: %{y:.0%}<extra></extra>"))
    for nombre_av, filtro, c in (("Aviso correcto", hist["alerta"] & hist["alza_cerca"], COLORS["danger"]),
                                 ("Falsa alarma", hist["alerta"] & ~hist["alza_cerca"], COLORS["neutral"])):
        av = hist[filtro]
        fh.add_trace(go.Scatter(x=av["fecha"], y=av["prob"], mode="markers", name=nombre_av,
                                marker=dict(size=8, color=c, line=dict(width=1, color="white")),
                                hovertemplate=f"{nombre_av} · %{{x|%b %Y}}: %{{y:.0%}}<extra></extra>"))
    fh.add_hline(y=AMARILLO, line=dict(color=COLORS["warning"], dash="dash", width=1))
    fh.update_layout(
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
        font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
        margin=dict(l=40, r=20, t=30, b=30), height=300,
        legend=dict(orientation="h", y=1.12, x=1, xanchor="right"),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB", tickformat=".0%",
                                               range=[0, max(0.5, float(hist["prob"].max()) * 1.1)]),
    )
    st.plotly_chart(fh, width="stretch", key="qf_chart_semaforo")
    st.caption(f"Franjas rojas: meses en que el precio sí subió más de {UMBRAL_ALZA:.0%} en los 3 meses siguientes · "
               f"Punteada: arriba de {AMARILLO:.0%} el modelo ve riesgo elevado · Puntos: meses en amarillo o rojo")

seccion_titulo(f"Noticias que pueden mover a {serie}",
               f"Últimos {DIAS_NOTICIAS_RECIENTES} días, por tipo de impacto · noticias generales, "
               f"no necesariamente de esta ferroaleación")
recientes = _noticias_por_tipo(serie, pd.Timestamp.now() - pd.Timedelta(days=DIAS_NOTICIAS_RECIENTES),
                               pd.Timestamp.now())
if recientes.empty:
    st.caption("Sin noticias clasificadas en este periodo.")
else:
    _pestanas_noticias(recientes, serie)

if vista.empty:
    st.info("No hay quiebres con la evidencia seleccionada.")
    st.stop()

# Clic en un quiebre -> se selecciona en el detalle (solo si cambió, para no pisar el selector)
puntos = [p for p in (evento_grafica.selection.points if evento_grafica else [])
          if p.get("customdata") and len(p["customdata"]) == 4]
if puntos:
    i_click = int(puntos[0]["customdata"][0])
    if st.session_state.get("_qf_ultimo_click") != (serie, i_click):
        st.session_state["_qf_ultimo_click"] = (serie, i_click)
        st.session_state["qf_quiebre"] = i_click
if st.session_state.get("qf_quiebre") not in vista.index:
    st.session_state["qf_quiebre"] = 0

# ---------------------------------------------------------------------------
# Detalle del quiebre
# ---------------------------------------------------------------------------
seccion_titulo("Detalle del quiebre", "Elige uno aquí o haz clic en la gráfica")
etiquetas = {i: f"{_mes(r.fecha)} · {r.regimen} · evidencia {r.evidencia.lower()}" + (" · ★" if r.evento_id else "")
             for i, r in vista.iterrows()}
i_sel = st.selectbox("Quiebre", list(etiquetas), format_func=etiquetas.get, key="qf_quiebre")
q = vista.loc[i_sel]

col_d, col_e = st.columns([1, 1])
with col_d:
    p_chow = f"{q['p_chow']:.4f}" if pd.notna(q["p_chow"]) else "no aplica (tramo corto)"
    cambios = _cambios_desde(precios[serie], q["fecha"])
    cambio = " · ".join(f"{h} meses {_pct(v)}" for h, v in cambios.items())
    st.html(
        f"<div style='font-size:13px;line-height:1.7;color:{COLORS['text']};background:{COLORS['surface']};"
        f"border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'>"
        f"<div style='font-weight:700;color:{COLORS['primary']};margin-bottom:4px;'>"
        f"{serie} · {_mes(q['fecha'])} · {q['regimen']}</div>"
        f"<div><b>Tendencia:</b> {q['tendencia_pre_anual']:+.0f}% → {q['tendencia_post_anual']:+.0f}% anual "
        f"<span style='color:{COLORS['text_light']};'>(p = {q['p_tendencia']:.4f})</span></div>"
        f"<div><b>Volatilidad:</b> {q['vol_pre_anual']:.0f}% → {q['vol_post_anual']:.0f}% anual "
        f"<span style='color:{COLORS['text_light']};'>(p = {q['p_volatilidad']:.4f})</span></div>"
        f"<div><b>Cambio estructural (Chow):</b> p = {p_chow}</div>"
        f"<div><b>Precio después del quiebre:</b> {cambio}</div>"
        f"<div><b>Evidencia:</b> {q['evidencia']} · régimen anterior {q['meses_pre']} meses, nuevo {q['meses_post']}</div>"
        f"<div style='margin-top:6px;'><b>Tipo de impacto:</b> {q['tipo_impacto']} "
        f"<span style='color:{COLORS['text_light']};'>"
        f"({'según el evento verificado' if q['tipo_fuente'] == 'evento verificado' else 'probable, según el mercado'})</span></div>"
        f"<div><b>Qué pasaba en el mercado (±2 meses):</b> {q['senales_mercado']}</div>"
        f"</div>"
    )
    st.html("<div style='height:10px'></div>" + _html_historia_serie(rupturas, q, serie))
with col_e:
    if q["evento_id"]:
        url = _url_en(q["evento_fuente"])
        fuente = (f"<a href='{url}' target='_blank' style='color:{COLORS['secondary']};'>Fuente</a>"
                  if url else (q["evento_fuente"] or ""))
        st.html(
            f"<div style='border-left:3px solid {COLORS['primary']};background:#F3F6FA;"
            f"padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;line-height:1.5;'>"
            f"<div style='font-weight:700;color:{COLORS['primary']};'>{q['evento_nombre']}</div>"
            f"<div style='margin-top:4px;'>{q['evento_descripcion']}</div>"
            f"<div style='margin-top:6px;font-size:11px;'>{fuente}</div></div>"
        )
    else:
        st.html(
            f"<div style='border-left:3px solid {COLORS['warning']};background:#FFF8EE;"
            f"padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;'>"
            f"Sin evento verificado en el catálogo para esta fecha.</div>"
        )
    antes, despues = q["fecha"] - pd.DateOffset(months=4), q["fecha"] + pd.DateOffset(months=3)
    gnews = "https://www.google.com/search?" + urllib.parse.urlencode({
        "q": f"{TERMINO_GOOGLE.get(serie, serie)} price",
        "tbs": f"cdr:1,cd_min:{antes.month}/{antes.day}/{antes.year},cd_max:{despues.month}/{despues.day}/{despues.year}",
    })
    st.html(f"<div style='margin-top:8px;font-size:12px;'>"
            f"<a href='{gnews}' target='_blank' style='color:{COLORS['secondary']};'>"
            f"Buscar noticias de ese periodo</a></div>")

if q["fecha"] >= INICIO_NOTICIAS:
    desde_n, hasta_n = q["fecha"] - pd.Timedelta(days=DIAS_CONTEXTO), q["fecha"] + pd.Timedelta(days=DIAS_CONTEXTO)
    periodo = _noticias_por_tipo(serie, desde_n, hasta_n)
    seccion_titulo("Noticias del periodo", f"±{DIAS_CONTEXTO} días del quiebre, por tipo de impacto · "
                                           f"contexto, no necesariamente la causa")
    if periodo.empty:
        st.info("Sin noticias clasificadas en ese periodo.")
    else:
        _pestanas_noticias(periodo, serie)

# ---------------------------------------------------------------------------
# Todos los quiebres de la serie, en orden cronológico
# ---------------------------------------------------------------------------
seccion_titulo(f"Quiebres de {serie}", f"Desde {desde_anio} · cambio del precio desde el mes del quiebre")
cambios_q = pd.DataFrame([_cambios_desde(precios[serie], f) for f in vista["fecha"]], index=vista.index)
cronologico = vista.join(cambios_q).sort_values("fecha")
tabla = pd.DataFrame({
    "Fecha": cronologico["fecha"].map(_mes),
    "Tendencia": cronologico["regimen"],
    "Volatilidad": cronologico["volatilidad"],
    "Evidencia": cronologico["evidencia"],
    "Precio (USD/t)": bandas["precio"].reindex(cronologico["fecha"]).map(lambda v: f"{v:,.0f}").values,
    **{f"{h} meses después": cronologico[h].map(_pct) for h in HORIZONTES_MESES},
})
st.dataframe(tabla, hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Qué tipo de impactos mueven a esta ferroaleación
# ---------------------------------------------------------------------------
seccion_titulo(f"Qué tipo de impactos mueven a {serie}",
               f"Quiebres desde {desde_anio} · el tipo probable sale de lo que hacía el mercado, no prueba la causa")
resumen_tipo = (
    cronologico.groupby("tipo_impacto")
    .agg(quiebres=("serie", "size"),
         verificados=("tipo_fuente", lambda s: int((s == "evento verificado").sum())),
         alzas=("direccion", lambda s: int((s == "Sube").sum())),
         **{f"m{h}": (h, "median") for h in HORIZONTES_MESES})
    .sort_values("quiebres", ascending=False).reset_index()
)
for h in HORIZONTES_MESES:
    resumen_tipo[f"m{h}"] = resumen_tipo[f"m{h}"].map(_pct)
resumen_tipo.columns = (["Tipo de impacto", "Quiebres", "Con evento verificado", "Tendencia sube"]
                        + [f"{h} meses después (mediana)" for h in HORIZONTES_MESES])
st.dataframe(resumen_tipo, hide_index=True, width="stretch")

st.caption("Datos: Fastmarkets (AMM), LME y Yahoo Finance · Eventos: catálogo curado con fuente")
