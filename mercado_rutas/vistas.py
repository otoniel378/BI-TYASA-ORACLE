"""
mercado_rutas/vistas.py — Piezas visuales de la página Rutas y puertos
(pages/mercado/10_rutas_puertos.py): mapa, tarjetas, tablas y detalle.

Color de estado reservado (riesgo / vigilar / normal / sin datos), siempre con
símbolo + texto (nunca solo color) y sin emojis.
"""

from html import escape

import pandas as pd
import plotly.graph_objects as go

from config import COLORS
from mercado_rutas.red import ISO3, PAISES, PASO_PAISES, PASOS, PUERTOS, TYASA

COLOR_NIVEL = {"riesgo": COLORS["danger"], "vigilar": COLORS["warning"], "normal": COLORS["success"],
               "sin datos": "#9CA3AF"}
FONDO_NIVEL = {"riesgo": "#FDECEC", "vigilar": "#FFF4E5", "normal": "#EAF5EB", "sin datos": "#F3F4F6"}
ICONO_NIVEL = {"riesgo": "▲", "vigilar": "●", "normal": "✓", "sin datos": "–"}
ETIQUETA_NIVEL = {"riesgo": "Riesgo", "vigilar": "Vigilar", "normal": "Normal", "sin datos": "Sin datos"}
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Mapa: países de origen del material, el elegido y los que bordea la ruta elegida
COLOR_ORIGEN, COLOR_ORIGEN_SEL, COLOR_PASA = "#B3C9E0", COLORS["secondary"], "#F4C766"

_FUENTE = "Inter, -apple-system, Segoe UI, Arial, sans-serif"
# Pulido común: transiciones solo de color/sombra (no "all"), hover solo con puntero fino
_CSS = (f"<style>.rp-card{{transition:box-shadow 160ms ease-out,border-color 160ms ease-out}}"
        f"@media (hover:hover) and (pointer:fine){{.rp-card:hover{{box-shadow:0 4px 14px rgba(27,58,92,.10);"
        f"border-color:{COLORS['secondary']}}}}}"
        f".rp-a{{color:{COLORS['secondary']};text-decoration:none}}.rp-a:hover{{text-decoration:underline}}</style>")
_ETIQ = (f"font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:{COLORS['text_light']};"
         f"font-weight:600;")


def fecha_corta(f) -> str:
    if f is None or pd.isna(f):
        return "—"
    f = pd.Timestamp(f)
    return f"{f.day} {_MESES[f.month - 1]} {f.year}"


def chip(nivel: str, texto: str | None = None) -> str:
    c = COLOR_NIVEL.get(nivel, COLORS["neutral"])
    return (f"<span style='display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:999px;"
            f"font-size:11.5px;font-weight:600;white-space:nowrap;background:{FONDO_NIVEL.get(nivel, '#F3F4F6')};"
            f"color:{c};'>{ICONO_NIVEL.get(nivel, '')} {escape(texto or ETIQUETA_NIVEL.get(nivel, nivel))}</span>")


def _n_noticias(n: int, g: int) -> str:
    if not n:
        return "—"
    return f"{n} ({g} grave{'s' if g != 1 else ''})" if g else str(n)


