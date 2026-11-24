"""
pages/mercado/10_rutas_puertos.py — Rutas y puertos: monitoreo de los pasos
marítimos, los puertos de llegada y las rutas de importación hacia TYASA.

Junta, por cada punto de la red (mercado_rutas/riesgo.py::estado_red):
  - tráfico real de IMF PortWatch contra lo normal (Oracle o descarga directa)
  - noticias de los últimos 21 días ligadas al lugar (rutas_alertas)
  - tormentas activas (NOAA) y oleaje pronosticado (Open-Meteo) en los puertos
Cada ruta toma el peor nivel de sus puntos; un escenario puede cerrar pasos.
Ideas tomadas del "Monitor materiales críticos" de los compañeros: barra de
escenario por paso marítimo, varias rutas por país y rutas con noticias en rojo.
"""

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
from config import COLORS

from core.components.kpi_cards import seccion_titulo
from mercado_rutas.datos import load_avisos, load_oleaje, load_precios_materiales, load_tormentas, load_trafico
from mercado_rutas.red import MATERIALES, PAISES, PASOS
from mercado_rutas.riesgo import estado_red, evaluar_ruta, matriz_calor, rutas_de
from mercado_rutas.vistas import (
    chip, detalle_nodo, estilo_rutas, fecha_corta, grafica_trafico, lista_noticias, mapa_calor, mapa_red, motivos_ruta,
    tabla_red, tabla_rutas, tarjeta_precio, tarjetas_resumen, trayecto,
)

# Pasos de la barra de escenario (los mismos que el monitor de los compañeros)
PASOS_ESCENARIO = ["suez", "bab", "hormuz", "panama", "malaca", "gibraltar", "mancha", "bos"]

# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
pasos_df, puertos_df, origen_trafico = load_trafico()
avisos = load_avisos()
tormentas = load_tormentas()
oleaje = load_oleaje()
red = estado_red(pasos_df, puertos_df, avisos, oleaje, tormentas)
precios = load_precios_materiales()

# Clic en el mapa de calor (al final de la página): se aplica aquí, antes de
# crear los selectores, porque Streamlit no deja cambiar un widget ya creado.
if "_rp_ir" in st.session_state:
    _mat, _iso = st.session_state.pop("_rp_ir")
    st.session_state["rp_material"] = _mat
    if _iso:
        st.session_state[f"rp_pais_{_mat}"] = _iso

seccion_titulo("Rutas y puertos", "Pasos marítimos, puertos de llegada y rutas de importación hacia TYASA")
al_trafico = pasos_df["fecha"].max() if not pasos_df.empty else None
nota_origen = {"descarga": " (descargado directo; falta la carga diaria a Oracle)",
               "sin datos": " (no disponible ahora)"}.get(origen_trafico, "")
st.caption(f"Tráfico de barcos: IMF PortWatch al {fecha_corta(al_trafico)}{nota_origen} · Noticias de los últimos 21 días · "
           f"Tormentas y oleaje: en vivo")
st.html(tarjetas_resumen(red, avisos, tormentas))

# ---------------------------------------------------------------------------
# Material, país y escenario
# ---------------------------------------------------------------------------
st.html("<div style='height:6px'></div>")
c_mat, c_esc = st.columns([3, 2])
with c_mat:
    # Valor inicial por session_state (no default=): el mapa de calor también los cambia
    st.session_state.setdefault("rp_material", "FeCr")
    material = st.segmented_control("Material", list(MATERIALES), key="rp_material", format_func=lambda k: k) or "FeCr"
    nombre_mat, paises_mat = MATERIALES[material]
    st.session_state.setdefault(f"rp_pais_{material}", paises_mat[0])
    iso = st.pills(f"{nombre_mat} · país de origen", paises_mat, key=f"rp_pais_{material}",
                   format_func=lambda i: PAISES[i]["nombre"]) or paises_mat[0]
    st.html(tarjeta_precio(nombre_mat, precios.get(material)))
with c_esc:
    cerrados = st.pills("Escenario · cerrar pasos marítimos", PASOS_ESCENARIO, selection_mode="multi",
                        key="rp_cerrados", format_func=lambda k: PASOS[k]["corto"]) or []
    st.caption("Las rutas que cruzan un paso cerrado quedan fuera; se muestran las alternativas.")

