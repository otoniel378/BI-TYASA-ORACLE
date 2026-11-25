"""
pages/mercado/10_rutas_puertos.py — Rutas y puertos: monitoreo de los pasos
marítimos, los puertos de llegada y las rutas de importación hacia TYASA.

Junta, por cada punto de la red (mercado_rutas/riesgo.py::estado_red):
  - tráfico real de IMF PortWatch contra lo normal (Oracle o descarga directa)
  - noticias de los últimos 21 días ligadas al lugar (rutas_alertas)
  - tormentas activas (NOAA) y oleaje pronosticado (Open-Meteo) en los puertos
Cada ruta toma el peor nivel de sus puntos; un escenario puede cerrar pasos.
Ideas tomadas del "Monitor materiales críticos" de los compañeros: barra de
escenario por paso marítimo, mapa a la izquierda y rutas a la derecha, varias
rutas por país y rutas con noticias en rojo.

Pestañas (solo se dibuja la abierta): Rutas · Pasos y puertos · Mapa de calor · Noticias.
"""

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st

from core.components.kpi_cards import seccion_titulo
from mercado_rutas.datos import load_avisos, load_oleaje, load_precios_materiales, load_tormentas, load_trafico
from mercado_rutas.red import MATERIALES, PAISES, PASOS
from mercado_rutas.riesgo import estado_red, evaluar_ruta, matriz_calor, rutas_de
from mercado_rutas.vistas import (
    detalle_nodo, detalle_ruta, estilo_red, estilo_rutas, fecha_corta, grafica_trafico, leyenda_mapa, lista_noticias,
    mapa_calor, mapa_red, tabla_red, tabla_rutas, tarjeta_precio, tarjetas_resumen, trayecto,
)

PESTANAS = ["Rutas", "Pasos y puertos", "Mapa de calor", "Noticias"]
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

# Saltos pedidos desde un clic (mapa de calor → Rutas, punto del mapa → Pasos y
# puertos): se aplican antes de crear los widgets, porque Streamlit no deja
# cambiar un widget ya creado en la misma corrida.
if "_rp_ir" in st.session_state:
    for _k, _v in st.session_state.pop("_rp_ir").items():
        st.session_state[_k] = _v

st.session_state.setdefault("rp_material", "FeCr")
st.session_state.setdefault("rp_tab", PESTANAS[0])
if st.session_state.get("rp_nodo") not in set(red["nodo"]):
    st.session_state["rp_nodo"] = tabla_red(red)["nodo"].iloc[0]


def _ir(**valores):
    st.session_state["_rp_ir"] = valores
    st.rerun()


# ---------------------------------------------------------------------------
# Encabezado, resumen y controles comunes
# ---------------------------------------------------------------------------
seccion_titulo("Rutas y puertos", "Pasos marítimos, puertos de llegada y rutas de importación hacia TYASA")
nota_origen = {"descarga": " (descargado directo; falta la carga diaria a Oracle)",
               "sin datos": " (no disponible ahora)"}.get(origen_trafico, "")
st.caption(f"Tráfico de barcos: IMF PortWatch al {fecha_corta(pasos_df['fecha'].max() if not pasos_df.empty else None)}"
           f"{nota_origen} · Noticias de los últimos 21 días · Tormentas y oleaje: en vivo")
st.html(tarjetas_resumen(red, avisos, tormentas))

c_mat, c_esc = st.columns([1, 1], gap="large")
with c_mat:
    material = st.segmented_control("Material", list(MATERIALES), key="rp_material", format_func=lambda k: k) or "FeCr"
with c_esc:
    cerrados = st.pills("Escenario · cerrar pasos marítimos", PASOS_ESCENARIO, selection_mode="multi",
                        key="rp_cerrados", format_func=lambda k: PASOS[k]["corto"]) or []
nombre_mat, paises_mat = MATERIALES[material]

tabs = st.tabs(PESTANAS, key="rp_tab", on_change="rerun")
activa = st.session_state.get("rp_tab", PESTANAS[0])