# ── Resumen ───────────────────────────────────────────────────────────────────
def tarjetas_resumen(red: pd.DataFrame, avisos: pd.DataFrame, tormentas: pd.DataFrame) -> str:
    """Cuatro tarjetas compactas: pasos, puertos, noticias graves y tormentas."""
    def cuenta(tipo):
        g = red[red["tipo"] == tipo]
        return len(g), int((g["nivel"] == "riesgo").sum()), int((g["nivel"] == "vigilar").sum())

    tp, rp, vp = cuenta("Paso marítimo")
    tq, rq, vq = cuenta("Puerto de llegada")
    # una nota que toca varios lugares (p. ej. Rusia y Ucrania) cuenta una vez
    graves = avisos.loc[avisos["severidad"] == "alta", "titulo"].nunique() if not avisos.empty else 0
    lugares_graves = avisos.loc[avisos["severidad"] == "alta", "lugar"].nunique() if not avisos.empty else 0
    torm = tormentas.sort_values("km").drop_duplicates("nombre") if not tormentas.empty else tormentas
    cerca = torm[torm["km"] <= 1000] if not torm.empty else torm

    def tarjeta(titulo, valor, detalle, nivel):
        c = COLOR_NIVEL[nivel]
        return (f"<div class='rp-card' style='flex:1 1 190px;background:{COLORS['surface']};border:1px solid #E5E7EB;"
                f"border-left:4px solid {c};border-radius:10px;padding:9px 14px;display:flex;align-items:center;"
                f"gap:12px;'>"
                f"<div style='font-size:24px;font-weight:700;color:{COLORS['text']};font-variant-numeric:tabular-nums;"
                f"line-height:1;'>{valor}</div>"
                f"<div><div style='{_ETIQ}'>{titulo}</div>"
                f"<div style='font-size:12px;color:{COLORS['text_light']};'>{detalle}</div></div></div>")

    def det(r, v, total):
        partes = [f"{r} en riesgo" if r else "", f"{v} por vigilar" if v else ""]
        return (" · ".join(p for p in partes if p) or "todo normal") + f" · de {total}"

    html = "".join([
        tarjeta("Pasos marítimos", rp + vp, det(rp, vp, tp), "riesgo" if rp else "vigilar" if vp else "normal"),
        tarjeta("Puertos de llegada", rq + vq, det(rq, vq, tq), "riesgo" if rq else "vigilar" if vq else "normal"),
        tarjeta("Noticias graves", graves,
                f"en {lugares_graves} lugar{'es' if lugares_graves != 1 else ''} · 21 días" if graves else "21 días",
                "riesgo" if graves else "normal"),
        tarjeta("Tormentas cerca", len(cerca),
                ", ".join(f"{r.nombre} a {r.km:,.0f} km de {PUERTOS[r.puerto]['nombre']}" for r in cerca.itertuples())
                or "ninguna a menos de 1,000 km", "riesgo" if len(cerca) else "normal"),
    ])
    return f"{_CSS}<div style='display:flex;flex-wrap:wrap;gap:10px;font-family:{_FUENTE};'>{html}</div>"


# ── Mapa ──────────────────────────────────────────────────────────────────────
def _hover_nodo(r) -> str:
    traf = (f"Tráfico: {r.trafico.lower()} ({r.cambio:+.0%} vs. lo normal)" if r.trafico != "Sin datos"
            else "Tráfico: sin dato")
    extra = "<br>".join(f"{ICONO_NIVEL[n]} {escape(t)}" for n, t in r.motivos) if r.motivos else "Sin alertas"
    return (f"<b>{escape(r.nombre)}</b> · {ETIQUETA_NIVEL[r.nivel]}<br>{r.tipo}<br>{traf}<br>{extra}"
            f"<br><i>Clic para ver detalle</i>")


def _capa_paises(fig: go.Figure, iso3: list[str], color: str, hover: list[str], borde: str = "white") -> None:
    if not iso3:
        return
    fig.add_trace(go.Choropleth(locations=iso3, z=[1] * len(iso3), colorscale=[[0, color], [1, color]],
                                showscale=False, marker_line_color=borde, marker_line_width=0.8,
                                hovertext=hover, hoverinfo="text"))


