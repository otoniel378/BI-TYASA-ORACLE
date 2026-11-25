"""
mercado_rutas/riesgo.py — Rutas, estado del tráfico y nivel de riesgo de cada
punto de la red (paso marítimo, puerto de llegada, país de origen) y de cada ruta.

Funciones puras (sin Streamlit ni red): reciben los DataFrames de datos.py.

Nivel de un punto (de peor a mejor):
  riesgo   noticia grave · tráfico muy reducido · tormenta a ≤ 400 km del puerto
  vigilar  noticia · tráfico reducido o inusualmente alto · oleaje ≥ 2.5 m ·
           tormenta a ≤ 1,000 km
  normal   ninguna de las anteriores con datos de tráfico
  sin datos
Una ruta toma el peor nivel de sus puntos (pasos que cruza, país y puerto).
"""

import math

import pandas as pd

from mercado_rutas.red import (
    ACCESOS, DIAS_CANAL, DIAS_FRONTERA, DIAS_PUERTO, FRONTERAS, KMH_CAMION, KMH_TREN, LLEGADAS, NUDOS_LENTO,
    NUDOS_RAPIDO, PAISES, PASOS, PUERTOS, SALIDAS, TYASA,
)

NIVELES = ("riesgo", "vigilar", "normal", "sin datos")
_ORDEN = {n: i for i, n in enumerate(NIVELES)}

# Tráfico: promedio de los últimos VENTANA días contra BASE días que terminan
# HUECO días antes (la base no se contamina con lo reciente). Los puertos
# reciben pocos barcos al día: un barco más o menos mueve mucho un promedio de
# 14 días, por eso usan 30.
VENTANA, VENTANA_PUERTO, HUECO, BASE = 14, 30, 14, 90
REDUCIDO, MUY_REDUCIDO, ALTO = -0.15, -0.35, 0.30
OLEAJE_ALTO_M = 2.5
TORMENTA_RIESGO_KM, TORMENTA_VIGILAR_KM = 400, 1000


def peor(*niveles: str) -> str:
    vals = [n for n in niveles if n]
    return min(vals, key=lambda n: _ORDEN.get(n, 99)) if vals else "sin datos"


def distancia_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


# ── Rutas ─────────────────────────────────────────────────────────────────────
def _resolver(puntos: list) -> tuple[list[tuple], list[str]]:
    """Convierte claves de paso en coordenadas y devuelve (coordenadas, pasos cruzados)."""
    coords, pasos = [], []
    for p in puntos:
        if isinstance(p, str):
            coords.append((PASOS[p]["lat"], PASOS[p]["lon"]))
            pasos.append(p)
        else:
            coords.append(p)
    return coords, pasos


