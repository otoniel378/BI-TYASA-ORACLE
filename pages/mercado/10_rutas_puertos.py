"""
pages/mercado/10_rutas_puertos.py — Rutas y puertos: monitoreo de los pasos
marítimos, los puertos de llegada, el cruce fronterizo y las rutas de
importación hacia TYASA de ferroaleaciones, insumos indirectos y chatarra.

Junta, por cada punto de la red (mercado_rutas/riesgo.py::estado_red):
  - tráfico real de IMF PortWatch contra lo normal (Oracle o descarga directa)
  - noticias de los últimos 21 días ligadas al lugar (rutas_alertas)
  - tormentas activas (NOAA) y oleaje pronosticado (Open-Meteo) en los puertos
Cada ruta toma el peor nivel de sus puntos; un escenario puede cerrar pasos.
Ideas tomadas del "Monitor materiales críticos" de los compañeros: barra de
escenario, mapa a la izquierda y rutas a la derecha, varias rutas por país,
comparar rutas, insumos indirectos, chatarra y proveedores.

Pestañas (solo se dibuja la abierta): Rutas · Comparar rutas · Pasos y puertos ·
Mapa de calor · Noticias · Proveedores.
"""

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd
import streamlit as st

from core.auth import get_usuario
from core.components.kpi_cards import seccion_titulo
from mercado_rutas import proveedores
from mercado_rutas.datos import load_avisos, load_oleaje, load_precios_materiales, load_tormentas, load_trafico
from mercado_rutas.red import GRUPOS, MATERIALES, PAISES, PASOS
from mercado_rutas.riesgo import estado_red, evaluar_ruta, matriz_calor, rutas_de
from mercado_rutas.vistas import (
    CONFIG_MAPA, ETIQUETA_NIVEL, ICONO_NIVEL, VISTAS_MAPA, detalle_nodo, detalle_ruta, estilo_red, estilo_rutas,
    fecha_corta, grafica_comparar, grafica_trafico, leyenda_mapa, lista_noticias, mapa_calor, mapa_comparar, mapa_red,
    tabla_red, tabla_rutas, tarjeta_precio, tarjetas_comparar, tarjetas_resumen, trayecto,
)

PESTANAS = {
    "rutas": ":material/route: Rutas",
    "comparar": ":material/compare_arrows: Comparar rutas",
    "red": ":material/anchor: Pasos y puertos",
    "calor": ":material/grid_view: Mapa de calor",
    "noticias": ":material/newspaper: Noticias",
    "proveedores": ":material/storefront: Proveedores",
}
ICONO_GRUPO = {"Ferroaleaciones": ":material/science:", "Insumos indirectos": ":material/category:",
               "Chatarra": ":material/recycling:"}
# Pasos de la barra de escenario (los mismos que el monitor de los compañeros)
PASOS_ESCENARIO = ["suez", "bab", "hormuz", "panama", "malaca", "gibraltar", "mancha", "bos"]
GRUPO_DE = {m: g for g, mats in GRUPOS.items() for m in mats}

# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
pasos_df, puertos_df, origen_trafico = load_trafico()
avisos = load_avisos()
tormentas = load_tormentas()
oleaje = load_oleaje()
red = estado_red(pasos_df, puertos_df, avisos, oleaje, tormentas)
precios = load_precios_materiales()
prov, prov_en_oracle = proveedores.cargar()

# Saltos pedidos desde un clic (mapa de calor → Rutas, punto del mapa → Pasos y
# puertos, proveedor → sus rutas): se aplican antes de crear los widgets,
# porque Streamlit no deja cambiar un widget ya creado en la misma corrida.
if "_rp_ir" in st.session_state:
    for _k, _v in st.session_state.pop("_rp_ir").items():
        st.session_state[_k] = _v

st.session_state.setdefault("rp_grupo", "Ferroaleaciones")
for _g, _mats in GRUPOS.items():
    st.session_state.setdefault(f"rp_mat_{_g}", _mats[0] if _g != "Ferroaleaciones" else "FeCr")
st.session_state.setdefault("rp_tab", PESTANAS["rutas"])
if st.session_state.get("rp_nodo") not in set(red["nodo"]):
    st.session_state["rp_nodo"] = tabla_red(red)["nodo"].iloc[0]


def _ir(**valores):
    st.session_state["_rp_ir"] = valores
    st.rerun()