def mapa_red(red: pd.DataFrame, rutas: list[dict] | None = None, ruta_sel: str | None = None,
             tormentas: pd.DataFrame | None = None, nodo_sel: str | None = None,
             origenes: list[str] | None = None, iso_sel: str | None = None, altura: int = 470) -> go.Figure:
    """Mapa de la red. Si se dan <origenes> (ISO numérico del material) se
    sombrean; el país elegido y los países que bordea la ruta elegida se
    iluminan, y la ruta lleva un halo."""
    fig = go.Figure()
    rutas = rutas or []
    sel = next((r for r in rutas if r["id"] == ruta_sel), None)

    # Países: origen del material, el elegido y por donde pasa la ruta elegida
    if origenes:
        otros = [i for i in origenes if i != iso_sel and i in ISO3]
        _capa_paises(fig, [ISO3[i] for i in otros], COLOR_ORIGEN,
                     [f"<b>{PAISES[i]['nombre']}</b><br>País de origen · clic en sus botones para ver sus rutas"
                      for i in otros])
    if sel:
        pasa = {}
        for p in sel["pasos"]:
            for c in PASO_PAISES.get(p, []):
                pasa.setdefault(c, PASOS[p]["nombre"])
        pasa.setdefault("MEX", "llegada a México")
        pasa.pop(ISO3.get(sel["iso"]), None)
        _capa_paises(fig, list(pasa), COLOR_PASA, [f"<b>La ruta pasa por aquí</b><br>{escape(v)}" for v in pasa.values()])
    if iso_sel and iso_sel in ISO3:
        _capa_paises(fig, [ISO3[iso_sel]], COLOR_ORIGEN_SEL,
                     [f"<b>{PAISES[iso_sel]['nombre']}</b><br>Origen elegido · sale de {PAISES[iso_sel]['puerto']}"],
                     borde=COLORS["primary"])

    # Rutas: las demás tenues; la elegida con halo (línea ancha translúcida) y encima la línea
    for r in rutas:
        if not r["coords"] or r is sel:
            continue
        lat, lon = zip(*r["coords"])
        fig.add_trace(go.Scattergeo(lat=lat, lon=lon, mode="lines", hoverinfo="skip", showlegend=False,
                                    line=dict(width=1.1, color="#9FB3C8", dash="solid" if r["disponible"] else "dot"),
                                    opacity=0.5))
    if sel and sel["coords"]:
        lat, lon = zip(*sel["coords"])
        c = COLOR_NIVEL.get(sel.get("nivel", "normal"), COLORS["primary"])
        fig.add_trace(go.Scattergeo(lat=lat, lon=lon, mode="lines", hoverinfo="skip", showlegend=False,
                                    line=dict(width=12, color=c), opacity=0.18))
        fig.add_trace(go.Scattergeo(lat=lat, lon=lon, mode="lines", hoverinfo="skip", showlegend=False,
                                    line=dict(width=3.5, color=c)))
        if sel["puerto"]:
            p = PUERTOS[sel["puerto"]]
            fig.add_trace(go.Scattergeo(lat=[p["lat"], TYASA["lat"]], lon=[p["lon"], TYASA["lon"]], mode="lines",
                                        line=dict(width=2.5, color=COLORS["primary"], dash="dot"), hoverinfo="skip",
                                        showlegend=False))

    # Halo de los puntos que cruza la ruta elegida
    if sel:
        nodos = {f"paso:{p}" for p in sel["pasos"]} | ({f"puerto:{sel['puerto']}"} if sel["puerto"] else set())
        g = red[red["nodo"].isin(nodos)]
        if not g.empty:
            fig.add_trace(go.Scattergeo(lat=g["lat"], lon=g["lon"], mode="markers", hoverinfo="skip", showlegend=False,
                                        marker=dict(size=30, color=[COLOR_NIVEL[n] for n in g["nivel"]], opacity=0.22)))

    # Puntos de la red (encima): países con noticias, pasos y puertos
    for tipo, simbolo, tam in (("País de origen", "square", 9), ("Paso marítimo", "diamond", 13),
                               ("Puerto de llegada", "circle", 12)):
        g = red[(red["tipo"] == tipo) & red["lat"].notna()]
        if g.empty:
            continue
        fig.add_trace(go.Scattergeo(
            # Los 5 puertos mexicanos quedan muy juntos a escala mundial: sin etiqueta (va en el tooltip)
            lat=g["lat"], lon=g["lon"], mode="markers+text" if tipo == "Paso marítimo" else "markers",
            text=[PASOS[k]["corto"] if tipo == "Paso marítimo" else "" for k in g["clave"]],
            textposition="top center", textfont=dict(size=10, color=COLORS["text"]),
            marker=dict(size=[tam + 6 if n == nodo_sel else tam for n in g["nodo"]], symbol=simbolo,
                        color=[COLOR_NIVEL[n] for n in g["nivel"]],
                        line=dict(width=[2.5 if n == nodo_sel else 1.5 for n in g["nodo"]],
                                  color=[COLORS["primary"] if n == nodo_sel else "white" for n in g["nodo"]])),
            customdata=g["nodo"], hovertext=[_hover_nodo(r) for r in g.itertuples()], hoverinfo="text",
            name=tipo, showlegend=False,
        ))
    fig.add_trace(go.Scattergeo(lat=[TYASA["lat"]], lon=[TYASA["lon"]], mode="markers", hoverinfo="text",
                                hovertext=["<b>TYASA</b><br>" + TYASA["lugar"]], showlegend=False,
                                marker=dict(size=15, symbol="star", color=COLORS["primary"],
                                            line=dict(width=1.5, color="white"))))
    if tormentas is not None and not tormentas.empty:
        t = tormentas.drop_duplicates("nombre")
        fig.add_trace(go.Scattergeo(lat=t["lat"], lon=t["lon"], mode="markers+text", text=t["nombre"],
                                    textposition="bottom center", showlegend=False, hoverinfo="text",
                                    hovertext=[f"<b>{escape(str(x.nombre))}</b><br>{x.tipo} · {x.viento_kt} kt"
                                               for x in t.itertuples()],
                                    marker=dict(size=16, symbol="circle-open", color="#7C3AED", line=dict(width=3))))
    lons = [lo for _, lo in (sel["coords"] if sel else [])] or [lo for r in rutas for _, lo in r["coords"]]
    cruza_pacifico = bool(lons) and max(lons) > 100 and min(lons) < -100
    fig.update_geos(projection_type="natural earth", showcountries=True, countrycolor="#D7DDE5",
                    showland=True, landcolor="#EEF1F5", showocean=True, oceancolor="#F8FAFC",
                    showlakes=False, showframe=False, coastlinecolor="#D7DDE5",
                    projection_rotation=dict(lon=-110 if cruza_pacifico else -30), lataxis_range=[-50, 72])
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor="white", font_size=12, font_family=_FUENTE),
                      clickmode="event+select", dragmode="pan")
    return fig