# ---------------------------------------------------------------------------
# Rutas: mapa a la izquierda, rutas y detalle a la derecha
# ---------------------------------------------------------------------------
with tabs[0]:
    if activa == "Rutas":
        st.session_state.setdefault(f"rp_pais_{material}", paises_mat[0])
        c_p, c_pr = st.columns([3, 2], gap="medium")
        with c_p:
            iso = st.pills(f"{nombre_mat} · país de origen (referencia)", paises_mat, key=f"rp_pais_{material}",
                           format_func=lambda i: PAISES[i]["nombre"]) or paises_mat[0]
        with c_pr:
            st.html(tarjeta_precio(nombre_mat, precios.get(material)))

        rutas = rutas_de(iso, frozenset(cerrados))
        for r in rutas:
            ev = evaluar_ruta(r, red)
            r.update(nivel=ev["nivel"], noticias=ev["noticias"], graves=ev["graves"], ev=ev)
        clave_ruta = f"rp_ruta_{iso}"
        ids = [r["id"] for r in rutas]
        if st.session_state.get(clave_ruta) not in ids:
            st.session_state[clave_ruta] = next((r["id"] for r in rutas if r["disponible"]), ids[0])
        ruta = next(r for r in rutas if r["id"] == st.session_state[clave_ruta])

        c_mapa, c_rutas = st.columns([3, 2], gap="medium")
        with c_mapa:
            ev_mapa = st.plotly_chart(
                mapa_red(red, rutas, ruta["id"], tormentas, None, origenes=paises_mat, iso_sel=iso, altura=470),
                width="stretch", key="rp_mapa_rutas", on_select="rerun", selection_mode="points",
                config={"scrollZoom": True, "displayModeBar": False})
            st.html(leyenda_mapa(True))
            puntos = [p for p in (ev_mapa.selection.points if ev_mapa else []) if isinstance(p.get("customdata"), str)]
            if puntos and st.session_state.get("_rp_click_rutas") != puntos[0]["customdata"]:
                st.session_state["_rp_click_rutas"] = puntos[0]["customdata"]
                _ir(rp_nodo=puntos[0]["customdata"], rp_tab="Pasos y puertos")
        with c_rutas:
            st.html(f"<div style='font-size:14px;font-weight:700;color:#1B3A5C;margin-bottom:2px;'>"
                    f"Rutas desde {PAISES[iso]['nombre']}</div><div style='font-size:12px;color:#6B7280;'>"
                    f"Sale de {PAISES[iso]['puerto']} · de la más rápida a la más lenta · rojo claro: con noticias</div>")
            sel_r = st.dataframe(estilo_rutas(tabla_rutas(rutas), rutas), hide_index=True, width="stretch",
                                 height=min(35 * len(rutas) + 38, 250), on_select="rerun",
                                 selection_mode="single-row", key=f"rp_tabla_rutas_{iso}")
            filas_r = sel_r.selection.rows if sel_r else []
            if filas_r and rutas[filas_r[0]]["id"] != st.session_state[clave_ruta]:
                st.session_state[clave_ruta] = rutas[filas_r[0]]["id"]
                st.rerun()
            with st.container(border=True):
                st.html(detalle_ruta(ruta))

        st.html(trayecto(ruta, red))
        noticias_ruta = avisos[avisos["nodo"].isin(ruta["ev"]["nodos"])] if not avisos.empty else avisos
        if not noticias_ruta.empty:
            with st.expander(f"Noticias en los puntos de esta ruta ({len(noticias_ruta)})"):
                st.html(lista_noticias(noticias_ruta, n=20, con_lugar=True))

# ---------------------------------------------------------------------------
# Pasos y puertos: mapa de la red y tabla a la izquierda, detalle a la derecha
# ---------------------------------------------------------------------------
with tabs[1]:
    if activa == "Pasos y puertos":
        c_red, c_det = st.columns([3, 2], gap="medium")
        with c_red:
            ev_red = st.plotly_chart(mapa_red(red, tormentas=tormentas, nodo_sel=st.session_state["rp_nodo"], altura=360),
                                     width="stretch", key="rp_mapa_red", on_select="rerun", selection_mode="points",
                                     config={"scrollZoom": True, "displayModeBar": False})
            st.html(leyenda_mapa(False))
            puntos = [p for p in (ev_red.selection.points if ev_red else []) if isinstance(p.get("customdata"), str)]
            if puntos and st.session_state.get("_rp_click_red") != puntos[0]["customdata"]:
                st.session_state["_rp_click_red"] = puntos[0]["customdata"]
                st.session_state["rp_nodo"] = puntos[0]["customdata"]
            tabla = tabla_red(red)
            sel = st.dataframe(estilo_red(tabla), hide_index=True, width="stretch", height=300,
                               on_select="rerun", selection_mode="single-row", key="rp_tabla_red")
            filas = sel.selection.rows if sel else []
            if filas and st.session_state.get("_rp_fila_red") != tabla["nodo"].iloc[filas[0]]:
                st.session_state["_rp_fila_red"] = tabla["nodo"].iloc[filas[0]]
                st.session_state["rp_nodo"] = tabla["nodo"].iloc[filas[0]]
            st.caption("Tráfico: barcos de los últimos 14 días (puertos: 30) contra el promedio de los 3 meses previos.")
        with c_det:
            nodo = st.session_state["rp_nodo"]
            fila = red.set_index("nodo").loc[nodo].copy()
            with st.container(border=True):
                if fila["tipo"] in ("Paso marítimo", "Puerto de llegada"):
                    paso = fila["tipo"] == "Paso marítimo"
                    df, col, campo = (pasos_df, "paso", "transitos") if paso else (puertos_df, "puerto", "llamadas")
                    s = df[df[col] == fila["clave"]].set_index("fecha")[campo]
                    st.plotly_chart(grafica_trafico(s, fila.to_dict(), "Barcos que cruzan al día" if paso
                                                    else "Barcos que llegan al día", "barcos"),
                                    width="stretch", key="rp_graf_nodo", config={"displayModeBar": False})
                avisos_nodo = avisos[avisos["nodo"] == nodo] if not avisos.empty else avisos
                st.html(detalle_nodo(fila, avisos_nodo, n=4))
                if len(avisos_nodo) > 4:
                    with st.expander(f"Ver las otras {len(avisos_nodo) - 4} noticias"):
                        st.html(lista_noticias(avisos_nodo.sort_values(["severidad", "fecha"],
                                                                       ascending=[True, False]).iloc[4:], n=20))