def _a_rutas(material: str, iso: str | None = None) -> dict:
    """Valores para saltar a la pestaña Rutas con un material (y país) elegido."""
    g = GRUPO_DE[material]
    d = {"rp_grupo": g, f"rp_mat_{g}": material, "rp_tab": PESTANAS["rutas"]}
    if iso:
        d[f"rp_pais_{material}"] = iso
    return d


def _origenes(material: str) -> list[str]:
    return proveedores.origenes(material, MATERIALES[material][1], prov)


def _con_estado(rutas: list[dict]) -> list[dict]:
    for r in rutas:
        ev = evaluar_ruta(r, red)
        r.update(nivel=ev["nivel"], noticias=ev["noticias"], graves=ev["graves"], ev=ev)
    return rutas


# ---------------------------------------------------------------------------
# Encabezado, resumen y controles comunes
# ---------------------------------------------------------------------------
seccion_titulo("Rutas y puertos", "Pasos marítimos, puertos, cruce fronterizo y rutas de importación hacia TYASA")
nota_origen = {"descarga": " (descargado directo; falta la carga diaria a Oracle)",
               "sin datos": " (no disponible ahora)"}.get(origen_trafico, "")
st.caption(f"Tráfico de barcos: IMF PortWatch al {fecha_corta(pasos_df['fecha'].max() if not pasos_df.empty else None)}"
           f"{nota_origen} · Noticias de los últimos 21 días · Tormentas y oleaje: en vivo")
st.html(tarjetas_resumen(red, avisos, tormentas))

c_mat, c_esc = st.columns([1, 1], gap="large")
with c_mat:
    grupo = st.segmented_control("Insumo", list(GRUPOS), key="rp_grupo",
                                 format_func=lambda g: f"{ICONO_GRUPO[g]} {g}") or "Ferroaleaciones"
    material = st.segmented_control("Material", GRUPOS[grupo], key=f"rp_mat_{grupo}",
                                    label_visibility="collapsed") or GRUPOS[grupo][0]
with c_esc:
    cerrados = st.pills("Escenario · cerrar pasos marítimos", PASOS_ESCENARIO, selection_mode="multi",
                        key="rp_cerrados", format_func=lambda k: PASOS[k]["corto"]) or []
nombre_mat = MATERIALES[material][0]
paises_mat = _origenes(material)
reales = set(prov.loc[prov["material"] == material, "pais_iso"]) if not prov.empty else set()

tabs = st.tabs(list(PESTANAS.values()), key="rp_tab", on_change="rerun")
activa = st.session_state.get("rp_tab", PESTANAS["rutas"])