def leyenda_mapa(con_rutas: bool) -> str:
    def m(forma, color, texto):
        formas = {"rombo": "width:9px;height:9px;transform:rotate(45deg);",
                  "circulo": "width:10px;height:10px;border-radius:50%;",
                  "cuadro": "width:10px;height:10px;border-radius:2px;"}
        return (f"<span style='display:inline-flex;align-items:center;gap:6px;'><i style='display:inline-block;"
                f"{formas[forma]}background:{color};'></i>{texto}</span>")
    partes = [m("rombo", COLORS["text_light"], "paso marítimo"), m("circulo", COLORS["text_light"], "puerto de llegada"),
              m("cuadro", COLORS["text_light"], "país con noticias")]
    if con_rutas:
        partes += [m("cuadro", COLOR_ORIGEN_SEL, "origen elegido"), m("cuadro", COLOR_ORIGEN, "otros orígenes"),
                   m("cuadro", COLOR_PASA, "por donde pasa la ruta")]
    partes += [m("circulo", COLOR_NIVEL["normal"], "normal"), m("circulo", COLOR_NIVEL["vigilar"], "vigilar"),
               m("circulo", COLOR_NIVEL["riesgo"], "riesgo")]
    return (f"<div style='display:flex;flex-wrap:wrap;gap:6px 14px;font-size:11.5px;color:{COLORS['text_light']};"
            f"font-family:{_FUENTE};'>{''.join(partes)}</div>")


# ── Tabla de la red ───────────────────────────────────────────────────────────
def tabla_red(red: pd.DataFrame) -> pd.DataFrame:
    orden = {"riesgo": 0, "vigilar": 1, "normal": 2, "sin datos": 3}
    t = red.assign(_o=red["nivel"].map(orden)).sort_values(["_o", "graves", "noticias"], ascending=[True, False, False])
    return pd.DataFrame({
        "nodo": t["nodo"],
        "nivel": t["nivel"],
        "Estado": t["nivel"].map(lambda n: f"{ICONO_NIVEL[n]} {ETIQUETA_NIVEL[n]}"),
        "Lugar": t["nombre"],
        "Tipo": t["tipo"],
        "Tráfico vs. normal": [f"{c:+.0%}" if pd.notna(c) else "—" for c in t["cambio"]],
        "Noticias": [_n_noticias(n, g) for n, g in zip(t["noticias"], t["graves"])],
        "Clima": [x.tormenta or (f"oleaje {x.oleaje_m:.1f} m" if pd.notna(x.oleaje_m) else "—")
                  for x in t.itertuples()],
    }).reset_index(drop=True)