rutas = rutas_de(iso, frozenset(cerrados))
for r in rutas:
    ev = evaluar_ruta(r, red)
    r.update(nivel=ev["nivel"], noticias=ev["noticias"], graves=ev["graves"], ev=ev)

# Ruta elegida: la que se seleccionó en la tabla, o la mejor disponible
clave_ruta = f"rp_ruta_{iso}"
ids = [r["id"] for r in rutas]
if st.session_state.get(clave_ruta) not in ids:
    st.session_state[clave_ruta] = next((r["id"] for r in rutas if r["disponible"]), ids[0])
ruta = next(r for r in rutas if r["id"] == st.session_state[clave_ruta])

# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------
if "rp_nodo" not in st.session_state or st.session_state["rp_nodo"] not in set(red["nodo"]):
    st.session_state["rp_nodo"] = tabla_red(red)["nodo"].iloc[0]
evento = st.plotly_chart(
    mapa_red(red, rutas, ruta["id"], tormentas, st.session_state["rp_nodo"]),
    width="stretch", key="rp_mapa", on_select="rerun", selection_mode="points",
    config={"scrollZoom": True, "displayModeBar": False},
)
st.caption("◆ paso marítimo · ● puerto de llegada · ■ país con noticias · ★ TYASA · "
           "verde normal, naranja vigilar, rojo riesgo · línea: rutas del país elegido (punteada si queda cerrada)")
puntos = [p for p in (evento.selection.points if evento else []) if p.get("customdata")]
if puntos:
    nodo_click = puntos[0]["customdata"]
    if st.session_state.get("_rp_ultimo_click") != nodo_click:
        st.session_state["_rp_ultimo_click"] = nodo_click
        st.session_state["rp_nodo"] = nodo_click

# ---------------------------------------------------------------------------
# Estado de la red
# ---------------------------------------------------------------------------
seccion_titulo("Estado de pasos y puertos", "Clic en una fila o en el mapa para ver el detalle")
col_t, col_d = st.columns([3, 2])
with col_t:
    tabla = tabla_red(red)
    sel = st.dataframe(tabla.drop(columns="nodo"), hide_index=True, width="stretch", height=420,
                       on_select="rerun", selection_mode="single-row", key="rp_tabla_red")
    filas = sel.selection.rows if sel else []
    if filas:
        nodo_tabla = tabla["nodo"].iloc[filas[0]]
        if st.session_state.get("_rp_ultima_fila") != nodo_tabla:
            st.session_state["_rp_ultima_fila"] = nodo_tabla
            st.session_state["rp_nodo"] = nodo_tabla
    st.caption("Tráfico: barcos de los últimos 14 días (puertos: 30) contra el promedio normal de los 3 meses previos.")

with col_d:
    nodo = st.session_state["rp_nodo"]
    fila = red.set_index("nodo").loc[nodo]
    fila["nodo"] = nodo
    with st.container(border=True):
        if fila["tipo"] == "Paso marítimo":
            s = pasos_df[pasos_df["paso"] == fila["clave"]].set_index("fecha")["transitos"]
            st.plotly_chart(grafica_trafico(s, fila.to_dict(), "Barcos que cruzan al día", "barcos"),
                            width="stretch", key="rp_graf_nodo", config={"displayModeBar": False})
        elif fila["tipo"] == "Puerto de llegada":
            s = puertos_df[puertos_df["puerto"] == fila["clave"]].set_index("fecha")["llamadas"]
            st.plotly_chart(grafica_trafico(s, fila.to_dict(), "Barcos que llegan al día", "barcos"),
                            width="stretch", key="rp_graf_nodo", config={"displayModeBar": False})
        avisos_nodo = avisos[avisos["nodo"] == nodo] if not avisos.empty else avisos
        st.html(detalle_nodo(fila, avisos_nodo, n=4))
        if len(avisos_nodo) > 4:
            with st.expander(f"Ver las otras {len(avisos_nodo) - 4} noticias"):
                st.html(lista_noticias(avisos_nodo.sort_values(["severidad", "fecha"], ascending=[True, False]).iloc[4:],
                                       n=20))