# ---------------------------------------------------------------------------
# Rutas: mapa a la izquierda, rutas y detalle a la derecha
# ---------------------------------------------------------------------------
with tabs[0]:
    if activa == PESTANAS["rutas"]:
        st.session_state.setdefault(f"rp_pais_{material}", paises_mat[0])
        c_p, c_pr = st.columns([3, 2], gap="medium")
        with c_p:
            iso = st.pills(f"{nombre_mat} · país de origen", paises_mat, key=f"rp_pais_{material}",
                           format_func=lambda i: PAISES[i]["nombre"] + (" · proveedor" if i in reales else "")
                           ) or paises_mat[0]
        with c_pr:
            st.html(tarjeta_precio(nombre_mat, precios.get(material)))

        rutas = _con_estado(rutas_de(iso, frozenset(cerrados)))
        principal, prov_principal = proveedores.ruta_principal(material, iso, prov)
        clave_ruta = f"rp_ruta_{iso}"
        ids = [r["id"] for r in rutas]
        if st.session_state.get(clave_ruta) not in ids:
            st.session_state[clave_ruta] = (principal if principal in ids
                                            else next((r["id"] for r in rutas if r["disponible"]), ids[0]))
        ruta = next(r for r in rutas if r["id"] == st.session_state[clave_ruta])

        c_mapa, c_rutas = st.columns([3, 2], gap="medium")
        with c_mapa:
            c_v, c_ayuda = st.columns([2, 3])
            with c_v:
                vista = st.segmented_control("Acercar a", VISTAS_MAPA, key="rp_vista", default="Ruta",
                                             label_visibility="collapsed") or "Ruta"
            with c_ayuda:
                st.caption("Acerca con + / − o la rueda del ratón · **Ver recorrido** anima la ruta")
            ev_mapa = st.plotly_chart(
                mapa_red(red, rutas, ruta["id"], tormentas, None, origenes=paises_mat, iso_sel=iso, altura=440,
                         vista=vista, animar=True),
                width="stretch", key="rp_mapa_rutas", on_select="rerun", selection_mode="points", config=CONFIG_MAPA)
            st.html(leyenda_mapa(True))
            puntos = [p for p in (ev_mapa.selection.points if ev_mapa else []) if isinstance(p.get("customdata"), str)]
            if puntos and st.session_state.get("_rp_click_rutas") != puntos[0]["customdata"]:
                st.session_state["_rp_click_rutas"] = puntos[0]["customdata"]
                _ir(rp_nodo=puntos[0]["customdata"], rp_tab=PESTANAS["red"])
        with c_rutas:
            st.html(f"<div style='font-size:14px;font-weight:700;color:#1B3A5C;margin-bottom:2px;'>"
                    f"Rutas desde {PAISES[iso]['nombre']}</div><div style='font-size:12px;color:#6B7280;'>"
                    f"Sale de {PAISES[iso]['puerto']} · de la más rápida a la más lenta · rojo claro: con noticias</div>")
            sel_r = st.dataframe(estilo_rutas(tabla_rutas(rutas, principal), rutas), hide_index=True, width="stretch",
                                 height=min(35 * len(rutas) + 38, 250), on_select="rerun",
                                 selection_mode="single-row", key=f"rp_tabla_rutas_{iso}")
            filas_r = sel_r.selection.rows if sel_r else []
            if filas_r and rutas[filas_r[0]]["id"] != st.session_state[clave_ruta]:
                st.session_state[clave_ruta] = rutas[filas_r[0]]["id"]
                st.rerun()
            with st.container(border=True):
                st.html(detalle_ruta(ruta, prov_principal if ruta["id"] == principal else None))

        with st.container(border=True):
            st.html(trayecto(ruta, red))
        noticias_ruta = avisos[avisos["nodo"].isin(ruta["ev"]["nodos"])] if not avisos.empty else avisos
        if not noticias_ruta.empty:
            with st.expander(f"Noticias en los puntos de esta ruta ({len(noticias_ruta)})"):
                st.html(lista_noticias(noticias_ruta, n=20, con_lugar=True))

# ---------------------------------------------------------------------------
# Comparar rutas: hasta 4 rutas del material, lado a lado
# ---------------------------------------------------------------------------
with tabs[1]:
    if activa == PESTANAS["comparar"]:
        todas, mejores = {}, []
        for i in paises_mat:
            rs_i = rutas_de(i, frozenset(cerrados))
            todas.update({r["id"]: r for r in rs_i})
            disp = [r for r in rs_i if r["disponible"]]
            if disp:
                mejores.append(disp[0]["id"])
        clave_cmp = f"rp_cmp_{material}"
        if not set(st.session_state.get(clave_cmp) or []) <= set(todas):
            st.session_state.pop(clave_cmp, None)
        # por omisión: la mejor ruta disponible de los primeros 3 países
        st.session_state.setdefault(clave_cmp, mejores[:3])
        elegidas = st.multiselect(f"Rutas de {nombre_mat} a comparar (hasta 4)", list(todas), key=clave_cmp,
                                  max_selections=4, format_func=lambda k: todas[k]["nombre"],
                                  placeholder="Elige rutas de cualquier país de origen")
        if not elegidas:
            st.info("Elige al menos una ruta para comparar.")
        else:
            rs = _con_estado([dict(todas[k]) for k in elegidas])
            st.html(tarjetas_comparar(rs))
            c_g, c_m = st.columns([2, 3], gap="medium")
            with c_g:
                st.plotly_chart(grafica_comparar(rs), width="stretch", key="rp_cmp_graf",
                                config={"displayModeBar": False})
                st.caption("Días estimados, de la salida a la planta. Color = estado de la ruta.")
            with c_m:
                st.plotly_chart(mapa_comparar(rs, red), width="stretch", key="rp_cmp_mapa", config=CONFIG_MAPA)