def estilo_red(df: pd.DataFrame):
    """Columna Estado en el color de su nivel (con símbolo y texto)."""
    niveles = df["nivel"]
    vista = df.drop(columns=["nodo", "nivel"])
    return vista.style.apply(lambda col: [f"color:{COLOR_NIVEL[n]};font-weight:600" for n in niveles]
                             if col.name == "Estado" else [""] * len(col), axis=0)


# ── Detalle de un punto ───────────────────────────────────────────────────────
def lista_noticias(avisos: pd.DataFrame, n: int = 8, con_lugar: bool = False) -> str:
    if avisos.empty:
        return f"<div style='font-size:13px;color:{COLORS['text_light']};'>Sin noticias en los últimos 21 días.</div>"
    filas = []
    for a in avisos.sort_values(["severidad", "fecha"], ascending=[True, False]).head(n).itertuples():
        nivel = "riesgo" if a.severidad == "alta" else "vigilar"
        url = a.url if str(a.url or "").startswith("http") else None
        titulo = (f"<a class='rp-a' href='{escape(url)}' target='_blank' rel='noopener'>{escape(a.titulo)}</a>"
                  if url else escape(a.titulo))
        lugar = f"{escape(a.lugar)} · " if con_lugar else ""
        filas.append(
            f"<div style='padding:9px 0;border-bottom:1px solid #EEF0F3;'>"
            f"<div style='display:flex;gap:8px;align-items:center;margin-bottom:3px;flex-wrap:wrap;'>"
            f"{chip(nivel, 'Grave' if nivel == 'riesgo' else 'Vigilar')}"
            f"<span style='font-size:11.5px;color:{COLORS['text_light']};'>{lugar}{fecha_corta(a.fecha)} · "
            f"{escape(str(a.fuente or ''))}</span></div>"
            f"<div style='font-size:13px;line-height:1.4;color:{COLORS['text']};'>{titulo}</div>"
            + (f"<div style='font-size:12px;color:{COLORS['text_light']};margin-top:2px;'>{escape(a.razon)}</div>"
               if a.razon else "") + "</div>")
    return f"{_CSS}<div style='font-family:{_FUENTE};'>{''.join(filas)}</div>"


def detalle_nodo(fila: pd.Series, avisos: pd.DataFrame, n: int = 4) -> str:
    motivos = ("".join(f"<div style='margin:2px 0;'><span style='color:{COLOR_NIVEL[nv]};'>{ICONO_NIVEL[nv]}</span> "
                       f"{escape(t)}</div>" for nv, t in fila["motivos"])
               or "<div>✓ Sin alertas</div>")
    return (f"{_CSS}<div style='font-family:{_FUENTE};'>"
            f"<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;'>"
            f"<span style='font-size:17px;font-weight:700;color:{COLORS['primary']};'>{escape(fila['nombre'])}</span>"
            f"{chip(fila['nivel'])}<span style='font-size:12px;color:{COLORS['text_light']};'>{fila['tipo']}</span></div>"
            f"<div style='margin:8px 0 10px;font-size:13px;color:{COLORS['text']};line-height:1.5;'>{motivos}</div>"
            f"<div style='{_ETIQ}margin-top:4px;'>Noticias</div>{lista_noticias(avisos, n)}</div>")


