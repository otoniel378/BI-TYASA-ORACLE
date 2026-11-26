"""
pages/mercado/07_comercio_exterior.py — Comercio Exterior Siderúrgico (SNICE)

Avisos automáticos de importación de productos siderúrgicos, acotados SIEMPRE al
catálogo de fracciones/subpartidas que le importan a TYASA (fracciones_tyasa.py).
Fuente: SNICE / Secretaría de Economía, actualización mensual automática
(scripts/download_snice_siderurgico.py + scripts/load_snice_to_oracle.py, vía
GitHub Actions).

Dos niveles de detalle, según de dónde sale cada tabla:
  - Volumen/avisos/categorías: desde GOLD_SNICE_TOP_FRACCIONES, que nunca se purga
    — disponible para CUALQUIER periodo histórico.
  - País de origen / empresa importadora / detalle de avisos: solo existen a nivel
    de aviso individual en BRONZE_SNICE_SIDERURGICO, que solo conserva los últimos
    PERIODOS_A_CONSERVAR periodos (hoy 6, ~igual a los 123 días de vigencia de un
    aviso — ver scripts/load_snice_to_oracle.py). Fuera de esa ventana no hay
    desglose por país/empresa, solo el total agregado.

DOM-STABLE: todo HTML dinámico usa st.html() (no st.markdown unsafe_allow_html
para contenido que cambia entre reruns).

Pestaña "Aranceles" (mercado/snice/vistas_aranceles.py): arancel base (TIGIE,
GOLD_TIGIE_BASE — carga manual, ver scripts/cargar_tigie_base_oracle.py y el
aviso mensual scripts/check_actualizacion_tigie.py) cruzado con lo que el DOF
le ha aplicado desde entonces (GOLD_MEDIDAS_ARANCELARIAS / GOLD_ALERTAS_DOF —
scripts/monitor_dof.py, automático).
"""

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)
_scripts_dir = os.path.join(_root, "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import streamlit as st
import pandas as pd

from config import COLORS
from core.components.kpi_cards import render_kpi_row
from core.components.tables import _boton_descarga
from fracciones_tyasa import FRACCIONES_TYASA, FRACCIONES_TYASA_PREFIJO
from tigie_partidas import PARTIDAS
from mercado.snice.loaders import (
    load_periodos_disponibles,
    load_periodos_bronze_disponibles,
    load_resumen_tyasa_bronze,
    load_top_fracciones_tyasa_gold,
    load_top_fracciones_tyasa_bronze,
    load_empresas_fracciones,
    load_paises_fracciones,
    load_paises_disponibles,
    load_empresa_detalle,
    load_avisos_detalle,
    load_avisos_para_exportar,
)

FRACCIONES_TYASA_T = tuple(FRACCIONES_TYASA)
FRACCIONES_TYASA_PREFIJO_T = tuple(FRACCIONES_TYASA_PREFIJO)

# Bajo este volumen, dividir VALOR_USD/VOLUMEN_TON para sacar precio unitario deja
# de tener sentido: unas cuantas fracciones-mes en CANACERO traen un volumen casi
# cero (ej. 0.000061 ton) con un valor normal, y el precio implícito se dispara a
# millones de USD/ton — no es un error del dato de valor, es dividir entre casi-cero.
VOLUMEN_MINIMO_PARA_PRECIO = 10

# El acero no se transa por debajo de esto ni como chatarra. Atrapa un error de
# dato real y aislado visto en 2023-06/07 (fracción 73170002: 100 ton reportadas
# en apenas $140 USD, un salto claro contra el resto de la serie — el siguiente
# precio más bajo en todo el histórico ya es ~$293/ton), no un volumen bajo.
PRECIO_MINIMO_PLAUSIBLE_USD_TON = 100

# Si UN SOLO mes aporta más de esta fracción del volumen total de un cuatrimestre,
# el "precio promedio ponderado" de ese cuatrimestre en realidad es casi solo el
# precio de ese mes — comparar dos cuatrimestres así puede verse como un cambio de
# precio enorme (ej. +377%) cuando en realidad es que cambió la MEZCLA de embarques
# (uno grande y barato vs. varios chicos y caros), no el precio de mercado. Caso
# real: 72142001 (varillas corrugadas), 2026 Ene-Abr tuvo 4,652 de 4,656 ton
# (99.9%) en un solo mes (marzo) a $612/ton; 2026 May-Ago no tuvo ningún mes así.
UMBRAL_CONCENTRACION_MENSUAL = 0.75

# Coeficiente de variación (std/mean) del precio mensual histórico. Por encima de
# esto, el "precio" de la fracción se mueve tanto mes a mes (por tratarse de pocas
# toneladas de especificaciones distintas bajo el mismo código arancelario) que
# comparar dos puntos no dice nada confiable — hay que verlo como serie histórica
# completa (sección de abajo), no como "subió/bajó X%". Calibrado contra datos
# reales: fracciones de alto volumen como 72071291 (planchón) tienen CV≈0.03-0.05;
# fracciones de bajo volumen como 72142001 (varillas) llegan a CV≈0.61-1.06.
UMBRAL_VOLATILIDAD_HISTORICA = 0.25

st.title("Comercio Exterior — Siderúrgico")
st.caption(
    "Avisos automáticos de importación · Fuente: SNICE (Secretaría de Economía) · "
    "Acotado al catálogo de fracciones arancelarias de TYASA"
)

# ---------------------------------------------------------------------------
# Datos disponibles
# ---------------------------------------------------------------------------
try:
    periodos = load_periodos_disponibles()
    periodos_bronze = load_periodos_bronze_disponibles()
    DATOS_REALES = True
except Exception as e:
    periodos = []
    periodos_bronze = set()
    DATOS_REALES = False
    st.warning(f"No se pudo conectar a Oracle: {e}")

if not periodos:
    st.info(
        "Todavía no hay datos de comercio exterior cargados. "
        "Corre `python scripts/load_snice_to_oracle.py` para la primera carga."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Catálogo de categorías TYASA (partidas de 4 dígitos que cubren FRACCIONES_TYASA)
# — estático, no requiere consultar Oracle: siempre son las mismas partidas.
# ---------------------------------------------------------------------------
PARTIDAS_TYASA = sorted({f[:4] for f in FRACCIONES_TYASA} | {p[:4] for p in FRACCIONES_TYASA_PREFIJO})
LABEL_PARTIDA = {
    p: f"{p[:2]}.{p[2:]} — {PARTIDAS.get(p, {}).get('descripcion', 'sin descripción')}"
    for p in PARTIDAS_TYASA
}

# ---------------------------------------------------------------------------
# Barra de filtros
# ---------------------------------------------------------------------------
with st.form("snice_filtros", border=True):
    c1, c2, c3, c4, c5 = st.columns([1, 1.3, 1.2, 1.6, 0.8])

    with c1:
        periodo_sel = st.selectbox("Periodo", periodos, index=0)

    with c2:
        partida_sel = st.selectbox(
            "Categoría de producto (TYASA)",
            ["Todas las categorías"] + PARTIDAS_TYASA,
            format_func=lambda p: p if p == "Todas las categorías" else LABEL_PARTIDA[p],
        )

    paises_disp = load_paises_disponibles(periodo_sel)
    with c3:
        pais_sel = st.selectbox("País de origen", ["Todos los países"] + paises_disp)

    with c4:
        busqueda_sel = st.text_input(
            "Buscar empresa (razón social)", placeholder="Ej. POSCO, GONVAUTO, TRUPER…"
        )

    with c5:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        st.form_submit_button("Aplicar filtros", width="stretch", type="primary")

partida_filtro = partida_sel if partida_sel != "Todas las categorías" else None
pais_filtro = pais_sel if pais_sel != "Todos los países" else None
busqueda_filtro = busqueda_sel.strip() if busqueda_sel and busqueda_sel.strip() else None
hay_filtro_extra = bool(partida_filtro or pais_filtro or busqueda_filtro)
en_ventana = periodo_sel in periodos_bronze

if not en_ventana:
    st.info(
        f"El periodo {periodo_sel} ya no tiene detalle por aviso en BRONZE (solo se "
        "conservan los últimos periodos — ver PERIODOS_A_CONSERVAR). Categorías y KPIs "
        "de volumen/avisos siguen siendo exactos (vienen de GOLD, histórico completo); "
        "país de origen, empresas y detalle de avisos no están disponibles para este periodo."
    )

# ---------------------------------------------------------------------------
# Helpers de render (HTML en un solo st.html() por bloque — DOM-stable)
# ---------------------------------------------------------------------------

from mercado.canacero.vista_participacion import render_participacion_tyasa
from mercado.snice.vistas import _card_open, _CARD_CLOSE, _rank_list_html, _agrupar_por_partida
from mercado.snice.vistas_aranceles import render_aranceles_tab



def _periodo_anterior_bronze(periodo: str) -> str | None:
    """Mes inmediato anterior que todavía tiene detalle por aviso (BRONZE)."""
    previos = [p for p in periodos if p < periodo and p in periodos_bronze]
    return max(previos) if previos else None


# ---------------------------------------------------------------------------
# Datos base del periodo (compartidos entre pestañas)
# ---------------------------------------------------------------------------

# Categorías/volumen: SIEMPRE desde GOLD (histórico completo), salvo que haya
# filtro de país o empresa activo y el periodo siga en BRONZE — esa dimensión
# no existe en GOLD_SNICE_TOP_FRACCIONES.
if en_ventana and (pais_filtro or busqueda_filtro):
    fracciones_df = load_top_fracciones_tyasa_bronze(
        periodo_sel, FRACCIONES_TYASA_T, FRACCIONES_TYASA_PREFIJO_T,
        pais=pais_filtro, busqueda=busqueda_filtro,
    )
else:
    fracciones_df = load_top_fracciones_tyasa_gold(
        periodo_sel, FRACCIONES_TYASA_T, FRACCIONES_TYASA_PREFIJO_T,
    )
if partida_filtro:
    fracciones_df = fracciones_df[fracciones_df["fraccion_arancelaria"].str[:4] == partida_filtro]

cats_resumen = _agrupar_por_partida(fracciones_df)

if en_ventana:
    paises_resumen = load_paises_fracciones(
        periodo_sel, FRACCIONES_TYASA_T, FRACCIONES_TYASA_PREFIJO_T,
        partida=partida_filtro, busqueda=busqueda_filtro,
    )
    empresas_df = load_empresas_fracciones(
        periodo_sel, FRACCIONES_TYASA_T, FRACCIONES_TYASA_PREFIJO_T,
        partida=partida_filtro, pais=pais_filtro, busqueda=busqueda_filtro,
    )
else:
    paises_resumen = pd.DataFrame()
    empresas_df = pd.DataFrame()

# ---------------------------------------------------------------------------
# KPIs del periodo — se derivan de fracciones_df (ya trae aplicados partida/país/
# búsqueda) y de una consulta BRONZE con esos mismos filtros, para que el
# resumen de arriba SIEMPRE coincida con lo que muestran las tarjetas de abajo.
# ---------------------------------------------------------------------------
volumen_ton = fracciones_df["volumen_total"].sum() / 1000 if not fracciones_df.empty else 0
avisos_total = int(fracciones_df["avisos"].sum()) if not fracciones_df.empty else 0

resumen_bronze = (
    load_resumen_tyasa_bronze(
        periodo_sel, FRACCIONES_TYASA_T, FRACCIONES_TYASA_PREFIJO_T,
        partida=partida_filtro, pais=pais_filtro, busqueda=busqueda_filtro,
    )
    if en_ventana else {}
)

render_kpi_row([
    {"label": "Volumen importado (TYASA)", "value": round(volumen_ton), "suffix": " ton"},
    {"label": "Avisos autorizados", "value": avisos_total},
    {
        "label": "Empresas importadoras",
        "value": int(resumen_bronze["empresas_distintas"]) if resumen_bronze else "N/D",
    },
    {
        "label": "Países de origen",
        "value": int(resumen_bronze["paises_distintos"]) if resumen_bronze else "N/D",
    },
])

st.divider()

# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------
tab_resumen, tab_categorias, tab_detalle, tab_tyasa, tab_aranceles = st.tabs(
    ["Resumen", "Categorías", "Detalle de avisos", "Participación TYASA", "Aranceles"]
)

# ── RESUMEN (categorías + países + empresas) ────────────────────────────────
with tab_resumen:
    col_a, col_b = st.columns([1.4, 1])

    with col_a:
        html = _card_open("¿Qué se está importando?", "Volumen por categoría de producto (partida TIGIE) — solo TYASA")
        html += _rank_list_html(cats_resumen, "categoria_producto", "subcategoria", max_filas=6)
        html += _CARD_CLOSE
        st.html(html)

    with col_b:
        html = _card_open("¿De dónde viene?", "% del volumen por país de origen")
        if not en_ventana:
            html += f"<p style='color:{COLORS['text_light']};font-size:0.85rem;'>No disponible fuera de la ventana de detalle (ver aviso arriba).</p>"
        else:
            top5 = paises_resumen.head(5)
            total_vol = paises_resumen["volumen_total"].sum() or 1
            filas = []
            for _, r in top5.iterrows():
                pct = (r["volumen_total"] or 0) / total_vol * 100
                filas.append(
                    f"<div style='display:flex;align-items:center;gap:8px;font-size:0.82rem;padding:5px 0;'>"
                    f"<span style='flex:1;font-weight:600;'>{r['pais_origen']}</span>"
                    f"<span style='font-weight:700;color:{COLORS['primary']};'>{pct:.1f}%</span></div>"
                )
            html += "".join(filas) if filas else f"<p style='color:{COLORS['text_light']};font-size:0.85rem;'>Sin datos.</p>"

            if len(top5) >= 3:
                conc3 = top5.head(3)["volumen_total"].sum() / total_vol * 100
                if conc3 > 50:
                    html += (
                        f"<div style='margin-top:14px;padding:11px 14px;border-radius:10px;"
                        f"background:#FFF3E0;color:#8A5000;font-size:0.8rem;border:1px solid #FFE0B2;'>"
                        f"Los 3 países principales concentran <b>{conc3:.1f}%</b> del volumen — "
                        f"dependencia alta de pocos orígenes.</div>"
                    )
        html += _CARD_CLOSE
        st.html(html)

    st.divider()
    st.markdown(f"##### Ranking de empresas importadoras{' — filtrado' if hay_filtro_extra else ''}")

    if not en_ventana:
        st.info("No disponible fuera de la ventana de detalle (ver aviso arriba).")
    elif empresas_df.empty:
        st.info("Sin empresas para este filtro.")
    else:
        tabla = empresas_df.head(30).copy()
        tabla["volumen_total"] = (tabla["volumen_total"] / 1000).map(lambda v: f"{v:,.1f}")
        tabla = tabla.rename(columns={
            "razon_social": "Razón social", "volumen_total": "Volumen (ton)",
            "avisos": "Avisos", "fracciones_distintas": "Fracciones TYASA", "paises_distintos": "Países",
        })
        cols_mostrar = [c for c in ["Razón social", "Volumen (ton)", "Avisos", "Fracciones TYASA", "Países"] if c in tabla.columns]
        st.dataframe(tabla[cols_mostrar], hide_index=True, width="stretch", height=340)

        st.markdown("###### Ficha de empresa")
        empresa_sel = st.selectbox(
            "Ver detalle de:", empresas_df["razon_social"].head(30).tolist(), key="empresa_drilldown"
        )
        if empresa_sel:
            detalle = load_empresa_detalle(empresa_sel, periodo_sel)
            r = detalle["resumen"]
            if r and r.get("volumen_total"):
                html = (
                    f"<div style='border:1px solid {COLORS['secondary']};border-radius:14px;"
                    f"background:{COLORS['surface']};padding:20px 22px;margin-top:6px;'>"
                    f"<p style='margin:0 0 14px;font-size:1.02rem;font-weight:700;color:{COLORS['primary']};'>{empresa_sel}</p>"
                    f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;'>"
                    f"<div style='background:{COLORS['background']};border-radius:8px;padding:10px 12px;'>"
                    f"<div style='font-size:0.66rem;font-weight:700;color:{COLORS['text_light']};text-transform:uppercase;'>Volumen</div>"
                    f"<div style='font-size:1rem;font-weight:700;color:{COLORS['primary']};'>{r['volumen_total']/1000:,.0f} ton</div></div>"
                    f"<div style='background:{COLORS['background']};border-radius:8px;padding:10px 12px;'>"
                    f"<div style='font-size:0.66rem;font-weight:700;color:{COLORS['text_light']};text-transform:uppercase;'>Avisos</div>"
                    f"<div style='font-size:1rem;font-weight:700;color:{COLORS['primary']};'>{int(r['avisos']):,}</div></div>"
                    f"<div style='background:{COLORS['background']};border-radius:8px;padding:10px 12px;'>"
                    f"<div style='font-size:0.66rem;font-weight:700;color:{COLORS['text_light']};text-transform:uppercase;'>Categorías</div>"
                    f"<div style='font-size:1rem;font-weight:700;color:{COLORS['primary']};'>{int(r['categorias']):,}</div></div>"
                    f"<div style='background:{COLORS['background']};border-radius:8px;padding:10px 12px;'>"
                    f"<div style='font-size:0.66rem;font-weight:700;color:{COLORS['text_light']};text-transform:uppercase;'>Países</div>"
                    f"<div style='font-size:1rem;font-weight:700;color:{COLORS['primary']};'>{int(r['paises']):,}</div></div>"
                    f"</div>"
                )
                cat_html = _rank_list_html(detalle["categorias"], "categoria_producto", None, max_filas=6)
                html += (
                    f"<p style='margin:0 0 4px;font-size:0.86rem;font-weight:700;color:{COLORS['primary']};'>Qué importa</p>"
                    f"{cat_html}{_CARD_CLOSE}"
                )
                st.html(html)

                avisos_recientes = detalle["avisos_recientes"]
                if not avisos_recientes.empty:
                    with st.expander(f"Avisos recientes de {empresa_sel}"):
                        av = avisos_recientes.copy()
                        av["volumen_aviso"] = (av["volumen_aviso"] / 1000).map(lambda v: f"{v:,.2f}")
                        av = av.rename(columns={
                            "fraccion_arancelaria": "Fracción", "categoria_producto": "Categoría",
                            "pais_origen": "País", "volumen_aviso": "Volumen (ton)",
                            "fecha_tramite": "Fecha trámite",
                        })
                        cols = [c for c in ["Fecha trámite", "Fracción", "Categoría", "País", "Volumen (ton)"] if c in av.columns]
                        st.dataframe(av[cols], hide_index=True, width="stretch")
            else:
                st.caption(
                    "Sin detalle disponible para esta empresa en el periodo seleccionado "
                    "(el detalle solo se conserva unos meses; el histórico agregado vive en los rankings de arriba)."
                )

# ── CATEGORÍAS ───────────────────────────────────────────────────────────────
with tab_categorias:
    subtitulo = "Agrupadas por partida arancelaria (catálogo TYASA, capítulos 72 y 73)"
    if hay_filtro_extra:
        subtitulo += " — filtrado"
    html = _card_open(f"Todas las categorías ({len(cats_resumen)})", subtitulo)
    html += _rank_list_html(cats_resumen, "categoria_producto", "subcategoria")
    html += _CARD_CLOSE
    st.html(html)

# ── DETALLE DE AVISOS ────────────────────────────────────────────────────────
with tab_detalle:
    if not en_ventana:
        st.info(
            f"El detalle de avisos solo cubre los periodos que siguen en BRONZE "
            f"(no incluye {periodo_sel})."
        )
    else:
        if "snice_pagina" not in st.session_state:
            st.session_state.snice_pagina = 1

        TAM_PAGINA = 25
        df_detalle, total = load_avisos_detalle(
            periodo_sel, fracciones_exactas=FRACCIONES_TYASA_T, fracciones_prefijo=FRACCIONES_TYASA_PREFIJO_T,
            partida=partida_filtro, pais=pais_filtro,
            busqueda_empresa=busqueda_filtro, pagina=st.session_state.snice_pagina, tam_pagina=TAM_PAGINA,
        )

        st.markdown(f"**Detalle de avisos** ({total:,} registros con los filtros actuales)")

        if df_detalle.empty:
            st.info("Sin avisos para este filtro.")
        else:
            tabla = df_detalle.copy()
            tabla["volumen_aviso"] = (tabla["volumen_aviso"] / 1000).map(lambda v: f"{v:,.2f}")
            tabla = tabla.rename(columns={
                "folio_tramite": "Folio", "razon_social": "Razón social", "fraccion_arancelaria": "Fracción",
                "categoria_producto": "Categoría", "pais_origen": "País", "volumen_aviso": "Volumen (ton)",
                "fecha_tramite": "Fecha",
            })
            st.dataframe(
                tabla[["Fecha", "Folio", "Razón social", "Fracción", "Categoría", "País", "Volumen (ton)"]],
                hide_index=True, width="stretch", height=360,
            )

            total_paginas = max(1, -(-total // TAM_PAGINA))
            c_prev, c_info, c_next = st.columns([1, 3, 1])
            with c_prev:
                if st.button("‹ Anterior", disabled=st.session_state.snice_pagina <= 1, width="stretch"):
                    st.session_state.snice_pagina -= 1
                    st.rerun()
            with c_info:
                st.markdown(
                    f"<div style='text-align:center;color:{COLORS['text_light']};font-size:0.85rem;padding-top:6px;'>"
                    f"Página {st.session_state.snice_pagina} de {total_paginas}</div>",
                    unsafe_allow_html=True,
                )
            with c_next:
                if st.button("Siguiente ›", disabled=st.session_state.snice_pagina >= total_paginas, width="stretch"):
                    st.session_state.snice_pagina += 1
                    st.rerun()

            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            df_export = load_avisos_para_exportar(
                periodo_sel, fracciones_exactas=FRACCIONES_TYASA_T, fracciones_prefijo=FRACCIONES_TYASA_PREFIJO_T,
                partida=partida_filtro, pais=pais_filtro, busqueda_empresa=busqueda_filtro,
            )
            if not df_export.empty:
                df_export = df_export.rename(columns={"volumen_aviso": "volumen_aviso_ton"})
                df_export["volumen_aviso_ton"] = (df_export["volumen_aviso_ton"] / 1000).round(3)
            _boton_descarga(df_export, key=f"snice_detalle_{periodo_sel}", label="Exportar todo el filtro a Excel")

# ── PARTICIPACIÓN TYASA (CANACERO × SNICE) ──────────────────────────────────
with tab_tyasa:
    render_participacion_tyasa(
        FRACCIONES_TYASA_PREFIJO_T=FRACCIONES_TYASA_PREFIJO_T,
        FRACCIONES_TYASA_T=FRACCIONES_TYASA_T,
        PRECIO_MINIMO_PLAUSIBLE_USD_TON=PRECIO_MINIMO_PLAUSIBLE_USD_TON,
        UMBRAL_CONCENTRACION_MENSUAL=UMBRAL_CONCENTRACION_MENSUAL,
        UMBRAL_VOLATILIDAD_HISTORICA=UMBRAL_VOLATILIDAD_HISTORICA,
        VOLUMEN_MINIMO_PARA_PRECIO=VOLUMEN_MINIMO_PARA_PRECIO,
        _periodo_anterior_bronze=_periodo_anterior_bronze,
        en_ventana=en_ventana,
        periodo_sel=periodo_sel,
        periodos=periodos,
    )

# ── ARANCELES (TIGIE base × medidas del DOF) ────────────────────────────────
with tab_aranceles:
    render_aranceles_tab()

st.caption(
    f"Datos: SNICE — Secretaría de Economía · Periodo {periodo_sel} · "
    "Catálogo: fracciones TYASA (capítulos 72 y 73) · Actualización mensual automática"
)
