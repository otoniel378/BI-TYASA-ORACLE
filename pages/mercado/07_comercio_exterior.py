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
from core.components.charts import linea_temporal, barras_horizontales, scatter
from fracciones_tyasa import FRACCIONES_TYASA, FRACCIONES_TYASA_PREFIJO, RAZON_SOCIAL_TYASA_SNICE
from fracciones_tyasa_ligie import FRACCIONES_TYASA_DESCRIPCION
from tigie_partidas import PARTIDAS, categoria_de
from mercado.snice.loaders import (
    load_periodos_disponibles,
    load_periodos_bronze_disponibles,
    load_resumen_tyasa_bronze,
    load_top_fracciones_tyasa_gold,
    load_top_fracciones_tyasa_bronze,
    load_serie_tyasa_gold,
    load_serie_empresa_gold,
    load_rango_vigencia_disponible,
    load_resumen_vigentes_en_mes,
    load_fracciones_vigentes_en_mes,
    load_avisos_vigentes_en_mes,
    load_empresas_fracciones,
    load_empresas_fraccion_exacta,
    load_avisos_fraccion_exacta,
    load_paises_fracciones,
    load_paises_disponibles,
    load_empresa_detalle,
    load_avisos_detalle,
    load_avisos_para_exportar,
)
from mercado.canacero.loaders import (
    cargar_csv_canacero,
    load_periodos_canacero,
    load_resumen_tyasa,
    load_serie_tiempo_tyasa,
    load_series_fracciones_tyasa,
    load_top_fracciones_tyasa,
    load_serie_fraccion,
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

def _rank_bar_row(nombre: str, valor_ton: float, avisos: int, pct_ancho: float, tag: str = "") -> str:
    tag_html = (
        f"<span style='font-size:0.68rem;font-weight:600;color:{COLORS['secondary']};"
        f"background:#E8EFF5;padding:2px 8px;border-radius:20px;margin-left:8px;white-space:nowrap;'>{tag}</span>"
        if tag else ""
    )
    return f"""
    <div style="display:grid;grid-template-columns:1fr 108px;align-items:center;gap:10px;padding:8px 0;">
      <div>
        <div style="font-size:0.85rem;font-weight:600;color:{COLORS['text']};">{nombre}{tag_html}</div>
        <div style="height:7px;background:{COLORS['background']};border-radius:4px;margin-top:5px;overflow:hidden;">
          <div style="height:100%;width:{max(pct_ancho, 2):.0f}%;background:{COLORS['primary']};border-radius:4px;"></div>
        </div>
      </div>
      <div style="text-align:right;font-size:0.82rem;font-weight:700;color:{COLORS['text']};">
        {valor_ton:,.0f} t
        <div style="font-size:0.68rem;font-weight:500;color:{COLORS['text_light']};">{avisos:,} avisos</div>
      </div>
    </div>
    """


def _card_open(titulo: str, subtitulo: str = "") -> str:
    sub = f"<p style='margin:0 0 14px;font-size:0.8rem;color:{COLORS['text_light']};'>{subtitulo}</p>" if subtitulo else "<div style='height:8px'></div>"
    return (
        f"<div style='background:{COLORS['surface']};border:1px solid #E5E7EB;border-radius:14px;"
        f"padding:20px 22px;'>"
        f"<p style='margin:0 0 3px;font-size:1rem;font-weight:700;color:{COLORS['primary']};'>{titulo}</p>"
        f"{sub}"
    )


_CARD_CLOSE = "</div>"


def _rank_list_html(df: pd.DataFrame, col_nombre: str, tag_col: str | None, max_filas: int = 999) -> str:
    if df.empty:
        return f"<p style='color:{COLORS['text_light']};font-size:0.85rem;'>Sin datos para este filtro.</p>"
    df2 = df.head(max_filas)
    max_vol = df2["volumen_total"].max() or 1
    filas = []
    for _, r in df2.iterrows():
        pct = (r["volumen_total"] or 0) / max_vol * 100
        tag = str(r[tag_col]) if tag_col and pd.notna(r.get(tag_col)) else ""
        filas.append(_rank_bar_row(
            str(r[col_nombre]), (r["volumen_total"] or 0) / 1000, int(r["avisos"] or 0), pct, tag,
        ))
    return "".join(filas)


def _agrupar_por_partida(fracciones_df: pd.DataFrame) -> pd.DataFrame:
    """Convierte un detalle por fracción (fraccion_arancelaria/volumen_total/avisos)
    en un ranking por partida (categoría TIGIE), usando el catálogo oficial LIGIE."""
    columnas = ["partida", "categoria_producto", "subcategoria", "volumen_total", "avisos"]
    if fracciones_df.empty:
        return pd.DataFrame(columns=columnas)
    df = fracciones_df.copy()
    df["partida"] = df["fraccion_arancelaria"].str[:4]
    info = df["partida"].apply(categoria_de)
    df["categoria_producto"] = info.apply(lambda t: t[0])
    df["subcategoria"] = info.apply(lambda t: t[1])
    agg = (
        df.groupby(["partida", "categoria_producto", "subcategoria"], as_index=False)[["volumen_total", "avisos"]]
        .sum()
        .sort_values("volumen_total", ascending=False)
    )
    return agg


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
tab_resumen, tab_categorias, tab_detalle, tab_tyasa = st.tabs(
    ["Resumen", "Categorías", "Detalle de avisos", "Participación TYASA"]
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
    st.caption(
        "CANACERO = comercio exterior TOTAL de México (fuente: SICEP), filtrado a las fracciones "
        "del catálogo de TYASA. SNICE = detalle por empresa de los avisos automáticos de importación "
        "en esas mismas fracciones. Esto todavía NO son los volúmenes propios de TYASA — ese cruce se "
        "agrega cuando se integren los datos internos de TYASA."
    )

    with st.expander("Cargar nuevo periodo de CANACERO (CSV de 'Base de datos tradicional')"):
        c_up1, c_up2 = st.columns([2, 1])
        with c_up1:
            archivo_canacero = st.file_uploader(
                "CSV exportado de CANACERO SICEP (Grupos Personalizados > Grupo Fracciones > "
                "Base de datos tradicional, agrupado por Fracciones)",
                type=["csv"], key="canacero_uploader",
            )
        with c_up2:
            movimiento_up_label = st.selectbox(
                "Movimiento", ["Importación", "Exportación"], key="canacero_movimiento_up"
            )
        if st.button("Cargar a Oracle", disabled=archivo_canacero is None, key="canacero_cargar_btn"):
            movimiento_up = "IMPORTACION" if movimiento_up_label == "Importación" else "EXPORTACION"
            try:
                resultado = cargar_csv_canacero(archivo_canacero, movimiento_up, archivo_canacero.name)
                if resultado["filas_insertadas"] == 0:
                    st.warning("El archivo no tenía filas con volumen distinto de cero.")
                else:
                    st.success(
                        f"Cargado: {resultado['filas_insertadas']:,} filas · "
                        f"periodos {', '.join(resultado['periodos'])} · movimiento {resultado['movimiento']}"
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"No se pudo cargar el archivo: {e}")

    movimiento_dash_label = st.radio(
        "Movimiento a analizar", ["Importación", "Exportación"], horizontal=True, key="canacero_movimiento_dash",
    )
    movimiento_dash = "IMPORTACION" if movimiento_dash_label == "Importación" else "EXPORTACION"

    periodos_canacero = load_periodos_canacero(movimiento_dash)

    if not periodos_canacero:
        st.info(
            "Todavía no hay datos de CANACERO cargados para este movimiento. "
            "Sube un CSV arriba para empezar."
        )
    else:
        periodo_canacero_sel = st.selectbox(
            "Periodo (CANACERO)", periodos_canacero, index=0, key="canacero_periodo_sel"
        )

        opciones_fraccion_todas = sorted(FRACCIONES_TYASA)
        etiquetas_fraccion = {
            f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}" for f in opciones_fraccion_todas
        }
        seleccion_analisis = st.multiselect(
            "Fracciones a incluir en el análisis (todo lo de abajo se filtra con esto)",
            opciones_fraccion_todas, default=opciones_fraccion_todas,
            format_func=lambda f: etiquetas_fraccion[f], key="canacero_fracciones_analisis",
        )
        if not seleccion_analisis:
            st.warning("Selecciona al menos una fracción para ver el análisis.")
            st.stop()

        usa_catalogo_completo = set(seleccion_analisis) == set(opciones_fraccion_todas)
        fracciones_filtro = None if usa_catalogo_completo else tuple(seleccion_analisis)
        fracciones_exactas_snice = tuple(FRACCIONES_TYASA) if usa_catalogo_completo else tuple(seleccion_analisis)
        fracciones_prefijo_snice = tuple(FRACCIONES_TYASA_PREFIJO) if usa_catalogo_completo else ()
        opciones_fraccion = sorted(seleccion_analisis)

        resumen_nac = load_resumen_tyasa(periodo_canacero_sel, movimiento_dash, fracciones=fracciones_filtro)
        vol_nacional_ton = resumen_nac.get("volumen_total") or 0

        empresas_tyasa = load_empresas_fracciones(
            periodo_sel, fracciones_exactas_snice, fracciones_prefijo_snice,
        )
        vol_snice_ton = (empresas_tyasa["volumen_total"].sum() / 1000) if not empresas_tyasa.empty else 0
        cobertura_pct = (vol_snice_ton / vol_nacional_ton * 100) if vol_nacional_ton else 0
        empresa_top = empresas_tyasa.iloc[0]["razon_social"] if not empresas_tyasa.empty else "—"

        render_kpi_row([
            {"label": f"Volumen nacional CANACERO ({periodo_canacero_sel})", "value": round(vol_nacional_ton), "suffix": " ton"},
            {"label": f"Reportado en avisos SNICE ({periodo_sel})", "value": round(vol_snice_ton), "suffix": " ton"},
            {"label": "Cobertura SNICE / CANACERO", "value": round(cobertura_pct, 1), "suffix": " %"},
            {"label": "Empresa líder (SNICE)", "value": empresa_top},
        ])
        st.caption(
            "\"Volumen nacional CANACERO\" es la suma de TODO México en las fracciones del catálogo "
            "TYASA (no el volumen propio de TYASA). El periodo de CANACERO y el de SNICE (filtro de "
            "arriba de la página) pueden no coincidir exactamente — cada fuente publica en fechas distintas."
        )

        st.divider()
        st.markdown("##### CANACERO vs. SNICE vs. TYASA")
        st.caption(
            "Las dos primeras series son el mismo universo — TODO México, pero SOLO en las "
            "fracciones del catálogo de TYASA (no todo el acero del país, y no el volumen propio "
            "de TYASA) — reportado por dos fuentes distintas: CANACERO (estadística oficial de "
            "comercio exterior) y SNICE (avisos automáticos de importación). La tercera es el "
            "volumen que TYASA reportó a su propio nombre en SNICE."
        )

        serie_canacero = load_serie_tiempo_tyasa(movimiento_dash, fracciones=fracciones_filtro)[["periodo_mes", "volumen_total"]]
        serie_canacero["serie"] = "CANACERO — nacional, catálogo TYASA"

        serie_snice_total = load_serie_tyasa_gold(fracciones_exactas_snice, fracciones_prefijo_snice)
        serie_snice_total = serie_snice_total.rename(columns={"periodo": "periodo_mes"})[["periodo_mes", "volumen_total"]]
        serie_snice_total["volumen_total"] = serie_snice_total["volumen_total"] / 1000
        serie_snice_total["serie"] = "SNICE — nacional, catálogo TYASA"

        serie_tyasa = load_serie_empresa_gold(RAZON_SOCIAL_TYASA_SNICE)
        serie_tyasa = serie_tyasa.rename(columns={"periodo": "periodo_mes"})[["periodo_mes", "volumen_total"]]
        serie_tyasa["volumen_total"] = serie_tyasa["volumen_total"].fillna(0) / 1000
        serie_tyasa["serie"] = f"SNICE — TYASA ({RAZON_SOCIAL_TYASA_SNICE})"

        serie_comparativa = pd.concat([serie_canacero, serie_snice_total, serie_tyasa], ignore_index=True)

        col_chart, col_top5 = st.columns([2, 1])
        with col_chart:
            st.plotly_chart(
                linea_temporal(
                    serie_comparativa, x="periodo_mes", y="volumen_total", color="serie",
                    titulo="Volumen mensual — nacional (catálogo TYASA) vs. TYASA",
                    y_label="Ton", height=480,
                ),
                width="stretch",
            )
            st.caption(
                "La serie de TYASA sale de GOLD_SNICE_TOP_EMPRESAS (histórico completo desde 2019, "
                "sin poder acotarse por fracción); en los meses donde sí se pudo comparar contra el "
                "detalle exacto del catálogo TYASA (los que siguen en BRONZE) el total coincidió "
                "exacto, así que no parece incluir nada fuera de su propio catálogo."
            )

        with col_top5:
            st.markdown("###### Top 5 fracciones por periodo")
            periodo_top5_sel = st.selectbox(
                "Periodo a comparar", periodos_canacero, index=0, key="snice_top5_periodo",
            )

            st.caption(f"CANACERO (nacional) — {periodo_top5_sel}")
            top5_canacero = load_top_fracciones_tyasa(
                periodo_top5_sel, movimiento_dash, limite=5, fracciones=fracciones_filtro,
            )
            if top5_canacero.empty:
                st.caption("Sin datos para este periodo.")
            else:
                t1 = top5_canacero.copy()
                t1["Fracción"] = t1["fraccion"].map(
                    lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}"
                )
                t1["Volumen (ton)"] = t1["volumen_total"].map(lambda v: f"{v:,.0f}")
                st.dataframe(t1[["Fracción", "Volumen (ton)"]], hide_index=True, width="stretch", height=210)

            st.caption(f"SNICE (avisos) — {periodo_top5_sel}")
            top5_snice = load_top_fracciones_tyasa_gold(
                periodo_top5_sel, fracciones_exactas_snice, fracciones_prefijo_snice,
            )
            if top5_snice.empty:
                st.caption("Sin datos para este periodo.")
            else:
                t2 = top5_snice.sort_values("volumen_total", ascending=False).head(5).copy()
                t2["Fracción"] = t2["fraccion_arancelaria"].map(
                    lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}"
                )
                t2["Volumen (ton)"] = (t2["volumen_total"] / 1000).map(lambda v: f"{v:,.0f}")
                st.dataframe(t2[["Fracción", "Volumen (ton)"]], hide_index=True, width="stretch", height=210)

        st.divider()
        st.markdown("##### Consumo aparente en México (Importación − Exportación)")

        serie_imp_neto = load_serie_tiempo_tyasa("IMPORTACION", fracciones=fracciones_filtro)[["periodo_mes", "volumen_total"]]
        serie_exp_neto = load_serie_tiempo_tyasa("EXPORTACION", fracciones=fracciones_filtro)[["periodo_mes", "volumen_total"]]

        if serie_exp_neto.empty:
            st.info(
                "Todavía no hay datos de EXPORTACIÓN de CANACERO cargados — sube un CSV de "
                "exportación arriba ('Cargar nuevo periodo de CANACERO') para activar esta sección."
            )
        else:
            neto_df = serie_imp_neto.rename(columns={"volumen_total": "importacion"}).merge(
                serie_exp_neto.rename(columns={"volumen_total": "exportacion"}), on="periodo_mes", how="inner",
            ).sort_values("periodo_mes")
            periodos_con_ambos = sorted(neto_df["periodo_mes"].unique().tolist())
            st.caption(
                "Importación menos exportación, para estimar qué tanto de lo que entra a México "
                "realmente se queda (vs. se reexporta) — mismo catálogo de fracciones TYASA. Solo "
                "cubre los meses donde CANACERO tiene AMBOS movimientos cargados: hoy, "
                f"{', '.join(periodos_con_ambos) if periodos_con_ambos else 'ninguno'} "
                "(exportación tiene mucho menos historial subido que importación)."
            )
            if neto_df.empty:
                st.info("Sin meses con importación y exportación cargadas a la vez todavía.")
            else:
                neto_df["neto"] = neto_df["importacion"] - neto_df["exportacion"]
                neto_df["pct_reexportado"] = (
                    (neto_df["exportacion"] / neto_df["importacion"] * 100).where(neto_df["importacion"] > 0)
                )

                ultimo = neto_df.iloc[-1]
                render_kpi_row([
                    {"label": f"Importación ({ultimo['periodo_mes']})", "value": round(ultimo["importacion"]), "suffix": " ton"},
                    {"label": f"Exportación ({ultimo['periodo_mes']})", "value": round(ultimo["exportacion"]), "suffix": " ton"},
                    {"label": "Consumo aparente (neto)", "value": round(ultimo["neto"]), "suffix": " ton"},
                    {
                        "label": "% reexportado",
                        "value": round(ultimo["pct_reexportado"], 1) if pd.notna(ultimo["pct_reexportado"]) else "N/D",
                        "suffix": " %",
                    },
                ])

                neto_long = pd.concat([
                    neto_df[["periodo_mes", "importacion"]].rename(columns={"importacion": "volumen_total"}).assign(serie="Importación"),
                    neto_df[["periodo_mes", "exportacion"]].rename(columns={"exportacion": "volumen_total"}).assign(serie="Exportación"),
                    neto_df[["periodo_mes", "neto"]].rename(columns={"neto": "volumen_total"}).assign(serie="Consumo aparente (neto)"),
                ], ignore_index=True)
                st.plotly_chart(
                    linea_temporal(
                        neto_long, x="periodo_mes", y="volumen_total", color="serie",
                        titulo="Importación vs. Exportación vs. Consumo aparente — catálogo TYASA",
                        y_label="Ton",
                    ),
                    width="stretch",
                )

        st.divider()
        st.markdown("##### Intención de importación (por vigencia del permiso)")
        st.caption(
            "A diferencia de las gráficas de arriba (agrupadas por el PERIODO en que se tramitó "
            "el aviso), aquí se agrupa por la VIGENCIA del permiso: qué avisos siguen habilitando "
            "la importación durante el mes que elijas, sin importar cuándo se hayan tramitado. Solo "
            "cubre los periodos que siguen en BRONZE (un aviso dura 123 días de vigencia)."
        )

        mes_min, mes_max = load_rango_vigencia_disponible(fracciones_exactas_snice, fracciones_prefijo_snice)
        if not mes_min:
            st.info("Sin datos de vigencia disponibles todavía.")
        else:
            meses_disponibles = pd.period_range(mes_min, mes_max, freq="M").astype(str).tolist()
            mes_sel = st.selectbox(
                "Mes a proyectar", meses_disponibles, index=len(meses_disponibles) - 1,
                key="snice_mes_vigencia",
            )
            resumen_mes = load_resumen_vigentes_en_mes(mes_sel, fracciones_exactas_snice, fracciones_prefijo_snice)
            if not resumen_mes or not resumen_mes.get("avisos"):
                st.info(f"Sin avisos con vigencia en {mes_sel}.")
            else:
                render_kpi_row([
                    {"label": f"Volumen con vigencia en {mes_sel}", "value": round((resumen_mes.get("volumen_total") or 0) / 1000), "suffix": " ton"},
                    {"label": "Avisos vigentes ese mes", "value": int(resumen_mes.get("avisos") or 0)},
                    {"label": "Empresas", "value": int(resumen_mes.get("empresas_distintas") or 0)},
                    {"label": "Países", "value": int(resumen_mes.get("paises_distintos") or 0)},
                ])

                col_v1, col_v2 = st.columns([1.2, 1])
                with col_v1:
                    fracciones_mes = load_fracciones_vigentes_en_mes(mes_sel, fracciones_exactas_snice, fracciones_prefijo_snice)
                    fracciones_mes = fracciones_mes.copy()
                    fracciones_mes["etiqueta"] = fracciones_mes["fraccion_arancelaria"].map(
                        lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}"
                    )
                    fracciones_mes["volumen_ton"] = fracciones_mes["volumen_total"] / 1000
                    st.plotly_chart(
                        barras_horizontales(
                            fracciones_mes, x="volumen_ton", y="etiqueta",
                            titulo=f"Qué fracciones tienen vigencia en {mes_sel}", x_label="Ton", max_items=12,
                        ),
                        width="stretch",
                    )
                with col_v2:
                    avisos_mes = load_avisos_vigentes_en_mes(
                        mes_sel, fracciones_exactas_snice, fracciones_prefijo_snice, limite=200,
                    )
                    tabla_v = avisos_mes.copy()
                    tabla_v["volumen_aviso"] = (tabla_v["volumen_aviso"] / 1000).map(lambda v: f"{v:,.2f}")
                    tabla_v = tabla_v.rename(columns={
                        "razon_social": "Razón social", "fraccion_arancelaria": "Fracción",
                        "pais_origen": "País", "volumen_aviso": "Volumen (ton)",
                        "inicio_vigencia": "Inicio vigencia", "fin_vigencia": "Fin vigencia",
                    })
                    st.dataframe(
                        tabla_v[["Razón social", "Fracción", "País", "Volumen (ton)", "Inicio vigencia", "Fin vigencia"]],
                        hide_index=True, width="stretch", height=360,
                    )

        st.divider()
        st.markdown("##### Comparación por cuatrimestre (CANACERO)")
        st.caption(
            "Agrupa el histórico nacional CANACERO en cuatrimestres (Ene-Abr / May-Ago / Sep-Dic) "
            "y compara el cuatrimestre elegido contra el inmediato anterior, fracción por fracción, "
            "para ver qué subió, qué bajó, y en qué porcentaje."
        )

        series_frac = load_series_fracciones_tyasa(movimiento_dash)
        if fracciones_filtro:
            series_frac = series_frac[series_frac["fraccion"].isin(fracciones_filtro)]

        if series_frac.empty:
            st.info("Sin histórico CANACERO por fracción todavía.")
        else:
            _CUATRI_LABEL = {0: "Ene-Abr", 1: "May-Ago", 2: "Sep-Dic"}
            series_frac = series_frac.copy()
            partes = series_frac["periodo_mes"].str.split("-", expand=True)
            series_frac["anio"] = partes[0].astype(int)
            series_frac["bloque"] = (partes[1].astype(int) - 1) // 4
            series_frac["cuatrimestre"] = series_frac["anio"].astype(str) + " " + series_frac["bloque"].map(_CUATRI_LABEL)

            cuatrimestres = (
                series_frac[["anio", "bloque", "cuatrimestre"]].drop_duplicates().sort_values(["anio", "bloque"])
            )
            opciones_cuatri = cuatrimestres["cuatrimestre"].tolist()
            cuatri_sel = st.selectbox(
                "Cuatrimestre a analizar", opciones_cuatri, index=len(opciones_cuatri) - 1, key="snice_cuatri_sel",
            )
            idx_sel = opciones_cuatri.index(cuatri_sel)
            if idx_sel == 0:
                st.info(f"{cuatri_sel} es el primer cuatrimestre con datos — no hay uno anterior para comparar.")
            else:
                cuatri_anterior = opciones_cuatri[idx_sel - 1]
                anio_sel, bloque_sel = cuatrimestres.iloc[idx_sel][["anio", "bloque"]]
                anio_ant, bloque_ant = cuatrimestres.iloc[idx_sel - 1][["anio", "bloque"]]

                actual = series_frac[(series_frac["anio"] == anio_sel) & (series_frac["bloque"] == bloque_sel)]
                anterior = series_frac[(series_frac["anio"] == anio_ant) & (series_frac["bloque"] == bloque_ant)]

                agg_actual = actual.groupby("fraccion", as_index=False)["volumen_total"].sum().rename(columns={"volumen_total": "actual"})
                agg_anterior = anterior.groupby("fraccion", as_index=False)["volumen_total"].sum().rename(columns={"volumen_total": "anterior"})
                comp = agg_actual.merge(agg_anterior, on="fraccion", how="outer").fillna(0)
                comp["delta_ton"] = comp["actual"] - comp["anterior"]
                comp["delta_pct"] = comp.apply(
                    lambda r: (r["delta_ton"] / r["anterior"] * 100) if r["anterior"] else (100.0 if r["actual"] else 0.0),
                    axis=1,
                )
                comp["direccion"] = comp["delta_ton"].map(lambda d: "▲ Aumentó" if d > 0 else ("▼ Disminuyó" if d < 0 else "= Sin cambio"))
                comp["etiqueta"] = comp["fraccion"].map(lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}")
                comp = comp.reindex(comp["delta_ton"].abs().sort_values(ascending=False).index)

                total_actual = comp["actual"].sum()
                total_anterior = comp["anterior"].sum()
                delta_total_pct = (total_actual - total_anterior) / total_anterior * 100 if total_anterior else 0

                render_kpi_row([
                    {"label": cuatri_anterior, "value": round(total_anterior), "suffix": " ton"},
                    {"label": cuatri_sel, "value": round(total_actual), "suffix": " ton"},
                    {"label": "Variación total", "value": round(delta_total_pct, 1), "suffix": " %"},
                ])

                comp_chart = comp.head(15).copy()
                comp_chart["delta_abs_ton"] = comp_chart["delta_ton"].abs()
                st.plotly_chart(
                    barras_horizontales(
                        comp_chart, x="delta_abs_ton", y="etiqueta",
                        titulo=f"Mayores variaciones: {cuatri_sel} vs. {cuatri_anterior}",
                        x_label="Ton (variación absoluta)", max_items=15,
                    ),
                    width="stretch",
                )

                tabla_comp = comp[["etiqueta", "anterior", "actual", "delta_ton", "delta_pct", "direccion"]].copy()
                for c in ("anterior", "actual", "delta_ton"):
                    tabla_comp[c] = tabla_comp[c].map(lambda v: f"{v:,.1f}")
                tabla_comp["delta_pct"] = tabla_comp["delta_pct"].map(lambda v: f"{v:.1f}%")
                tabla_comp.columns = [
                    "Fracción", f"{cuatri_anterior} (ton)", f"{cuatri_sel} (ton)",
                    "Variación (ton)", "Variación (%)", "Dirección",
                ]
                st.dataframe(tabla_comp, hide_index=True, width="stretch", height=360)

                st.markdown("###### Precio unitario — mismos cuatrimestres")
                st.caption(
                    "Precio implícito (valor USD / volumen ton) por fracción, promedio ponderado de "
                    "cada cuatrimestre. Solo incluye fracciones con al menos "
                    f"{VOLUMEN_MINIMO_PARA_PRECIO} ton en AMBOS cuatrimestres — con menos volumen, el "
                    "precio implícito se vuelve ruido estadístico (dividir entre casi-cero dispara el "
                    "resultado), no una señal real de mercado. Las marcadas ⚠ tienen más del "
                    f"{UMBRAL_CONCENTRACION_MENSUAL:.0%} de su volumen concentrado en UN solo mes de ese "
                    "cuatrimestre — su 'precio promedio' es en realidad casi solo el de ese mes, así que "
                    "una variación grande puede ser un cambio en la mezcla de embarques, no en el precio."
                )

                def _concentracion_mensual(df_cuatri: pd.DataFrame) -> pd.Series:
                    """Para cada fracción: qué fracción de su volumen del cuatrimestre
                    vino del mes más grande de ese cuatrimestre (1.0 = un solo mes
                    explica el 100%)."""
                    agg = df_cuatri.groupby("fraccion")["volumen_total"].agg(["sum", "max"])
                    return (agg["max"] / agg["sum"]).rename("concentracion")

                concentracion_actual = _concentracion_mensual(actual)
                concentracion_anterior = _concentracion_mensual(anterior)

                precio_actual_cuatri = actual.groupby("fraccion", as_index=False).agg(
                    volumen=("volumen_total", "sum"), valor=("valor_total", "sum"),
                )
                precio_actual_cuatri = precio_actual_cuatri[precio_actual_cuatri["volumen"] >= VOLUMEN_MINIMO_PARA_PRECIO]
                precio_actual_cuatri["precio_actual"] = precio_actual_cuatri["valor"] / precio_actual_cuatri["volumen"]
                precio_actual_cuatri = precio_actual_cuatri[precio_actual_cuatri["precio_actual"] >= PRECIO_MINIMO_PLAUSIBLE_USD_TON]

                precio_anterior_cuatri = anterior.groupby("fraccion", as_index=False).agg(
                    volumen=("volumen_total", "sum"), valor=("valor_total", "sum"),
                )
                precio_anterior_cuatri = precio_anterior_cuatri[precio_anterior_cuatri["volumen"] >= VOLUMEN_MINIMO_PARA_PRECIO]
                precio_anterior_cuatri["precio_anterior"] = precio_anterior_cuatri["valor"] / precio_anterior_cuatri["volumen"]
                precio_anterior_cuatri = precio_anterior_cuatri[precio_anterior_cuatri["precio_anterior"] >= PRECIO_MINIMO_PLAUSIBLE_USD_TON]

                precio_comp = precio_actual_cuatri[["fraccion", "precio_actual"]].merge(
                    precio_anterior_cuatri[["fraccion", "precio_anterior"]], on="fraccion", how="inner",
                )
                if precio_comp.empty:
                    st.info("Sin fracciones con volumen en ambos cuatrimestres para comparar precio.")
                else:
                    precio_comp["delta_precio_pct"] = (
                        (precio_comp["precio_actual"] - precio_comp["precio_anterior"]) / precio_comp["precio_anterior"] * 100
                    )
                    precio_comp["etiqueta"] = precio_comp["fraccion"].map(
                        lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}"
                    )
                    precio_comp["concentracion_max"] = precio_comp["fraccion"].map(
                        lambda f: max(
                            concentracion_actual.get(f, 0.0), concentracion_anterior.get(f, 0.0),
                        )
                    )
                    precio_comp["confiable"] = precio_comp["concentracion_max"] <= UMBRAL_CONCENTRACION_MENSUAL
                    precio_comp = precio_comp.reindex(precio_comp["delta_precio_pct"].abs().sort_values(ascending=False).index)

                    top_precio_chart = precio_comp[precio_comp["confiable"]].head(10).copy()
                    if top_precio_chart.empty:
                        st.info(
                            "Todas las fracciones con variación de precio en este periodo están "
                            "marcadas como poco confiables (un solo mes concentra la mayoría del "
                            "volumen) — ver la tabla de abajo para el detalle."
                        )
                    else:
                        top_precio_chart["delta_abs_pct"] = top_precio_chart["delta_precio_pct"].abs()
                        st.plotly_chart(
                            barras_horizontales(
                                top_precio_chart, x="delta_abs_pct", y="etiqueta",
                                titulo=f"Mayor variación de precio unitario: {cuatri_sel} vs. {cuatri_anterior}",
                                x_label="% variación absoluta", max_items=10,
                            ),
                            width="stretch",
                        )
                    tabla_precio = precio_comp[
                        ["etiqueta", "precio_anterior", "precio_actual", "delta_precio_pct", "confiable"]
                    ].copy()
                    tabla_precio["precio_anterior"] = tabla_precio["precio_anterior"].map(lambda v: f"${v:,.0f}")
                    tabla_precio["precio_actual"] = tabla_precio["precio_actual"].map(lambda v: f"${v:,.0f}")
                    tabla_precio["delta_precio_pct"] = tabla_precio["delta_precio_pct"].map(lambda v: f"{v:+.1f}%")
                    tabla_precio["confiable"] = tabla_precio["confiable"].map(lambda b: "" if b else "⚠ concentrado en 1 mes")
                    tabla_precio.columns = [
                        "Fracción", f"{cuatri_anterior} (USD/ton)", f"{cuatri_sel} (USD/ton)",
                        "Variación precio (%)", "Confiabilidad",
                    ]
                    st.dataframe(tabla_precio, hide_index=True, width="stretch", height=320)

        st.divider()
        st.markdown("##### Precio unitario CANACERO (USD/ton)")
        st.caption(
            "Precio implícito = valor en dólares reportado / volumen en toneladas, por fracción y "
            "mes. Solo CANACERO trae valor en dólares limpio; SNICE no tiene un campo de precio "
            "estructurado por aviso (solo aparece, a veces, en texto libre dentro de la descripción). "
            f"Se excluyen meses con menos de {VOLUMEN_MINIMO_PARA_PRECIO} ton en esa fracción (con "
            "volumen casi cero el precio implícito se dispara — sin este filtro había meses con "
            "precios de hasta $5.7 millones USD/ton, de dividir entre 0.00006 toneladas) y precios "
            f"por debajo de ${PRECIO_MINIMO_PLAUSIBLE_USD_TON} USD/ton (2 filas aisladas en todo el "
            "histórico con un valor en dólares claramente mal capturado en el CSV de CANACERO)."
        )

        precio_frac = (
            series_frac[series_frac["volumen_total"] >= VOLUMEN_MINIMO_PARA_PRECIO].copy()
            if not series_frac.empty else series_frac
        )
        if not precio_frac.empty:
            precio_frac["precio_usd_ton"] = precio_frac["valor_total"] / precio_frac["volumen_total"]
            precio_frac = precio_frac[precio_frac["precio_usd_ton"] >= PRECIO_MINIMO_PLAUSIBLE_USD_TON]
        if precio_frac.empty:
            st.info("Sin datos de precio disponibles.")
        else:
            col_p1, col_p2 = st.columns([1.3, 1])
            with col_p1:
                fraccion_precio_sel = st.selectbox(
                    "Fracción", sorted(precio_frac["fraccion"].unique()),
                    format_func=lambda f: etiquetas_fraccion.get(f, f),
                    key="precio_fraccion_sel",
                )
                serie_precio = precio_frac[precio_frac["fraccion"] == fraccion_precio_sel].sort_values("periodo_mes")
                st.plotly_chart(
                    linea_temporal(
                        serie_precio, x="periodo_mes", y="precio_usd_ton",
                        titulo=f"Precio unitario mensual — {etiquetas_fraccion.get(fraccion_precio_sel, fraccion_precio_sel)}",
                        y_label="USD/ton", show_area=True,
                    ),
                    width="stretch",
                )
            with col_p2:
                periodo_scatter_sel = st.selectbox(
                    "Periodo (para el scatter)", periodos_canacero, index=0, key="precio_scatter_periodo",
                )
                scatter_df = precio_frac[precio_frac["periodo_mes"] == periodo_scatter_sel].copy()
                if scatter_df.empty:
                    st.info(f"Sin datos de precio para {periodo_scatter_sel}.")
                else:
                    scatter_df["etiqueta"] = scatter_df["fraccion"].map(
                        lambda f: etiquetas_fraccion.get(f, f)
                    )
                    st.plotly_chart(
                        scatter(
                            scatter_df, x="volumen_total", y="precio_usd_ton", hover_name="etiqueta",
                            titulo=f"Volumen vs. precio unitario — {periodo_scatter_sel}",
                            x_label="Ton", y_label="USD/ton",
                        ),
                        width="stretch",
                    )
                    st.caption(
                        "Cada punto es una fracción. Abajo a la derecha = mucho volumen a precio bajo "
                        "(posible presión de oferta); arriba a la izquierda = poco volumen a precio alto."
                    )

        st.divider()
        st.markdown("###### Fracciones CANACERO por volumen nacional")
        st.caption(
            "Estas son las fracciones del catálogo TYASA, pero el volumen que se ve aquí es el "
            "total nacional reportado por CANACERO (no el volumen propio de TYASA)."
        )
        fracciones_top_full = load_top_fracciones_tyasa(
            periodo_canacero_sel, movimiento_dash, limite=100, fracciones=fracciones_filtro,
        )
        if fracciones_top_full.empty:
            st.info("Sin fracciones con movimiento en este periodo.")
        else:
            etiquetas_chart = {
                row.fraccion: (
                    f"{row.fraccion} — "
                    f"{FRACCIONES_TYASA_DESCRIPCION.get(row.fraccion, row.descripcion or 'sin descripción')}"
                )
                for row in fracciones_top_full.itertuples()
            }
            default_chart = fracciones_top_full["fraccion"].head(15).tolist()
            seleccion_chart = st.multiselect(
                "Fracciones a mostrar en la gráfica",
                fracciones_top_full["fraccion"].tolist(),
                default=default_chart,
                format_func=lambda f: etiquetas_chart[f],
                key="canacero_fracciones_chart_sel",
            )
            if not seleccion_chart:
                st.info("Selecciona al menos una fracción para graficar.")
            else:
                fracciones_top_chart = fracciones_top_full[
                    fracciones_top_full["fraccion"].isin(seleccion_chart)
                ].copy()
                fracciones_top_chart["etiqueta"] = fracciones_top_chart["fraccion"].map(etiquetas_chart)
                st.plotly_chart(
                    barras_horizontales(
                        fracciones_top_chart, x="volumen_total", y="etiqueta",
                        titulo="Fracciones CANACERO por volumen nacional", x_label="Ton",
                        max_items=len(seleccion_chart),
                    ),
                    width="stretch",
                )

        st.divider()
        st.markdown("##### Consulta por fracción específica")
        st.caption(
            "Elige una sola fracción para ver su volumen nacional (CANACERO) y, al lado, "
            "qué empresas la están importando según SNICE."
        )

        fraccion_sel = st.selectbox(
            "Fracción TYASA", opciones_fraccion, format_func=lambda f: etiquetas_fraccion[f],
            key="canacero_fraccion_sel",
        )

        col_f1, col_f2 = st.columns([1.3, 1])
        with col_f1:
            serie_fraccion = load_serie_fraccion(fraccion_sel, movimiento_dash)
            st.plotly_chart(
                linea_temporal(
                    serie_fraccion, x="periodo_mes", y="volumen_total",
                    titulo=f"Volumen nacional mensual — {etiquetas_fraccion[fraccion_sel]}",
                    y_label="Ton", show_area=True,
                ),
                width="stretch",
            )

        with col_f2:
            avisos_fraccion = load_avisos_fraccion_exacta(periodo_sel, fraccion_sel)
            st.markdown(f"**Avisos SNICE — {fraccion_sel}** (periodo {periodo_sel})")
            if avisos_fraccion.empty:
                st.info(
                    "Sin avisos SNICE para esta fracción en este periodo "
                    "(el detalle solo cubre los periodos que siguen en BRONZE)."
                )
            else:
                tabla_f = avisos_fraccion.copy()
                tabla_f["volumen_aviso"] = (tabla_f["volumen_aviso"] / 1000).map(lambda v: f"{v:,.2f}")
                tabla_f = tabla_f.rename(columns={
                    "razon_social": "Razón social", "pais_origen": "País",
                    "volumen_aviso": "Volumen (ton)", "fecha_tramite": "Fecha trámite",
                    "inicio_vigencia": "Inicio vigencia", "fin_vigencia": "Fin vigencia",
                })
                st.dataframe(
                    tabla_f[["Razón social", "País", "Volumen (ton)", "Fecha trámite", "Inicio vigencia", "Fin vigencia"]],
                    hide_index=True, width="stretch", height=280,
                )

        with st.expander("Ranking de empresas (SNICE, fracciones TYASA)"):
            filtro_ranking = st.selectbox(
                "Filtrar por fracción (opcional)",
                ["Todas las fracciones TYASA"] + opciones_fraccion,
                format_func=lambda f: f if f == "Todas las fracciones TYASA" else etiquetas_fraccion[f],
                key="canacero_ranking_filtro_fraccion",
            )
            ranking_df = (
                empresas_tyasa if filtro_ranking == "Todas las fracciones TYASA"
                else load_empresas_fraccion_exacta(periodo_sel, filtro_ranking)
            )
            if ranking_df.empty:
                st.caption("Sin datos para este filtro.")
            else:
                tabla = ranking_df.head(30).copy()
                tabla["volumen_total"] = (tabla["volumen_total"] / 1000).map(lambda v: f"{v:,.1f}")
                tabla = tabla.rename(columns={
                    "razon_social": "Razón social", "volumen_total": "Volumen (ton)",
                    "avisos": "Avisos", "fracciones_distintas": "Fracciones TYASA", "paises_distintos": "Países",
                })
                cols_mostrar = [c for c in ["Razón social", "Volumen (ton)", "Avisos", "Fracciones TYASA", "Países"] if c in tabla.columns]
                st.dataframe(tabla[cols_mostrar], hide_index=True, width="stretch")

st.caption(
    f"Datos: SNICE — Secretaría de Economía · Periodo {periodo_sel} · "
    "Catálogo: fracciones TYASA (capítulos 72 y 73) · Actualización mensual automática"
)