def grafica_trafico(serie: pd.Series, estado: dict, titulo: str, unidad: str) -> go.Figure:
    """Promedio de 7 días del último año contra el nivel normal (línea punteada)."""
    s = serie.sort_index()
    s = s[s.index >= s.index.max() - pd.Timedelta(days=365)] if len(s) else s
    prom = s.rolling(7, min_periods=3).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prom.index, y=prom, mode="lines", name="Promedio 7 días",
                             line=dict(color=COLORS["primary"], width=2),
                             hovertemplate="%{x|%d %b %Y}: %{y:.1f} " + unidad + "<extra></extra>"))
    if estado.get("base"):
        fig.add_trace(go.Scatter(x=[prom.index.min(), prom.index.max()], y=[estado["base"]] * 2, mode="lines",
                                 name="Nivel normal", line=dict(color=COLORS["neutral"], width=1.5, dash="dash"),
                                 hovertemplate="Normal: %{y:.1f} " + unidad + "<extra></extra>"))
    fig.update_layout(height=210, margin=dict(l=6, r=6, t=30, b=6), plot_bgcolor="white", paper_bgcolor="white",
                      title=dict(text=titulo, font=dict(size=12, color=COLORS["text_light"]), x=0, y=0.97),
                      font=dict(family=_FUENTE, size=11, color=COLORS["text"]), hovermode="x unified",
                      legend=dict(orientation="h", y=1.18, x=1, xanchor="right", font=dict(size=10)),
                      xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#EEF0F3", rangemode="tozero", title=None))
    return fig


# ── Rutas ─────────────────────────────────────────────────────────────────────
def tabla_rutas(rutas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame({
        # el país ya va en el título de la tabla ("Rutas desde ..."): solo el destino y la vía
        "Ruta": ["→ " + r["nombre"].split(" → ", 1)[-1] for r in rutas],
        "Días": [f"{r['dias_min']}–{r['dias_max']}" for r in rutas],
        "Estado": ["✕ Cerrada" if not r["disponible"] else f"{ICONO_NIVEL[r['nivel']]} {ETIQUETA_NIVEL[r['nivel']]}"
                   for r in rutas],
        "Noticias": [_n_noticias(r["noticias"], r["graves"]) for r in rutas],
    })


def estilo_rutas(df: pd.DataFrame, rutas: list[dict]):
    """Fila en rojo claro si la ruta tiene noticias (más intenso si alguna es
    grave), gris si el escenario la cierra; Estado en el color de su nivel."""
    def fila(row):
        r = rutas[row.name]
        if not r["disponible"]:
            base = "color:#9CA3AF;"
        elif r["graves"]:
            base = "background-color:#F9D9D9;"
        elif r["noticias"]:
            base = "background-color:#FDEEEE;"
        else:
            base = ""
        estado = "" if not r["disponible"] else f"color:{COLOR_NIVEL[r['nivel']]};font-weight:600;"
        return [base + (estado if c == "Estado" else "") for c in row.index]
    return df.style.apply(fila, axis=1)


def detalle_ruta(ruta: dict) -> str:
    """Encabezado de la ruta elegida: nombre, días, estado y motivos."""
    cerrada = "" if ruta["disponible"] else chip("riesgo", "Cerrada en el escenario")
    pasa = ("pasa por " + ", ".join(PASOS[p]["nombre"] for p in ruta["pasos"]) if ruta["pasos"]
            else "sin pasos marítimos de por medio")
    return (f"{_CSS}<div style='font-family:{_FUENTE};'>"
            f"<div style='display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap;'>"
            f"<span style='font-size:15px;font-weight:700;color:{COLORS['primary']};'>{escape(ruta['nombre'])}</span>"
            f"<span style='font-size:22px;font-weight:700;color:{COLORS['primary']};font-variant-numeric:tabular-nums;'>"
            f"{ruta['dias_min']}–{ruta['dias_max']} d</span></div>"
            f"<div style='display:flex;gap:6px;margin:4px 0 8px;flex-wrap:wrap;align-items:center;'>{chip(ruta['nivel'])}"
            f"{cerrada}<span style='font-size:12px;color:{COLORS['text_light']};'>puerta a puerta · estimado · "
            f"{escape(pasa)}</span></div>{motivos_ruta(ruta['ev'])}</div>")


def trayecto(ruta: dict, red: pd.DataFrame) -> str:
    """Tira de pasos: origen → mar → pasos marítimos → puerto → camión → planta, con el estado de cada uno."""
    r = red.set_index("nodo")
    o = PAISES[ruta["iso"]]

    def paso(etiqueta, titulo, sub, nodo=None):
        nivel = r.loc[nodo, "nivel"] if nodo and nodo in r.index else None
        alerta = nivel and nivel not in ("normal", "sin datos")
        borde = COLOR_NIVEL[nivel] if alerta else "#E5E7EB"
        fondo = FONDO_NIVEL[nivel] if alerta else "#FFFFFF"
        return (f"<div style='flex:1 1 105px;min-width:105px;border:1px solid {borde};border-radius:10px;"
                f"padding:7px 10px;background:{fondo};'>"
                f"<div style='{_ETIQ}font-size:9.5px;'>{etiqueta}</div>"
                f"<div style='font-size:12.5px;font-weight:600;color:{COLORS['text']};line-height:1.25;margin-top:2px;'>"
                f"{escape(titulo)}</div>"
                f"<div style='font-size:11px;color:{COLORS['text_light']};margin-top:1px;'>{escape(sub)}</div>"
                + (f"<div style='margin-top:5px;'>{chip(nivel)}</div>" if nivel else "") + "</div>")

    pasos = [paso("Salida", o["puerto"], o["nombre"], f"pais:{ruta['iso']}")]
    if ruta["puerto"]:
        pasos.append(paso("Mar", f"{ruta['dias_mar'][0]}–{ruta['dias_mar'][1]} días", f"{ruta['nm']:,.0f} millas"))
        pasos += [paso("Paso marítimo", PASOS[p]["nombre"], "", f"paso:{p}") for p in ruta["pasos"]]
        pasos.append(paso("Llegada", PUERTOS[ruta["puerto"]]["nombre"], "puerto", f"puerto:{ruta['puerto']}"))
    pasos.append(paso("Camión", f"{ruta['km_camion']:,} km", "a la planta"))
    pasos.append(paso("Planta", "TYASA", TYASA["lugar"]))
    flecha = f"<div style='align-self:center;color:#9CA3AF;font-size:14px;'>›</div>"
    return f"<div style='display:flex;gap:6px;flex-wrap:wrap;font-family:{_FUENTE};'>{flecha.join(pasos)}</div>"


def motivos_ruta(ev: dict) -> str:
    if not ev["motivos"]:
        return (f"<div style='padding:8px 12px;border-radius:8px;background:{FONDO_NIVEL['normal']};"
                f"color:{COLORS['success']};font-size:13px;'>✓ Sin alertas en los puntos de esta ruta.</div>")
    return "".join(
        f"<div style='padding:6px 12px;border-left:3px solid {COLOR_NIVEL[n]};background:{FONDO_NIVEL[n]};"
        f"border-radius:0 8px 8px 0;font-size:12.5px;color:{COLORS['text']};margin-bottom:5px;'>"
        f"<span style='color:{COLOR_NIVEL[n]};'>{ICONO_NIVEL[n]}</span> {escape(t)}</div>" for n, t in ev["motivos"])


# ── Precio del material ───────────────────────────────────────────────────────
TEXTO_SEMAFORO = {"normal": "Riesgo de alza bajo", "vigilar": "Riesgo de alza elevado", "riesgo": "Riesgo de alza alto",
                  "sin datos": "Sin semáforo"}


def tarjeta_precio(nombre: str, info: dict | None) -> str:
    """Precio del material junto a sus rutas: semáforo de alza, último precio,
    cambio a 3 meses y quiebre en formación (página de quiebres de ferroaleaciones)."""
    if not info:
        return (f"<div style='font-size:12.5px;color:{COLORS['text_light']};'>Sin precios de {escape(nombre)} "
                f"en el sistema.</div>")
    extra = []
    if info["arriba"]:
        extra.append(chip("vigilar", "Precio arriba de su rango normal"))
    f = info["formacion"]
    if f:
        extra.append(chip("vigilar", f"Posible quiebre en formación: {f['regimen']}"))
    if not info["confiable"] and info["semaforo"]:
        extra.append(f"<span style='font-size:11.5px;color:{COLORS['text_light']};'>señal débil</span>")
    c3 = info["cambio_3m"]
    return (f"{_CSS}<div class='rp-card' style='display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;"
            f"background:{COLORS['surface']};border:1px solid #E5E7EB;border-radius:10px;padding:9px 14px;"
            f"font-family:{_FUENTE};'>"
            f"<div><div style='{_ETIQ}'>Precio de {escape(nombre)}</div>"
            f"<div style='font-size:19px;font-weight:700;color:{COLORS['text']};font-variant-numeric:tabular-nums;'>"
            f"{info['precio']:,.0f} <span style='font-size:12px;font-weight:500;color:{COLORS['text_light']};'>USD/t · "
            f"{fecha_corta(info['fecha'])}</span></div></div>"
            + (f"<div style='font-size:12.5px;color:{COLORS['text_light']};'>3 meses: <b style='color:{COLORS['text']};'>"
               f"{c3:+.0%}</b></div>" if c3 is not None else "")
            + chip(info["nivel"], TEXTO_SEMAFORO[info["nivel"]]) + "".join(extra) + "</div>")


# ── Mapa de calor material × origen ───────────────────────────────────────────
COLOR_CALOR = {**COLOR_NIVEL, "cerrada": "#4B5563"}
ICONO_CALOR = {**ICONO_NIVEL, "cerrada": "✕"}
ETIQUETA_CALOR = {**ETIQUETA_NIVEL, "cerrada": "Cerrada"}


def mapa_calor(matriz: pd.DataFrame, precios: dict, nombres: dict, sel: tuple | None = None) -> go.Figure:
    """Cuadrícula seleccionable: filas = material; primera columna = semáforo de
    precio; demás = país de origen, color = nivel de la mejor ruta disponible."""
    paises = matriz.groupby("pais").size().sort_values(ascending=False).index.tolist()
    cols = ["Precio"] + paises
    mats = list(dict.fromkeys(matriz["material"]))
    fig = go.Figure()
    # Fondo: todas las celdas (para leer la cuadrícula), sin hover
    fig.add_trace(go.Scatter(x=[c for _ in mats for c in cols], y=[m for m in mats for _ in cols], mode="markers",
                             marker=dict(symbol="square", size=30, color="#F3F4F6"), hoverinfo="skip",
                             showlegend=False))
    xs, ys, colores, textos, hovers, datos = [], [], [], [], [], []
    for m in mats:
        info = precios.get(m)
        nivel = info["nivel"] if info else "sin datos"
        xs.append("Precio"); ys.append(m); colores.append(COLOR_CALOR[nivel]); textos.append(ICONO_CALOR[nivel])
        hovers.append(f"<b>{escape(nombres[m])} · precio</b><br>{TEXTO_SEMAFORO[nivel]}"
                      + (f"<br>{info['precio']:,.0f} USD/t" + (f" · {info['cambio_3m']:+.0%} en 3 meses"
                                                               if info["cambio_3m"] is not None else "")
                         + ("<br>Posible quiebre en formación" if info["formacion"] else "") if info else ""))
        datos.append([m, ""])
    for r in matriz.itertuples():
        xs.append(r.pais); ys.append(r.material); colores.append(COLOR_CALOR[r.nivel]); textos.append(ICONO_CALOR[r.nivel])
        hovers.append(f"<b>{escape(nombres[r.material])} desde {escape(r.pais)}</b><br>{ETIQUETA_CALOR[r.nivel]}"
                      f"<br>Mejor ruta: {escape(r.ruta)} ({r.dias} d)"
                      + (f"<br>{r.noticias} noticias ({r.graves} graves)" if r.noticias else "")
                      + "<br><i>Clic para ver sus rutas</i>")
        datos.append([r.material, r.iso])
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=textos, textfont=dict(color="white", size=12),
        marker=dict(symbol="square", size=30, color=colores, line=dict(width=2, color="white")),
        customdata=datos, hovertext=hovers, hoverinfo="text", showlegend=False,
        # al seleccionar, Plotly atenúa lo demás: se deja todo opaco (la elegida lleva borde)
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
    ))
    i = next((k for k, d in enumerate(datos) if sel and d[0] == sel[0] and d[1] == sel[1]), None)
    if i is not None:
        fig.add_trace(go.Scatter(x=[xs[i]], y=[ys[i]], mode="markers", hoverinfo="skip", showlegend=False,
                                 marker=dict(symbol="square-open", size=38, color=COLORS["primary"],
                                             line=dict(width=2.5))))
    fig.update_layout(
        height=70 + 42 * len(mats), margin=dict(l=10, r=10, t=90, b=10), plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family=_FUENTE, size=11.5, color=COLORS["text"]), clickmode="event+select", dragmode=False,
        hoverlabel=dict(bgcolor="white", font_size=12, font_family=_FUENTE),
        xaxis=dict(side="top", tickangle=-40, showgrid=False, zeroline=False, fixedrange=True,
                   categoryorder="array", categoryarray=cols),
        yaxis=dict(showgrid=False, zeroline=False, fixedrange=True, autorange="reversed",
                   categoryorder="array", categoryarray=mats, tickvals=mats, ticktext=[f"{m}  " for m in mats]),
    )
    return fig