def rutas_de(iso: str, cerrados: frozenset = frozenset()) -> list[dict]:
    """Todas las rutas de un país a TYASA (salida × puerto), ordenadas por días.
    Las que cruzan un paso de <cerrados> quedan con disponible=False."""
    o = PAISES[iso]
    if not o["salidas"]:
        km = o.get("km_terrestre", 0)
        dias = km / KMH_CAMION / 24
        return [{
            "id": f"{iso}-terrestre", "nombre": f"{o['nombre']} → TYASA (carretera)", "iso": iso, "salida": None,
            "puerto": None, "pasos": [], "coords": [], "nm": 0, "km_camion": km,
            "dias_min": max(1, round(dias)), "dias_max": max(2, round(dias) + 2), "dias_mar": (0, 0),
            "disponible": True, "cerrados": [], "frontera": None, "modo": "camion",
        }]
    out = [_ruta_terrestre(iso, f) for f in o.get("terrestre", [])]
    for s_id in o["salidas"]:
        s = SALIDAS[s_id]
        for p_id, p in PUERTOS.items():
            tramo = LLEGADAS[(s["acceso"], p["costa"])]
            coords, pasos = _resolver([(o["lat"], o["lon"])] + s["puntos"] + [ACCESOS[s["acceso"]]] + tramo
                                      + [(p["lat"], p["lon"])])
            km_mar = sum(distancia_km(*a, *b) for a, b in zip(coords[:-1], coords[1:]))
            nm = km_mar / 1.852
            canales = sum(1 for x in pasos if x in ("panama", "suez")) * DIAS_CANAL
            mar = (nm / (NUDOS_RAPIDO * 24), nm / (NUDOS_LENTO * 24))
            camion = p["km"] / KMH_CAMION / 24
            via = [PASOS[x]["corto"] for x in pasos if x in ("panama", "suez", "cabo")]
            nombre = f"{o['nombre']} → {p['nombre']}" + (f" · vía {', '.join(via)}" if via else "")
            bloqueo = [x for x in pasos if x in cerrados]
            out.append({
                "id": f"{iso}-{s_id}-{p_id}", "nombre": nombre, "iso": iso, "salida": s_id, "salida_nombre": s["nombre"],
                "puerto": p_id, "pasos": list(dict.fromkeys(pasos)), "coords": coords, "nm": nm, "km_camion": p["km"],
                "dias_mar": (round(mar[0]), round(mar[1])),
                "dias_min": round(mar[0] + DIAS_PUERTO[0] + canales + camion),
                "dias_max": round(mar[1] + DIAS_PUERTO[1] + canales + camion + 1),
                "disponible": not bloqueo, "cerrados": bloqueo, "frontera": None, "modo": "barco",
            })
    return sorted(out, key=lambda r: (not r["disponible"], r["dias_max"], r["dias_min"]))


def _ruta_terrestre(iso: str, f_id: str) -> dict:
    """Ruta por tren: origen → cruce fronterizo → planta (no cruza pasos marítimos)."""
    o, f = PAISES[iso], FRONTERAS[f_id]
    km = f["km_origen"] + f["km"]
    horas = km / KMH_TREN / 24
    return {
        "id": f"{iso}-tierra-{f_id}", "nombre": f"{o['nombre']} → TYASA · tren vía {f['nombre']}", "iso": iso,
        "salida": None, "salida_nombre": "por tren", "puerto": None, "pasos": [],
        "coords": [(o["lat"], o["lon"]), (f["lat"], f["lon"])] + f["via"] + [(TYASA["lat"], TYASA["lon"])],
        "nm": 0, "km_camion": km, "dias_mar": (0, 0),
        "dias_min": round(horas + DIAS_FRONTERA[0]), "dias_max": round(horas * 1.5 + DIAS_FRONTERA[1]),
        "disponible": True, "cerrados": [], "frontera": f_id, "modo": "tren",
    }


# ── Tráfico ───────────────────────────────────────────────────────────────────
def estado_trafico(serie: pd.Series, ventana: int = VENTANA) -> dict:
    """serie diaria (índice fecha) -> reciente, base, cambio, estado, al."""
    s = serie.dropna().sort_index()
    vacio = {"reciente": None, "base": None, "cambio": None, "estado": "Sin datos", "al": None}
    if len(s) < ventana + HUECO + 30:
        return vacio
    fin = s.index.max()
    reciente = s[s.index > fin - pd.Timedelta(days=ventana)].mean()
    corte = fin - pd.Timedelta(days=ventana + HUECO)
    base = s[(s.index <= corte) & (s.index > corte - pd.Timedelta(days=BASE))].mean()
    if not base or pd.isna(base):
        return {**vacio, "al": fin}
    cambio = reciente / base - 1
    estado = ("Muy reducido" if cambio <= MUY_REDUCIDO else "Reducido" if cambio <= REDUCIDO
              else "Alto" if cambio >= ALTO else "Normal")
    return {"reciente": reciente, "base": base, "cambio": cambio, "estado": estado, "al": fin}


# ── Estado de los puntos de la red ────────────────────────────────────────────
def _nivel_trafico(estado: str) -> str:
    return {"Muy reducido": "riesgo", "Reducido": "vigilar", "Alto": "vigilar", "Normal": "normal"}.get(estado, "sin datos")


