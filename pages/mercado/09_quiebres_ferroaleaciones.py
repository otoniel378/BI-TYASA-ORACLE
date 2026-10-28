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

from mercado_fastmarkets.loaders import FERROALEACIONES, load_ferroaleaciones, load_semaforo_ferros
from mercado_noticias.loaders import (
    load_eventos_todos, load_mercado_mensual, load_noticias_en_rango, load_noticias_ferroaleaciones,
)
from mercado_noticias.analytics.rupturas import (
    MIN_SEGMENTO, agregar_desempeno_posterior, bandas_normales, detectar_rupturas, huella_impacto, normalizar_mensual,
    resumen_casos_parecidos, rupturas_a_dataframe, vincular_eventos,
)
from core.components.kpi_cards import render_kpi_row, seccion_titulo

# Las noticias clasificadas del sistema empiezan en nov 2024; antes no hay con qué cruzar.
INICIO_NOTICIAS = pd.Timestamp("2024-11-01")
DIAS_CONTEXTO = 45
CATEGORIAS_CONTEXTO = ("aranceles_comercio", "china_sobrecapacidad", "energia_electricidad",
                       "chatarra_scrap", "demanda_general", "carbon_coquizable")
TERMINO_GOOGLE = {
    "FerroManganeso": "ferromanganese", "SilicoManganeso": "silicomanganese",
    "FerroSilicio": "ferrosilicon", "FerroCromo": "ferrochrome", "FerroVanadio": "ferrovanadium",
    "FerroMolibdeno": "ferromolybdenum", "FerroTitanio": "ferrotitanium", "FerroNiobio": "ferroniobium",
    "Niquel": "LME nickel",
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
    los "casos parecidos" comparan contra las demás ferroaleaciones."""
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


def _noticias_de_serie(serie: str, desde, hasta) -> pd.DataFrame:
    noticias = load_noticias_ferroaleaciones(desde, hasta)
    if noticias.empty:
        return noticias
    patron = f"{PATRON_SERIE.get(serie, serie)}|{PATRON_GENERAL}"
    return noticias[noticias["titulo"].str.contains(patron, case=False, regex=True, na=False)]


def _tabla_noticias(noticias: pd.DataFrame, n: int = 12) -> None:
    st.dataframe(
        noticias.head(n).assign(Fecha=lambda d: d["fecha_pub"].dt.strftime("%Y-%m-%d"))[
            ["Fecha", "titulo", "razon", "fuente", "url"]],
        hide_index=True, width="stretch",
        column_config={
            "titulo": "Noticia", "razon": "Impacto para TYASA", "fuente": "Fuente",
            "url": st.column_config.LinkColumn("Liga", display_text="Abrir"),
        },
    )


def _html_casos_parecidos(resumen: pd.DataFrame, regimen: str, desde_cuando: str) -> str:
    """Tarjeta: qué hizo el precio en quiebres del mismo tipo en las demás series."""
    if resumen.empty:
        return (f"<div style='font-size:13px;color:{COLORS['text_light']};'>"
                f"Sin casos parecidos ({regimen}) con historia suficiente.</div>")
    filas = "".join(
        f"<tr><td style='padding:3px 10px 3px 0;'>{int(r.horizonte)} meses</td>"
        f"<td style='padding:3px 10px;font-weight:700;color:{COLORS['danger'] if r.mediana > 0 else COLORS['success']};'>"
        f"{r.mediana:+.0f}%</td>"
        f"<td style='padding:3px 10px;color:{COLORS['text_light']};'>{r.p25:+.0f}% a {r.p75:+.0f}%</td>"
        f"<td style='padding:3px 0 3px 10px;'>subió en {r.subieron} de {r.casos}</td></tr>"
        for r in resumen.itertuples()
    )
    return (
        f"<div style='font-size:13px;line-height:1.5;color:{COLORS['text']};background:{COLORS['surface']};"
        f"border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'>"
        f"<div style='font-weight:700;color:{COLORS['primary']};'>Qué pasó en casos parecidos ({regimen})</div>"
        f"<div style='font-size:11px;color:{COLORS['text_light']};margin-bottom:6px;'>"
        f"Cambio del precio {desde_cuando}, en las 9 series desde {desde_anio}. Mediana y rango de la mitad central.</div>"
        f"<table style='font-size:13px;border-collapse:collapse;'>{filas}</table></div>"
    )


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
if not sem_prob.empty:
    sem_actual = sem_prob[sem_prob["tipo"] == "actual"].set_index("serie")
    seccion_titulo("Semáforo de alza", f"Probabilidad de subir más de 20% en los próximos 3 meses · "
                                       f"datos al {_mes(sem_actual['fecha'].max())}")
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
            f"<span style='font-size:15px;font-weight:700;color:{COLORS['text']};'>{r['prob']:.0%}</span>"
            f"<span style='font-size:11px;color:{c};font-weight:600;'>{r['semaforo']}</span></div>"
            f"{nota_debil}</div>"
        )
    st.html(f"<div style='display:flex;flex-wrap:wrap;gap:8px;'>{''.join(chips)}</div>")
    st.caption("Verde < 20% · Amarillo 20–40% · Rojo ≥ 40% · Señal débil: el modelo no ha demostrado acierto "
               "en esa serie, tómalo solo como referencia")

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
st.caption("Sombra: rango normal según el año anterior · Naranja: fuera de lo normal · "
           "Rombo/estrella: quiebre (estrella = explicado por un evento) · Clic en un quiebre para ver su detalle")

# ---------------------------------------------------------------------------
# Situación actual
# ---------------------------------------------------------------------------
seccion_titulo("Situación actual", f"Datos al {_mes(bandas.index[-1])}")
col_s, col_c = st.columns([1, 1])
if not rupturas.empty:
    actual = rupturas.sort_values("fecha").iloc[-1]
    confirmado = actual["fecha"] + pd.DateOffset(months=MIN_SEGMENTO) <= bandas.index[-1]
    estado_mes = ("fuera de lo normal" if bandas["fuera"].iloc[-1] else "dentro de lo normal")
    with col_s:
        st.html(
            f"<div style='font-size:13px;line-height:1.7;color:{COLORS['text']};background:{COLORS['surface']};"
            f"border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'>"
            f"<div><b>Régimen actual:</b> {actual['regimen'].split(' → ')[-1]} "
            f"({actual['tendencia_post_anual']:+.0f}% anual), desde {_mes(actual['fecha'])}</div>"
            f"<div><b>Último quiebre:</b> {actual['regimen']} · evidencia {actual['evidencia'].lower()} · "
            f"{'confirmado' if confirmado else 'aún en confirmación (menos de 6 meses de datos)'}</div>"
            f"<div><b>Último mes:</b> {estado_mes}</div>"
            f"<div><b>Causa:</b> {actual['evento_nombre'] or 'sin evento verificado'}</div></div>"
        )
    with col_c:
        st.html(_html_casos_parecidos(
            resumen_casos_parecidos(rupturas_todas, actual["regimen"], excluir=(serie, actual["fecha"])),
            actual["regimen"], "desde que el quiebre se confirma (6 meses después)"))
else:
    st.info("Sin quiebres detectados en este periodo.")

hist = sem_prob[(sem_prob["serie"] == serie) & (sem_prob["tipo"] == "backtest")].sort_values("fecha") \
    if not sem_prob.empty else pd.DataFrame()
if not hist.empty:
    with st.expander(f"Cómo le ha ido al semáforo con {serie}"):
        m = sem_met[sem_met["serie"] == serie]
        if not m.empty:
            m = m.iloc[0]
            st.html(
                f"<div style='font-size:13px;line-height:1.6;color:{COLORS['text']};'>"
                f"Desde 2008 hubo <b>{int(m['episodios'])}</b> alzas de más de 20% en 3 meses; el semáforo avisó "
                f"(amarillo o rojo) a tiempo en <b>{int(m['detectados'])}</b>. Da en promedio "
                f"<b>{float(m['falsas_por_anio']):.1f}</b> falsas alarmas al año. Cuando avisa, acierta "
                f"{float(m['aciertan']) if pd.notna(m['aciertan']) else 0:.0%} de las veces, contra "
                f"{float(m['prob_base']):.0%} si no hubiera aviso. Cada año se calculó solo con información anterior."
                f"</div>"
            )
        fh = go.Figure()
        alzas = hist[hist["y"] == 1]
        for f in alzas["fecha"]:
            fh.add_vrect(x0=f, x1=f + pd.DateOffset(months=1), fillcolor=COLORS["danger"], opacity=0.15, line_width=0)
        fh.add_trace(go.Scatter(x=hist["fecha"], y=hist["prob"], mode="lines", name="Probabilidad de alza",
                                line=dict(color=COLORS["primary"], width=1.8),
                                hovertemplate="%{x|%b %Y}: %{y:.0%}<extra></extra>"))
        fh.add_hline(y=0.20, line=dict(color=COLORS["warning"], dash="dash", width=1))
        fh.add_hline(y=0.40, line=dict(color=COLORS["danger"], dash="dash", width=1))
        fh.update_layout(
            paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["background"],
            font=dict(family="Inter, Arial, sans-serif", color=COLORS["text"]),
            margin=dict(l=40, r=20, t=20, b=30), height=280, showlegend=False,
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#E5E7EB", tickformat=".0%", range=[0, 1]),
        )
        st.plotly_chart(fh, width="stretch", key="qf_chart_semaforo")
        st.caption("Línea: probabilidad que daba el modelo cada mes · Franjas rojas: meses en que el precio "
                   "sí subió más de 20% en los 3 meses siguientes · Punteadas: umbrales amarillo y rojo")

seccion_titulo(f"Noticias recientes de {serie}", f"Últimos {DIAS_NOTICIAS_RECIENTES} días")
recientes = _noticias_de_serie(serie, pd.Timestamp.now() - pd.Timedelta(days=DIAS_NOTICIAS_RECIENTES), pd.Timestamp.now())
if recientes.empty:
    st.caption("Sin noticias todavía; el proceso diario ya busca noticias de ferroaleaciones.")
else:
    _tabla_noticias(recientes, n=8)

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
    cambio = f"{q['cambio_precio_6m']:+.0f}%" if pd.notna(q["cambio_precio_6m"]) else "—"
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
        f"<div><b>Precio 6 meses después vs. 6 antes:</b> {cambio}</div>"
        f"<div><b>Evidencia:</b> {q['evidencia']} · régimen anterior {q['meses_pre']} meses, nuevo {q['meses_post']}</div>"
        f"<div style='margin-top:6px;'><b>Tipo de impacto:</b> {q['tipo_impacto']} "
        f"<span style='color:{COLORS['text_light']};'>"
        f"({'según el evento verificado' if q['tipo_fuente'] == 'evento verificado' else 'probable, según el mercado'})</span></div>"
        f"<div><b>Qué pasaba en el mercado (±2 meses):</b> {q['senales_mercado']}</div>"
        f"</div>"
    )
    st.html("<div style='height:10px'></div>" + _html_casos_parecidos(
        resumen_casos_parecidos(rupturas_todas, q["regimen"], excluir=(serie, q["fecha"])),
        q["regimen"], "desde que el quiebre se confirma (6 meses después)"))
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
    termino = TERMINO_GOOGLE.get(serie, serie)
    antes = (q["fecha"] - pd.DateOffset(months=3)).strftime("%Y-%m-%d")
    despues = (q["fecha"] + pd.DateOffset(months=1)).strftime("%Y-%m-%d")
    gnews = "https://www.google.com/search?" + urllib.parse.urlencode(
        {"q": f"{termino} price after:{antes} before:{despues}", "tbm": "nws"})
    st.html(f"<div style='margin-top:8px;font-size:12px;'>"
            f"<a href='{gnews}' target='_blank' style='color:{COLORS['secondary']};'>"
            f"Buscar noticias de ese periodo</a></div>")

if q["fecha"] >= INICIO_NOTICIAS:
    desde_n, hasta_n = q["fecha"] - pd.Timedelta(days=DIAS_CONTEXTO), q["fecha"] + pd.Timedelta(days=DIAS_CONTEXTO)
    propias = _noticias_de_serie(serie, desde_n, hasta_n)
    if not propias.empty:
        seccion_titulo(f"Noticias de {serie} en ese periodo", f"±{DIAS_CONTEXTO} días del quiebre")
        _tabla_noticias(propias)
    else:
        seccion_titulo("Noticias del periodo", f"±{DIAS_CONTEXTO} días · contexto general, no necesariamente la causa")
        generales = load_noticias_en_rango(desde_n, hasta_n, CATEGORIAS_CONTEXTO)
        if generales.empty:
            st.info("Sin noticias clasificadas en ese periodo.")
        else:
            _tabla_noticias(generales)

# ---------------------------------------------------------------------------
# Todos los quiebres de la serie
# ---------------------------------------------------------------------------
seccion_titulo(f"Quiebres de {serie}", f"Desde {desde_anio}")
tabla = vista.assign(
    Fecha=lambda d: d["fecha"].map(_mes),
    Cambio=lambda d: d["cambio_precio_6m"].map(lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"),
    Evento=lambda d: d["evento_nombre"].fillna("—"),
    Tipo=lambda d: d["tipo_impacto"] + d["tipo_fuente"].map({"evento verificado": "", "huella de mercado": " (probable)"}),
)[["Fecha", "regimen", "volatilidad", "Cambio", "evidencia", "Tipo", "Evento"]]
tabla.columns = ["Fecha", "Tendencia", "Volatilidad", "Precio 6m después vs. 6m antes", "Evidencia",
                 "Tipo de impacto", "Evento"]
st.dataframe(tabla, hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Qué tipo de impactos mueven las ferroaleaciones (todas las series)
# ---------------------------------------------------------------------------
todas_vista = rupturas_todas[rupturas_todas["evidencia"].isin(evid_sel)] if not rupturas_todas.empty else rupturas_todas
if not todas_vista.empty:
    seccion_titulo("Qué tipo de impactos mueven las ferroaleaciones",
                   f"Las 9 series desde {desde_anio} · el tipo probable sale de lo que hacía el mercado, no prueba la causa")
    resumen_tipo = (
        todas_vista.groupby("tipo_impacto")
        .agg(quiebres=("serie", "size"),
             verificados=("tipo_fuente", lambda s: int((s == "evento verificado").sum())),
             alzas=("direccion", lambda s: int((s == "Sube").sum())),
             cambio=("cambio_precio_6m", "median"),
             a12=("despues_12m", "median"))
        .sort_values("quiebres", ascending=False).reset_index()
    )
    resumen_tipo["cambio"] = resumen_tipo["cambio"].map(lambda v: f"{v:+.0f}%" if pd.notna(v) else "—")
    resumen_tipo["a12"] = resumen_tipo["a12"].map(lambda v: f"{v:+.0f}%" if pd.notna(v) else "—")
    resumen_tipo.columns = ["Tipo de impacto", "Quiebres", "Con evento verificado", "Tendencia sube",
                            "Precio 6m después vs. 6m antes (mediana)", "12 meses después de confirmarse (mediana)"]
    st.dataframe(resumen_tipo, hide_index=True, width="stretch")

st.caption("Datos: Fastmarkets (AMM), LME y Yahoo Finance · Eventos: catálogo curado con fuente")