# ---------------------------------------------------------------------------
# Pasos y puertos: mapa de la red y tabla a la izquierda, detalle a la derecha
# ---------------------------------------------------------------------------
with tabs[2]:
    if activa == PESTANAS["red"]:
        c_red, c_det = st.columns([3, 2], gap="medium")
        with c_red:
            ev_red = st.plotly_chart(mapa_red(red, tormentas=tormentas, nodo_sel=st.session_state["rp_nodo"], altura=360),
                                     width="stretch", key="rp_mapa_red", on_select="rerun", selection_mode="points",
                                     config=CONFIG_MAPA)
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
            st.caption("Tráfico: barcos de los últimos 14 días (puertos: 30) contra el promedio de los 3 meses previos. "
                       "El cruce fronterizo se vigila solo con noticias.")
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
# Mapa de calor: material × país de origen (del grupo elegido)
# ---------------------------------------------------------------------------
with tabs[3]:
    if activa == PESTANAS["calor"]:
        st.caption(f"{grupo}: estado de la mejor ruta desde cada país"
                   + (" con el escenario aplicado" if cerrados else "")
                   + (" · columna Precio: semáforo de alza" if grupo == "Ferroaleaciones" else
                      " · sin semáforo de precio (pasa el cursor por Precio para ver el último)")
                   + " · clic en una celda para ver sus rutas")
        nombres = {k: v[0] for k, v in MATERIALES.items()}
        iso_actual = st.session_state.get(f"rp_pais_{material}", paises_mat[0])
        matriz = matriz_calor(red, frozenset(cerrados), {m: _origenes(m) for m in GRUPOS[grupo]})
        fig_calor = mapa_calor(matriz, precios, nombres, (material, iso_actual))
        ev_calor = st.plotly_chart(fig_calor, width="content" if fig_calor.layout.width else "stretch",
                                   key=f"rp_calor_{grupo}", on_select="rerun",
                                   selection_mode="points", config={"displayModeBar": False})
        st.caption(" · ".join(f"{ICONO_NIVEL[n]} {ETIQUETA_NIVEL[n].lower()}" for n in ("normal", "vigilar", "riesgo"))
                   + " · ✕ sin ruta en el escenario · gris: no es origen de ese material")
        celdas = [p for p in (ev_calor.selection.points if ev_calor else []) if p.get("customdata")]
        if celdas:
            _mat, _iso = celdas[0]["customdata"][:2]
            if st.session_state.get("_rp_ultima_celda") != (_mat, _iso):
                st.session_state["_rp_ultima_celda"] = (_mat, _iso)
                _ir(**_a_rutas(_mat, _iso or None))

# ---------------------------------------------------------------------------
# Noticias de todos los puntos de la red
# ---------------------------------------------------------------------------
with tabs[4]:
    if activa == PESTANAS["noticias"]:
        if avisos.empty:
            st.info("Sin noticias ligadas a pasos marítimos, países de origen, puertos o cruces en los últimos 21 días.")
        else:
            tipos_lugar = {"Pasos marítimos": "paso:", "Países de origen": "pais:", "Puertos de llegada": "puerto:",
                           "Cruce fronterizo": "frontera:"}
            c_f1, c_f2 = st.columns([1, 2])
            with c_f1:
                solo_graves = st.segmented_control("Mostrar", ["Todas", "Solo graves"], default="Todas",
                                                   key="rp_not_graves") == "Solo graves"
            with c_f2:
                tipos = st.pills("Lugar", list(tipos_lugar), selection_mode="multi", key="rp_not_tipos",
                                 default=list(tipos_lugar))
            v = (avisos[avisos["nodo"].str.startswith(tuple(tipos_lugar[t] for t in tipos))] if tipos
                 else avisos.iloc[0:0])
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