def estado_red(pasos_df: pd.DataFrame, puertos_df: pd.DataFrame, avisos: pd.DataFrame,
               oleaje: pd.DataFrame, tormentas: pd.DataFrame) -> pd.DataFrame:
    """Una fila por punto de la red (pasos, puertos y países con noticias):
    nodo, tipo, clave, nombre, lat, lon, trafico (estado), cambio, al, noticias,
    graves, oleaje_m, tormenta (texto), nivel y motivos (lista de (nivel, texto))."""
    filas = []
    noti = avisos.groupby("nodo") if not avisos.empty else None

    def _noticias(nodo):
        if noti is None or nodo not in noti.groups:
            return 0, 0
        g = noti.get_group(nodo)
        return len(g), int((g["severidad"] == "alta").sum())

    for k, p in PASOS.items():
        s = (pasos_df[pasos_df["paso"] == k].set_index("fecha")["transitos"] if not pasos_df.empty
             else pd.Series(dtype=float))
        filas.append({"nodo": f"paso:{k}", "tipo": "Paso marítimo", "clave": k, "nombre": p["nombre"],
                      "lat": p["lat"], "lon": p["lon"], **estado_trafico(s)})
    for k, p in PUERTOS.items():
        s = (puertos_df[puertos_df["puerto"] == k].set_index("fecha")["llamadas"] if not puertos_df.empty
             else pd.Series(dtype=float))
        filas.append({"nodo": f"puerto:{k}", "tipo": "Puerto de llegada", "clave": k, "nombre": p["nombre"],
                      "lat": p["lat"], "lon": p["lon"], **estado_trafico(s, VENTANA_PUERTO)})
    for k, f in FRONTERAS.items():
        filas.append({"nodo": f"frontera:{k}", "tipo": "Cruce fronterizo", "clave": k, "nombre": f["nombre"],
                      "lat": f["lat"], "lon": f["lon"], "reciente": None, "base": None, "cambio": None,
                      "estado": "Sin datos", "al": None})
    if not avisos.empty:
        for nodo in sorted(n for n in avisos["nodo"].unique() if n.startswith("pais:")):
            iso = nodo.split(":", 1)[1]
            o = PAISES.get(iso)
            filas.append({"nodo": nodo, "tipo": "País de origen", "clave": iso,
                          "nombre": o["nombre"] if o else avisos.loc[avisos["nodo"] == nodo, "lugar"].iloc[0],
                          "lat": o["lat"] if o else None, "lon": o["lon"] if o else None,
                          "reciente": None, "base": None, "cambio": None, "estado": "Sin datos", "al": None})
    red = pd.DataFrame(filas).rename(columns={"estado": "trafico"})

    olas = dict(zip(oleaje["puerto"], oleaje["oleaje_max_m"])) if not oleaje.empty else {}
    niveles, motivos, n_not, n_graves, ola_col, torm_col = [], [], [], [], [], []
    for r in red.itertuples():
        m, nv = [], []
        n, g = _noticias(r.nodo)
        if g:
            nv.append("riesgo"); m.append(("riesgo", f"{g} noticia{'s' if g > 1 else ''} grave{'s' if g > 1 else ''}"))
        elif n:
            nv.append("vigilar")
        if n and n > g:
            m.append(("vigilar", f"{n - g} noticia{'s' if n - g > 1 else ''} para vigilar"))
        if r.trafico != "Sin datos":
            nv.append(_nivel_trafico(r.trafico))
            if r.trafico != "Normal":
                m.append((_nivel_trafico(r.trafico), f"tráfico {r.trafico.lower()} ({r.cambio:+.0%} vs. lo normal)"))
        ola, torm = None, None
        if r.tipo == "Puerto de llegada":
            ola = olas.get(r.clave)
            if ola is not None and ola >= OLEAJE_ALTO_M:
                nv.append("vigilar"); m.append(("vigilar", f"oleaje de {ola:.1f} m en los próximos 7 días"))
            if not tormentas.empty:
                cerca = tormentas[tormentas["puerto"] == r.clave].sort_values("km")
                if not cerca.empty and cerca["km"].iloc[0] <= TORMENTA_VIGILAR_KM:
                    t = cerca.iloc[0]
                    torm = f"{t['nombre']} a {t['km']:,.0f} km"
                    nv.append("riesgo" if t["km"] <= TORMENTA_RIESGO_KM else "vigilar")
                    m.append((nv[-1], f"tormenta {t['nombre']} ({t['tipo']}) a {t['km']:,.0f} km"))
        niveles.append(peor(*nv) if nv else "sin datos")
        motivos.append(m); n_not.append(n); n_graves.append(g); ola_col.append(ola); torm_col.append(torm)
    return red.assign(nivel=niveles, motivos=motivos, noticias=n_not, graves=n_graves, oleaje_m=ola_col,
                      tormenta=torm_col)


