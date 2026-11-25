"""
mercado_rutas/vistas.py — Piezas visuales de la página Rutas y puertos
(pages/mercado/10_rutas_puertos.py): mapa, tarjetas, tablas y detalle.

Color de estado reservado (riesgo / vigilar / normal / sin datos), siempre con
símbolo + texto (nunca solo color) y sin emojis.
"""

from html import escape
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go

from config import COLORS
from mercado_rutas.red import FRONTERAS, ISO3, PAISES, PASO_PAISES, PASOS, PUERTOS, TYASA

COLOR_NIVEL = {"riesgo": COLORS["danger"], "vigilar": COLORS["warning"], "normal": COLORS["success"],
               "sin datos": "#9CA3AF"}
FONDO_NIVEL = {"riesgo": "#FDECEC", "vigilar": "#FFF4E5", "normal": "#EAF5EB", "sin datos": "#F3F4F6"}
ICONO_NIVEL = {"riesgo": "▲", "vigilar": "●", "normal": "✓", "sin datos": "–"}
ETIQUETA_NIVEL = {"riesgo": "Riesgo", "vigilar": "Vigilar", "normal": "Normal", "sin datos": "Sin datos"}
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Mapa: países de origen del material, el elegido y los que bordea la ruta elegida
COLOR_ORIGEN, COLOR_ORIGEN_SEL, COLOR_PASA = "#B3C9E0", COLORS["secondary"], "#F4C766"

# Íconos de línea (estilo Lucide, licencia ISC): trazo del color del texto, sin relleno
_SVG = {
    "pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    "barco": '<path d="M12 10.2V14"/><path d="M12 2v3"/><path d="M19 13V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6"/>'
             '<path d="M19.4 20A11.6 11.6 0 0 0 21 14l-8.2-3.6a2 2 0 0 0-1.6 0L3 14a11.6 11.6 0 0 0 2.8 7.8"/>'
             '<path d="M2 21c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1s1.2 1 2.5 1c2.5 0 2.5-2 5-2 1.3 0 '
             '1.9.5 2.5 1"/>',
    "olas": '<path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>'
            '<path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>'
            '<path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
    "ancla": '<path d="M12 22V8"/><path d="M5 12H2a10 10 0 0 0 20 0h-3"/><circle cx="12" cy="5" r="3"/>',
    "camion": '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/>'
              '<path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14"/>'
              '<circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>',
    "tren": '<rect width="16" height="16" x="4" y="3" rx="2"/><path d="M4 11h16"/><path d="M12 3v8"/>'
            '<path d="m8 19-2 3"/><path d="m18 22-2-3"/><path d="M8 15h.01"/><path d="M16 15h.01"/>',
    "bandera": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    "planta": '<path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/>'
              '<path d="M17 18h1"/><path d="M12 18h1"/><path d="M7 18h1"/>',
    "noticia": '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9'
               'c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/>',
    "tormenta": '<path d="M12.8 19.6A2 2 0 1 0 14 16H2"/><path d="M17.5 8a2.5 2.5 0 1 1 2 4H2"/>'
                '<path d="M9.8 4.4A2 2 0 1 1 11 8H2"/>',
}