# ---------------------------------------------------------------------------
# Proveedores reales: registrar y consultar
# ---------------------------------------------------------------------------
with tabs[5]:
    if activa == PESTANAS["proveedores"]:
        if not prov_en_oracle:
            st.warning("Los proveedores se guardan solo mientras esta sesión esté abierta: falta crear su tabla "
                       "(`python scripts/setup_proveedores_oracle.py`).")
        c_form, c_lista = st.columns([2, 3], gap="large")
        with c_form:
            with st.container(border=True):
                st.html("<div style='font-size:15px;font-weight:700;color:#1B3A5C;'>Registrar proveedor</div>"
                        "<div style='font-size:12px;color:#6B7280;'>Su país se suma a los orígenes del material "
                        "y su ruta principal se marca en Rutas.</div>")
                todos_mats = [m for g in GRUPOS.values() for m in g]
                st.session_state.setdefault("rp_prov_mat", material)
                p_mat = st.selectbox("Material", todos_mats, key="rp_prov_mat",
                                     format_func=lambda m: f"{m} · {MATERIALES[m][0]}")
                p_nombre = st.text_input("Proveedor", key="rp_prov_nombre", placeholder="Nombre de la empresa")
                isos = sorted(PAISES, key=lambda i: PAISES[i]["nombre"])
                ref = MATERIALES[p_mat][1]
                p_iso = st.selectbox("País de origen", isos, index=isos.index(ref[0]), key=f"rp_prov_pais_{p_mat}",
                                     format_func=lambda i: PAISES[i]["nombre"] + ("" if i in ref else " · otro origen"))
                rutas_p = _con_estado(rutas_de(p_iso))
                nombres_r = {r["id"]: f"{r['nombre'].split(' → ', 1)[-1]} · {r['dias_min']}–{r['dias_max']} d · "
                                      f"{ETIQUETA_NIVEL[r['nivel']]}" for r in rutas_p}
                p_ruta = st.selectbox("Ruta principal", [None] + list(nombres_r), key=f"rp_prov_ruta_{p_iso}",
                                      format_func=lambda k: "Sin definir" if k is None else "→ " + nombres_r[k])
                c_v, c_n = st.columns([1, 2])
                with c_v:
                    p_vol = st.number_input("Toneladas al año", min_value=0.0, step=100.0, key="rp_prov_vol")
                with c_n:
                    p_notas = st.text_input("Notas", key="rp_prov_notas", placeholder="Contrato, incoterm, contacto…")
                if st.button("Guardar proveedor", type="primary", icon=":material/add:", width="stretch",
                             disabled=not p_nombre.strip()):
                    u = get_usuario()
                    try:
                        proveedores.agregar(p_mat, p_nombre, p_iso, p_ruta, p_vol or None, p_notas,
                                            u.nombre if u else "sin usuario", prov_en_oracle)
                        st.toast(f"{p_nombre.strip()} registrado para {p_mat}", icon=":material/check:")
                        _ir(rp_prov_nombre="", rp_prov_notas="", rp_prov_vol=0.0)
                    except Exception as e:
                        st.error(f"No se pudo guardar: {e}")
        with c_lista:
            if prov.empty:
                st.html("<div style='padding:28px;text-align:center;color:#6B7280;font-size:13px;border:1px dashed "
                        "#D7DDE5;border-radius:10px;font-family:sans-serif;'>Aún no hay proveedores registrados.<br>"
                        "Mientras tanto, los orígenes de cada material son los principales productores "
                        "(referencia).</div>")
            else:
                filas_p = []
                for p in prov.itertuples():
                    rs = {r["id"]: r for r in _con_estado(rutas_de(p.pais_iso, frozenset(cerrados)))}
                    r = rs.get(p.ruta_id) if isinstance(p.ruta_id, str) else None
                    filas_p.append({
                        "Material": p.material, "Proveedor": p.proveedor,
                        "País": PAISES.get(p.pais_iso, {}).get("nombre", p.pais_iso),
                        "Ruta principal": r["nombre"].split(" → ", 1)[-1] if r else "Sin definir",
                        "Días": f"{r['dias_min']}–{r['dias_max']}" if r else "—",
                        "Estado": (("✕ Cerrada" if not r["disponible"] else
                                    f"{ICONO_NIVEL[r['nivel']]} {ETIQUETA_NIVEL[r['nivel']]}") if r else "—"),
                        "t/año": f"{p.volumen_ton_anio:,.0f}" if pd.notna(p.volumen_ton_anio) else "—",
                    })
                st.caption(f"{len(prov)} proveedores · elige uno para ver sus rutas o quitarlo")
                sel_p = st.dataframe(pd.DataFrame(filas_p), hide_index=True, width="stretch",
                                     height=min(35 * len(filas_p) + 38, 420), on_select="rerun",
                                     selection_mode="single-row", key="rp_tabla_prov")
                elegido = sel_p.selection.rows if sel_p else []
                if elegido:
                    p = prov.iloc[elegido[0]]
                    b1, b2, _ = st.columns([1, 1, 1])
                    if b1.button("Ver sus rutas", icon=":material/route:", width="stretch"):
                        _ir(**_a_rutas(p["material"], p["pais_iso"]))
                    if b2.button("Quitar", icon=":material/delete:", width="stretch"):
                        proveedores.quitar(p["id"], prov_en_oracle)
                        st.rerun()
                    if isinstance(p["notas"], str) and p["notas"]:
                        st.caption(f"Notas: {p['notas']}")

st.caption("Fuentes: IMF PortWatch (tráfico de barcos), noticias clasificadas del sistema, NOAA (tormentas), "
           "Open-Meteo (oleaje). Orígenes de referencia, distancias y días son estimados.")