# ---------------------------------------------------------------------------
# Rutas del país elegido
# ---------------------------------------------------------------------------
o = PAISES[iso]
seccion_titulo(f"Rutas desde {o['nombre']}",
               f"{nombre_mat} · sale de {o['puerto']} · origen de referencia, no el proveedor real")
col_r, col_rd = st.columns([3, 2])
with col_r:
    df_rutas = tabla_rutas(rutas)
    sel_r = st.dataframe(estilo_rutas(df_rutas, rutas), hide_index=True, width="stretch",
                         height=min(35 * len(rutas) + 38, 460), on_select="rerun", selection_mode="single-row",
                         key=f"rp_tabla_rutas_{iso}")
    filas_r = sel_r.selection.rows if sel_r else []
    if filas_r and rutas[filas_r[0]]["id"] != st.session_state[clave_ruta]:
        st.session_state[clave_ruta] = rutas[filas_r[0]]["id"]
        st.rerun()
    st.caption("Ordenadas de la más rápida a la más lenta · rojo claro: la ruta tiene noticias en alguno de sus puntos "
               "(más intenso si alguna es grave) · clic para ver el detalle")

with col_rd:
    with st.container(border=True):
        disponible = "" if ruta["disponible"] else chip("riesgo", "Cerrada en el escenario")
        st.html(
            f"<div style='display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap;'>"
            f"<span style='font-size:16px;font-weight:700;color:{COLORS['primary']};'>{ruta['nombre']}</span>"
            f"<span style='font-size:22px;font-weight:700;color:{COLORS['primary']};font-variant-numeric:tabular-nums;'>"
            f"{ruta['dias_min']}–{ruta['dias_max']} d</span></div>"
            f"<div style='display:flex;gap:6px;margin:6px 0 10px;flex-wrap:wrap;'>{chip(ruta['nivel'])}{disponible}"
            f"<span style='font-size:12px;color:{COLORS['text_light']};'>puerta a puerta · estimado</span></div>"
            + motivos_ruta(ruta["ev"]))

st.html("<div style='height:8px'></div>")
st.html(trayecto(ruta, red))

noticias_ruta = avisos[avisos["nodo"].isin(ruta["ev"]["nodos"])] if not avisos.empty else avisos
if not noticias_ruta.empty:
    with st.expander(f"Noticias en los puntos de esta ruta ({len(noticias_ruta)})", expanded=bool(ruta["graves"])):
        st.html(lista_noticias(noticias_ruta, n=20))

# ---------------------------------------------------------------------------
# Mapa de calor: material × país de origen
# ---------------------------------------------------------------------------
seccion_titulo("Mapa de calor: material × origen",
               "Estado de la mejor ruta desde cada país" + (" con el escenario aplicado" if cerrados else "")
               + " · columna Precio: semáforo de alza · clic en una celda para ver sus rutas")
nombres = {k: v[0] for k, v in MATERIALES.items()}
evento_calor = st.plotly_chart(mapa_calor(matriz_calor(red, frozenset(cerrados)), precios, nombres, (material, iso)),
                               width="stretch", key="rp_calor", on_select="rerun", selection_mode="points",
                               config={"displayModeBar": False})
st.caption("✓ normal · ● vigilar · ▲ riesgo · ✕ sin ruta en el escenario · celda gris: no es origen de ese material")
celdas = [p for p in (evento_calor.selection.points if evento_calor else []) if p.get("customdata")]
if celdas:
    _mat, _iso = celdas[0]["customdata"][:2]
    if st.session_state.get("_rp_ultima_celda") != (_mat, _iso):
        st.session_state["_rp_ultima_celda"] = (_mat, _iso)
        if (_mat, _iso or iso) != (material, iso):
            st.session_state["_rp_ir"] = (_mat, _iso)
            st.rerun()

st.caption("Fuentes: IMF PortWatch (tráfico de barcos), noticias clasificadas del sistema, NOAA (tormentas), "
           "Open-Meteo (oleaje). Orígenes, distancias y días son de referencia.")