def icono(nombre: str, color: str = "#6B7280", tam: int = 18) -> str:
    """Ícono como imagen (st.html quita los <svg> en línea, pero deja <img> con data URI)."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_SVG[nombre]}</svg>')
    return (f"<img alt='' width='{tam}' height='{tam}' style='flex:none;display:block' "
            f"src='data:image/svg+xml;charset=utf-8,{quote(svg)}'>")


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

    def tarjeta(titulo, valor, detalle, nivel, ico):
        c = COLOR_NIVEL[nivel]
        return (f"<div class='rp-card' style='flex:1 1 190px;background:{COLORS['surface']};border:1px solid #E5E7EB;"
                f"border-left:4px solid {c};border-radius:10px;padding:9px 14px;display:flex;align-items:center;"
                f"gap:12px;'>{icono(ico, COLORS['text_light'], 20)}"
                f"<div style='font-size:24px;font-weight:700;color:{COLORS['text']};font-variant-numeric:tabular-nums;"
                f"line-height:1;'>{valor}</div>"
                f"<div><div style='{_ETIQ}'>{titulo}</div>"
                f"<div style='font-size:12px;color:{COLORS['text_light']};'>{detalle}</div></div></div>")

    def det(r, v, total):
        partes = [f"{r} en riesgo" if r else "", f"{v} por vigilar" if v else ""]
        return (" · ".join(p for p in partes if p) or "todo normal") + f" · de {total}"

    html = "".join([
        tarjeta("Pasos marítimos", rp + vp, det(rp, vp, tp), "riesgo" if rp else "vigilar" if vp else "normal", "olas"),
        tarjeta("Puertos de llegada", rq + vq, det(rq, vq, tq), "riesgo" if rq else "vigilar" if vq else "normal",
                "ancla"),
        tarjeta("Noticias graves", graves,
                f"en {lugares_graves} lugar{'es' if lugares_graves != 1 else ''} · 21 días" if graves else "21 días",
                "riesgo" if graves else "normal", "noticia"),
        tarjeta("Tormentas cerca", len(cerca),
                ", ".join(f"{r.nombre} a {r.km:,.0f} km de {PUERTOS[r.puerto]['nombre']}" for r in cerca.itertuples())
                or "ninguna a menos de 1,000 km", "riesgo" if len(cerca) else "normal", "tormenta"),
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


def _sin_salto(lons: list[float]) -> list[float]:
    """Longitudes continuas (sin el salto de 180 a -180 al cruzar el Pacífico)."""
    out = []
    for lo in lons:
        if out:
            while lo - out[-1] > 180:
                lo -= 360
            while lo - out[-1] < -180:
                lo += 360
        out.append(lo)
    return out


def _densificar(coords: list[tuple], n: int = 70) -> tuple[list[float], list[float]]:
    """~n puntos repartidos a lo largo de la ruta (para la animación del recorrido)."""
    lats = [c[0] for c in coords]
    lons = _sin_salto([c[1] for c in coords])
    seg = [((la2 - la1) ** 2 + (lo2 - lo1) ** 2) ** 0.5 for la1, lo1, la2, lo2 in
           zip(lats[:-1], lons[:-1], lats[1:], lons[1:])]
    total = sum(seg) or 1
    out_la, out_lo = [], []
    for i, d in enumerate(seg):
        k = max(1, round(n * d / total))
        for j in range(k):
            t = j / k
            out_la.append(lats[i] + (lats[i + 1] - lats[i]) * t)
            out_lo.append(lons[i] + (lons[i + 1] - lons[i]) * t)
    out_la.append(lats[-1])
    out_lo.append(lons[-1])
    return out_la, [((lo + 180) % 360) - 180 for lo in out_lo]


VISTAS_MAPA = ["Ruta", "México", "Mundo"]


def _encuadre(fig: go.Figure, coords: list[tuple], vista: str, cruza_pacifico: bool) -> None:
    """Acerca el mapa: a la ruta elegida, a la llegada a México o al mundo completo."""
    base = dict(projection_type="natural earth", showcountries=True, countrycolor="#D7DDE5", showland=True,
                landcolor="#EEF1F5", showocean=True, oceancolor="#F8FAFC", showlakes=False, showframe=False,
                coastlinecolor="#D7DDE5")
    if vista == "México":
        fig.update_geos(**base, projection_rotation=dict(lon=-98), center=dict(lat=21.5, lon=-98),
                        projection_scale=5.2)
    elif vista == "Ruta" and coords:
        lats = [c[0] for c in coords] + [TYASA["lat"]]
        lons = _sin_salto([c[1] for c in coords] + [TYASA["lon"]])
        c_lon = ((min(lons) + max(lons)) / 2 + 180) % 360 - 180
        c_lat = (min(lats) + max(lats)) / 2
        escala = min(250 / max(max(lons) - min(lons), 8), 120 / max(max(lats) - min(lats), 6))
        fig.update_geos(**base, projection_rotation=dict(lon=c_lon), center=dict(lat=c_lat, lon=c_lon),
                        projection_scale=max(1.0, min(escala, 7.0)))
    else:
        fig.update_geos(**base, projection_rotation=dict(lon=-110 if cruza_pacifico else -30),
                        lataxis_range=[-50, 72])


def mapa_red(red: pd.DataFrame, rutas: list[dict] | None = None, ruta_sel: str | None = None,
             tormentas: pd.DataFrame | None = None, nodo_sel: str | None = None,
             origenes: list[str] | None = None, iso_sel: str | None = None, altura: int = 470,
             vista: str = "Mundo", animar: bool = False) -> go.Figure:
    """Mapa de la red. Si se dan <origenes> (ISO numérico del material) se
    sombrean; el país elegido y los países que bordea la ruta elegida se
    iluminan, y la ruta lleva un halo. <vista>: Ruta | México | Mundo.
    <animar>: botón "Ver recorrido" que mueve un marcador por la ruta."""
    fig = go.Figure()
    rutas = rutas or []
    sel = next((r for r in rutas if r["id"] == ruta_sel), None)

    # Países: origen del material, el elegido y por donde pasa la ruta elegida
    if origenes:
        otros = [i for i in origenes if i != iso_sel and i in ISO3]
        _capa_paises(fig, [ISO3[i] for i in otros], COLOR_ORIGEN,
                     [f"<b>{PAISES[i]['nombre']}</b><br>País de origen · elígelo arriba para ver sus rutas"
                      for i in otros])
    if sel:
        pasa = {}
        for p in sel["pasos"]:
            for c in PASO_PAISES.get(p, []):
                pasa.setdefault(c, PASOS[p]["nombre"])
        if sel.get("frontera"):
            pasa.setdefault("USA", f"tren hasta {FRONTERAS[sel['frontera']]['nombre']}")
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
                                    line=dict(width=3.5, color=c,
                                              dash="dash" if sel.get("modo") == "tren" else "solid")))
        if sel["puerto"]:
            p = PUERTOS[sel["puerto"]]
            fig.add_trace(go.Scattergeo(lat=[p["lat"], TYASA["lat"]], lon=[p["lon"], TYASA["lon"]], mode="lines",
                                        line=dict(width=2.5, color=COLORS["primary"], dash="dot"), hoverinfo="skip",
                                        showlegend=False))

    # Halo de los puntos que cruza la ruta elegida
    if sel:
        nodos = ({f"paso:{p}" for p in sel["pasos"]} | ({f"puerto:{sel['puerto']}"} if sel["puerto"] else set())
                 | ({f"frontera:{sel['frontera']}"} if sel.get("frontera") else set()))
        g = red[red["nodo"].isin(nodos)]
        if not g.empty:
            fig.add_trace(go.Scattergeo(lat=g["lat"], lon=g["lon"], mode="markers", hoverinfo="skip", showlegend=False,
                                        marker=dict(size=30, color=[COLOR_NIVEL[n] for n in g["nivel"]], opacity=0.22)))

    # Puntos de la red (encima): países con noticias, pasos, puertos y cruces
    for tipo, simbolo, tam in (("País de origen", "square", 9), ("Paso marítimo", "diamond", 13),
                               ("Puerto de llegada", "circle", 12), ("Cruce fronterizo", "hexagon", 12)):
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

    coords_sel = list(sel["coords"]) if sel and sel["coords"] else []
    if sel and sel["puerto"]:
        coords_sel.append((TYASA["lat"], TYASA["lon"]))
    lons = [lo for _, lo in coords_sel] or [lo for r in rutas for _, lo in r["coords"]]
    cruza_pacifico = bool(lons) and max(lons) > 100 and min(lons) < -100
    _encuadre(fig, coords_sel, vista, cruza_pacifico)

    # Recorrido animado: una estela que se dibuja y un marcador que avanza hasta la planta
    menus = []
    if animar and len(coords_sel) > 1:
        la, lo = _densificar(coords_sel)
        fig.add_trace(go.Scattergeo(lat=[la[0]], lon=[lo[0]], mode="lines", hoverinfo="skip", showlegend=False,
                                    line=dict(width=5, color=COLORS["primary"])))
        fig.add_trace(go.Scattergeo(lat=[la[0]], lon=[lo[0]], mode="markers", hoverinfo="skip", showlegend=False,
                                    marker=dict(size=14, color="white", line=dict(width=4, color=COLORS["primary"]))))
        i_estela, i_marca = len(fig.data) - 2, len(fig.data) - 1
        fig.frames = [go.Frame(name=str(i), traces=[i_estela, i_marca],
                               data=[go.Scattergeo(lat=la[:i + 1], lon=lo[:i + 1]),
                                     go.Scattergeo(lat=[la[i]], lon=[lo[i]])])
                      for i in range(len(la))]
        menus = [dict(type="buttons", direction="left", x=0.01, y=0.03, xanchor="left", yanchor="bottom",
                      showactive=False, pad=dict(r=4, t=4), bgcolor="white", bordercolor="#D7DDE5", borderwidth=1,
                      font=dict(size=12, color=COLORS["primary"]), buttons=[
                          dict(label="Ver recorrido", method="animate",
                               args=[None, dict(frame=dict(duration=55, redraw=True), transition=dict(duration=0),
                                                fromcurrent=False, mode="immediate")]),
                          dict(label="Pausa", method="animate",
                               args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")]),
                      ])]
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor="white", font_size=12, font_family=_FUENTE),
                      clickmode="event+select", dragmode="pan", updatemenus=menus)
    return fig


# Controles del mapa: acercar, alejar y volver al encuadre (sin el resto de la barra de Plotly)
CONFIG_MAPA = {"displayModeBar": True, "displaylogo": False, "scrollZoom": True,
               "modeBarButtons": [["zoomInGeo", "zoomOutGeo", "resetGeo"]]}


def leyenda_mapa(con_rutas: bool) -> str:
    def m(forma, color, texto):
        formas = {"rombo": "width:9px;height:9px;transform:rotate(45deg);",
                  "circulo": "width:10px;height:10px;border-radius:50%;",
                  "cuadro": "width:10px;height:10px;border-radius:2px;",
                  "hexagono": "width:11px;height:10px;clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);"}
        return (f"<span style='display:inline-flex;align-items:center;gap:6px;'><i style='display:inline-block;"
                f"{formas[forma]}background:{color};'></i>{texto}</span>")
    partes = [m("rombo", COLORS["text_light"], "paso marítimo"), m("circulo", COLORS["text_light"], "puerto de llegada"),
              m("hexagono", COLORS["text_light"], "cruce fronterizo"),
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
def tabla_rutas(rutas: list[dict], principal: str | None = None) -> pd.DataFrame:
    return pd.DataFrame({
        # el país ya va en el título de la tabla ("Rutas desde ..."): solo el destino y la vía
        "Ruta": ["→ " + r["nombre"].split(" → ", 1)[-1] + ("  · principal" if r["id"] == principal else "")
                 for r in rutas],
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


def detalle_ruta(ruta: dict, proveedor_principal: str | None = None) -> str:
    """Encabezado de la ruta elegida: nombre, días, estado y motivos."""
    cerrada = "" if ruta["disponible"] else chip("riesgo", "Cerrada en el escenario")
    if proveedor_principal:
        cerrada += (f"<span style='display:inline-flex;padding:2px 9px;border-radius:999px;font-size:11.5px;"
                    f"font-weight:600;background:#E8EEF5;color:{COLORS['primary']};'>Ruta principal de "
                    f"{escape(proveedor_principal)}</span>")
    pasa = ("pasa por " + ", ".join(PASOS[p]["nombre"] for p in ruta["pasos"]) if ruta["pasos"]
            else f"por tren, cruza en {FRONTERAS[ruta['frontera']]['nombre']}" if ruta.get("frontera")
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
    """Línea de tiempo con íconos: salida → mar → pasos marítimos → puerto (o
    cruce fronterizo) → camión o tren → planta, con el estado de cada punto."""
    r = red.set_index("nodo")
    o = PAISES[ruta["iso"]]

    def paso(ico, titulo, sub, nodo=None, tramo=False):
        nivel = r.loc[nodo, "nivel"] if nodo and nodo in r.index else None
        alerta = nivel in ("riesgo", "vigilar")
        c = COLOR_NIVEL[nivel] if alerta else COLORS["secondary"]
        # Los tramos (mar, camión, tren) van en círculo relleno; los lugares, en contorno
        circulo = (f"background:{c};color:white;border:2px solid {c};" if tramo
                   else f"background:{FONDO_NIVEL[nivel] if alerta else 'white'};color:{c};border:2px solid {c};")
        estado = (f"<div style='margin-top:4px;'>{chip(nivel)}</div>" if alerta else "")
        return (f"<div style='flex:1 1 0;min-width:92px;display:flex;flex-direction:column;align-items:center;"
                f"text-align:center;position:relative;z-index:1;'>"
                f"<div style='width:40px;height:40px;border-radius:50%;display:flex;align-items:center;"
                f"justify-content:center;{circulo}'>{icono(ico, 'white' if tramo else c, 19)}</div>"
                f"<div style='font-size:12.5px;font-weight:700;color:{COLORS['text']};margin-top:6px;line-height:1.25;'>"
                f"{escape(titulo)}</div>"
                f"<div style='font-size:11px;color:{COLORS['text_light']};line-height:1.3;'>{escape(sub)}</div>"
                f"{estado}</div>")

    pasos = [paso("pin", o["puerto"], f"Salida · {o['nombre']}", f"pais:{ruta['iso']}")]
    if ruta["puerto"]:
        pasos.append(paso("barco", f"Barco · {ruta['dias_mar'][0]}–{ruta['dias_mar'][1]} días",
                          f"{ruta['nm']:,.0f} millas", tramo=True))
        pasos += [paso("olas", PASOS[p]["nombre"], "paso marítimo", f"paso:{p}") for p in ruta["pasos"]]
        pasos.append(paso("ancla", PUERTOS[ruta["puerto"]]["nombre"], "puerto de llegada", f"puerto:{ruta['puerto']}"))
        pasos.append(paso("camion", f"Camión · {ruta['km_camion']:,} km",
                          f"≈ {ruta['km_camion'] / 60:.1f} h a 60 km/h", tramo=True))
    elif ruta.get("frontera"):
        f = FRONTERAS[ruta["frontera"]]
        pasos.append(paso("tren", f"Tren · {f['km_origen']:,} km", "hasta la frontera", tramo=True))
        pasos.append(paso("bandera", f["nombre"], "cruce fronterizo", f"frontera:{ruta['frontera']}"))
        pasos.append(paso("tren", f"Tren · {f['km']:,} km", "a la planta", tramo=True))
    else:
        pasos.append(paso("camion", f"Camión · {ruta['km_camion']:,} km", "nacional", tramo=True))
    pasos.append(paso("planta", "TYASA", TYASA["lugar"]))
    # línea punteada detrás de los círculos
    return (f"<div style='position:relative;font-family:{_FUENTE};padding:4px 0;'>"
            f"<div style='position:absolute;left:5%;right:5%;top:24px;border-top:2px dashed #CBD5E1;'></div>"
            f"<div style='display:flex;gap:4px;'>{''.join(pasos)}</div></div>")


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
        return (f"<div class='rp-card' style='background:{COLORS['surface']};border:1px dashed #D7DDE5;"
                f"border-radius:10px;padding:9px 14px;font-family:{_FUENTE};'><div style='{_ETIQ}'>Precio de "
                f"{escape(nombre)}</div><div style='font-size:12.5px;color:{COLORS['text_light']};margin-top:3px;'>"
                f"Sin precio de referencia en el sistema</div></div>")
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
            + (chip(info["nivel"], TEXTO_SEMAFORO[info["nivel"]]) if info["semaforo"] else
               f"<span style='font-size:11.5px;color:{COLORS['text_light']};'>sin semáforo de alza</span>")
            + "".join(extra) + "</div>")


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
        height=110 + 44 * len(mats), width=(150 + 64 * len(cols)) if len(cols) <= 14 else None,
        margin=dict(l=10, r=10, t=90, b=10), plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family=_FUENTE, size=11.5, color=COLORS["text"]), clickmode="event+select", dragmode=False,
        hoverlabel=dict(bgcolor="white", font_size=12, font_family=_FUENTE),
        xaxis=dict(side="top", tickangle=-40, showgrid=False, zeroline=False, fixedrange=True,
                   categoryorder="array", categoryarray=cols),
        yaxis=dict(showgrid=False, zeroline=False, fixedrange=True, autorange="reversed",
                   categoryorder="array", categoryarray=mats, tickvals=mats, ticktext=[f"{m}  " for m in mats]),
    )
    return fig


# ── Comparar rutas ────────────────────────────────────────────────────────────
_ORDEN_NIVEL = {"normal": 0, "sin datos": 1, "vigilar": 2, "riesgo": 3}


def tarjetas_comparar(rutas: list[dict]) -> str:
    """Una tarjeta por ruta, lado a lado: días, estado, tramos y noticias; marca
    la más rápida y la de menor riesgo entre las disponibles."""
    disp = [r for r in rutas if r["disponible"]]
    rapida = min(disp, key=lambda r: (r["dias_max"], r["dias_min"]))["id"] if disp else None
    segura = (min(disp, key=lambda r: (_ORDEN_NIVEL[r["nivel"]], r["graves"], r["noticias"], r["dias_max"]))["id"]
              if disp else None)

    def fila(etq, val):
        return (f"<div style='display:flex;justify-content:space-between;gap:8px;padding:4px 0;"
                f"border-bottom:1px solid #EEF0F3;font-size:12px;'><span style='color:{COLORS['text_light']};'>"
                f"{etq}</span><span style='color:{COLORS['text']};font-weight:600;text-align:right;'>{val}</span></div>")

    def marca(texto, color, fondo):
        return (f"<span style='font-size:10.5px;font-weight:700;color:{color};background:{fondo};"
                f"padding:2px 7px;border-radius:999px;'>{texto}</span>")

    tarjetas = []
    for i, r in enumerate(rutas, 1):
        marcas = (marca("Más rápida", COLORS["primary"], "#E8EEF5") if r["id"] == rapida else "") + \
                 (marca("Menor riesgo", COLORS["success"], FONDO_NIVEL["normal"]) if r["id"] == segura else "")
        estado = chip("riesgo", "Cerrada en el escenario") if not r["disponible"] else chip(r["nivel"])
        if r["puerto"]:
            tramos = [fila("Barco", f"{r['dias_mar'][0]}–{r['dias_mar'][1]} d · {r['nm']:,.0f} mi"),
                      fila("Llega a", PUERTOS[r["puerto"]]["nombre"]),
                      fila("Camión", f"{r['km_camion']:,} km")]
        elif r.get("frontera"):
            tramos = [fila("Tren", f"{r['km_camion']:,} km"), fila("Cruza en", FRONTERAS[r["frontera"]]["nombre"])]
        else:
            tramos = [fila("Camión", f"{r['km_camion']:,} km")]
        pasos = ", ".join(PASOS[p]["corto"] for p in r["pasos"]) or "ninguno"
        borde = COLOR_NIVEL[r["nivel"]] if r["disponible"] else "#4B5563"
        tarjetas.append(
            f"<div class='rp-card' style='background:{COLORS['surface']};border:1px solid #E5E7EB;"
            f"border-top:4px solid {borde};border-radius:10px;padding:10px 14px;'>"
            f"<div style='display:flex;align-items:center;gap:8px;'><span style='width:22px;height:22px;"
            f"border-radius:50%;background:{COLORS['primary']};color:white;font-size:12px;font-weight:700;display:flex;"
            f"align-items:center;justify-content:center;flex:none;'>{i}</span><span style='font-size:13px;"
            f"font-weight:700;color:{COLORS['primary']};line-height:1.25;'>{escape(r['nombre'])}</span></div>"
            f"<div style='display:flex;align-items:baseline;gap:8px;margin:8px 0 4px;flex-wrap:wrap;'>"
            f"<span style='font-size:24px;font-weight:700;color:{COLORS['text']};font-variant-numeric:tabular-nums;'>"
            f"{r['dias_min']}–{r['dias_max']}</span><span style='font-size:12px;color:{COLORS['text_light']};'>"
            f"días</span>{estado}</div>"
            f"<div style='display:flex;gap:5px;flex-wrap:wrap;min-height:20px;margin-bottom:4px;'>{marcas}</div>"
            + "".join(tramos) + fila("Pasos marítimos", escape(pasos))
            + fila("Noticias", _n_noticias(r["noticias"], r["graves"])) + "</div>")
    return (f"{_CSS}<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;"
            f"font-family:{_FUENTE};'>{''.join(tarjetas)}</div>")


def grafica_comparar(rutas: list[dict]) -> go.Figure:
    """Rango de días puerta a puerta de cada ruta, en el color de su estado."""
    fig = go.Figure()
    ys = [str(i) for i in range(1, len(rutas) + 1)]
    fig.add_trace(go.Bar(
        y=ys, x=[max(r["dias_max"] - r["dias_min"], 0.6) for r in rutas], base=[r["dias_min"] for r in rutas],
        orientation="h", width=0.5,
        marker=dict(color=[COLOR_NIVEL[r["nivel"]] if r["disponible"] else "#9CA3AF" for r in rutas], cornerradius=4),
        text=[f"{r['dias_min']}–{r['dias_max']} d" + ("" if r["disponible"] else " · cerrada") for r in rutas],
        textposition="outside", textfont=dict(size=11, color=COLORS["text"]), cliponaxis=False,
        hovertext=[f"<b>{escape(r['nombre'])}</b><br>{r['dias_min']}–{r['dias_max']} días · "
                   f"{ETIQUETA_NIVEL[r['nivel']] if r['disponible'] else 'Cerrada'}" for r in rutas],
        hoverinfo="text"))
    fig.update_layout(
        height=60 + 42 * len(rutas), margin=dict(l=6, r=70, t=28, b=6), plot_bgcolor="white", paper_bgcolor="white",
        title=dict(text="Días puerta a puerta (mínimo a máximo)", font=dict(size=12, color=COLORS["text_light"]), x=0),
        font=dict(family=_FUENTE, size=11, color=COLORS["text"]), showlegend=False,
        hoverlabel=dict(bgcolor="white", font_size=12, font_family=_FUENTE),
        xaxis=dict(gridcolor="#EEF0F3", rangemode="tozero", fixedrange=True, ticksuffix=" d"),
        yaxis=dict(autorange="reversed", fixedrange=True, tickvals=ys, ticktext=[f"Ruta {y}  " for y in ys]))
    return fig


def mapa_comparar(rutas: list[dict], red: pd.DataFrame, altura: int = 330) -> go.Figure:
    """Las rutas comparadas, cada una en el color de su estado y con su número."""
    fig = go.Figure()
    for i, r in enumerate(rutas, 1):
        if not r["coords"]:
            continue
        c = COLOR_NIVEL[r["nivel"]] if r["disponible"] else "#9CA3AF"
        coords = list(r["coords"]) + ([(TYASA["lat"], TYASA["lon"])] if r["puerto"] else [])
        lat, lon = zip(*coords)
        fig.add_trace(go.Scattergeo(lat=lat, lon=lon, mode="lines", showlegend=False, hoverinfo="skip",
                                    line=dict(width=2.8, color=c, dash="solid" if r["disponible"] else "dot")))
        m = len(coords) // 2
        fig.add_trace(go.Scattergeo(
            lat=[coords[m][0]], lon=[coords[m][1]], mode="markers+text", text=[str(i)],
            textfont=dict(size=11, color="white"), showlegend=False, hoverinfo="text",
            hovertext=[f"<b>{i} · {escape(r['nombre'])}</b><br>{r['dias_min']}–{r['dias_max']} d"],
            marker=dict(size=20, color=COLORS["primary"], line=dict(width=2, color="white"))))
    usados = ({f"paso:{p}" for r in rutas for p in r["pasos"]}
              | {f"frontera:{r['frontera']}" for r in rutas if r.get("frontera")})
    g = red[red["nodo"].isin(usados)]
    if not g.empty:
        fig.add_trace(go.Scattergeo(lat=g["lat"], lon=g["lon"], mode="markers", showlegend=False,
                                    marker=dict(size=11, symbol="diamond", color=[COLOR_NIVEL[n] for n in g["nivel"]],
                                                line=dict(width=1.5, color="white")),
                                    hovertext=[_hover_nodo(x) for x in g.itertuples()], hoverinfo="text"))
    fig.add_trace(go.Scattergeo(lat=[TYASA["lat"]], lon=[TYASA["lon"]], mode="markers", hoverinfo="text",
                                hovertext=["<b>TYASA</b>"], showlegend=False,
                                marker=dict(size=14, symbol="star", color=COLORS["primary"],
                                            line=dict(width=1.5, color="white"))))
    todas = [c for r in rutas for c in r["coords"]]
    lons = [lo for _, lo in todas]
    cruza = bool(lons) and max(lons) > 100 and min(lons) < -100
    _encuadre(fig, todas, "Mundo" if cruza else "Ruta", cruza)
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor="white", font_size=12, font_family=_FUENTE), dragmode="pan")
    return fig