# ---------------------------------------------------------------------------
# Mapa de calor: material × país de origen
# ---------------------------------------------------------------------------
with tabs[2]:
    if activa == "Mapa de calor":
        st.caption("Estado de la mejor ruta desde cada país" + (" con el escenario aplicado" if cerrados else "")
                   + " · columna Precio: semáforo de alza · clic en una celda para ver sus rutas")
        nombres = {k: v[0] for k, v in MATERIALES.items()}
        iso_actual = st.session_state.get(f"rp_pais_{material}", paises_mat[0])
        ev_calor = st.plotly_chart(mapa_calor(matriz_calor(red, frozenset(cerrados)), precios, nombres,
                                              (material, iso_actual)),
                                   width="stretch", key="rp_calor", on_select="rerun", selection_mode="points",
                                   config={"displayModeBar": False})
        st.caption("✓ normal · ● vigilar · ▲ riesgo · ✕ sin ruta en el escenario · gris: no es origen de ese material")
        celdas = [p for p in (ev_calor.selection.points if ev_calor else []) if p.get("customdata")]
        if celdas:
            _mat, _iso = celdas[0]["customdata"][:2]
            if st.session_state.get("_rp_ultima_celda") != (_mat, _iso):
                st.session_state["_rp_ultima_celda"] = (_mat, _iso)
                destino = {"rp_material": _mat, "rp_tab": "Rutas"}
                if _iso:
                    destino[f"rp_pais_{_mat}"] = _iso
                _ir(**destino)

# ---------------------------------------------------------------------------
# Noticias de todos los puntos de la red
# ---------------------------------------------------------------------------
with tabs[3]:
    if activa == "Noticias":
        if avisos.empty:
            st.info("Sin noticias ligadas a pasos marítimos, países de origen o puertos en los últimos 21 días.")
        else:
            c_f1, c_f2 = st.columns([1, 2])
            with c_f1:
                solo_graves = st.segmented_control("Mostrar", ["Todas", "Solo graves"], default="Todas",
                                                   key="rp_not_graves") == "Solo graves"
            with c_f2:
                tipos = st.pills("Lugar", ["Pasos marítimos", "Países de origen", "Puertos de llegada"],
                                 selection_mode="multi", key="rp_not_tipos",
                                 default=["Pasos marítimos", "Países de origen", "Puertos de llegada"])
            prefijo = {"Pasos marítimos": "paso:", "Países de origen": "pais:", "Puertos de llegada": "puerto:"}
            v = avisos[avisos["nodo"].str.startswith(tuple(prefijo[t] for t in tipos))] if tipos else avisos.iloc[0:0]
            if solo_graves:
                v = v[v["severidad"] == "alta"]
            orden = (v.assign(_g=v["severidad"].eq("alta")).groupby("lugar")["_g"].sum()
                     .sort_values(ascending=False).index.tolist())
            st.caption(f"{v['titulo'].nunique()} noticias en {len(orden)} lugares · las graves primero")
            col_a, col_b = st.columns(2, gap="medium")
            for i, lugar in enumerate(orden):
                g = v[v["lugar"] == lugar]
                with (col_a if i % 2 == 0 else col_b):
                    with st.container(border=True):
                        graves = int((g["severidad"] == "alta").sum())
                        st.html(f"<div style='font-size:14px;font-weight:700;color:#1B3A5C;'>{lugar}"
                                f"<span style='font-size:12px;font-weight:500;color:#6B7280;'> · {len(g)} noticias"
                                + (f", {graves} graves" if graves else "") + "</span></div>"
                                + lista_noticias(g, n=3))
                        if len(g) > 3:
                            with st.expander(f"Ver las otras {len(g) - 3}"):
                                st.html(lista_noticias(g.sort_values(["severidad", "fecha"],
                                                                     ascending=[True, False]).iloc[3:], n=20))

st.caption("Fuentes: IMF PortWatch (tráfico de barcos), noticias clasificadas del sistema, NOAA (tormentas), "
           "Open-Meteo (oleaje). Orígenes, distancias y días son de referencia.")