def evaluar_ruta(ruta: dict, red: pd.DataFrame) -> dict:
    """Nivel de la ruta (peor de sus puntos), cuántas noticias la tocan y por qué."""
    nodos = [f"paso:{p}" for p in ruta["pasos"]] + [f"pais:{ruta['iso']}"]
    if ruta["puerto"]:
        nodos.append(f"puerto:{ruta['puerto']}")
    if ruta.get("frontera"):
        nodos.append(f"frontera:{ruta['frontera']}")
    r = red.set_index("nodo")
    nivel, noticias, graves, motivos = "normal", 0, 0, []
    for n in nodos:
        if n not in r.index:
            continue
        x = r.loc[n]
        nivel = peor(nivel, x["nivel"] if x["nivel"] != "sin datos" else "normal")
        noticias += int(x["noticias"]); graves += int(x["graves"])
        motivos += [(nv, f"{x['nombre']}: {t}") for nv, t in x["motivos"]]
    if not ruta["disponible"]:
        nivel = "riesgo"
        motivos.insert(0, ("riesgo", "Cruza " + ", ".join(PASOS[p]["nombre"] for p in ruta["cerrados"])
                           + ", cerrado en el escenario"))
    return {"nivel": nivel, "noticias": noticias, "graves": graves, "nodos": nodos,
            "motivos": sorted(motivos, key=lambda m: _ORDEN.get(m[0], 9))}


def matriz_calor(red: pd.DataFrame, cerrados: frozenset = frozenset(),
                 origenes: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Material × país de origen: nivel de la mejor ruta disponible (la más
    rápida que no cruza un paso cerrado). nivel = 'cerrada' si el escenario no
    deja ninguna. <origenes>: {material: [iso]} (por omisión, red.MATERIALES).
    Columnas: material, iso, pais, nivel, ruta, dias, noticias, graves."""
    from mercado_rutas.red import MATERIALES

    origenes = origenes or {m: p for m, (_, p) in MATERIALES.items()}
    filas, cache = [], {}
    for mat, paises in origenes.items():
        for iso in paises:
            if iso not in cache:
                disp = [r for r in rutas_de(iso, cerrados) if r["disponible"]]
                if disp:
                    ev = evaluar_ruta(disp[0], red)
                    cache[iso] = {"nivel": ev["nivel"], "ruta": disp[0]["nombre"],
                                  "dias": f"{disp[0]['dias_min']}–{disp[0]['dias_max']}",
                                  "noticias": ev["noticias"], "graves": ev["graves"]}
                else:
                    cache[iso] = {"nivel": "cerrada", "ruta": "Sin ruta disponible en el escenario", "dias": "—",
                                  "noticias": 0, "graves": 0}
            filas.append({"material": mat, "iso": iso, "pais": PAISES[iso]["nombre"], **cache[iso]})
    return pd.DataFrame(filas)
