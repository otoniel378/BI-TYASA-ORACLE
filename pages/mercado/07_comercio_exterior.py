"""
pages/mercado/07_comercio_exterior.py — Comercio Exterior Siderúrgico (SNICE)

Avisos automáticos de importación de productos siderúrgicos, categorizados por
partida arancelaria (catálogo oficial TIGIE). Fuente: SNICE / Secretaría de
Economía, actualización mensual automática (scripts/download_snice_siderurgico.py
+ scripts/load_snice_to_oracle.py, vía GitHub Actions).

DOM-STABLE: todo HTML dinámico usa st.html() (no st.markdown unsafe_allow_html
para contenido que cambia entre reruns).
"""

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd

from config import COLORS
from core.components.kpi_cards import render_kpi_row
from core.components.tables import _boton_descarga
from mercado.snice.loaders import (
    load_periodos_disponibles,
    load_resumen,
    load_top_categorias,
    load_top_paises,
    load_top_empresas,
    load_empresas_filtradas,
    load_categorias_filtradas,
    load_paises_filtrados,
    load_empresa_detalle,
    load_categorias_disponibles,
    load_paises_disponibles,
    load_avisos_detalle,
    load_avisos_para_exportar,
)

st.title("Comercio Exterior — Siderúrgico")
st.caption(
    "Avisos automáticos de importación de productos siderúrgicos · Fuente: SNICE "
    "(Secretaría de Economía) · Categorías según catálogo oficial TIGIE"
)

# ---------------------------------------------------------------------------
# Datos disponibles
# ---------------------------------------------------------------------------
try:
    periodos = load_periodos_disponibles()
    DATOS_REALES = True
except Exception as e:
    periodos = []
    DATOS_REALES = False
    st.warning(f"No se pudo conectar a Oracle: {e}")

if not periodos:
    st.info(
        "Todavía no hay datos de comercio exterior cargados. "
        "Corre `python scripts/load_snice_to_oracle.py` para la primera carga."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Barra de filtros
# ---------------------------------------------------------------------------
with st.form("snice_filtros", border=True):
    c1, c2, c3, c4, c5 = st.columns([1, 1.3, 1.2, 1.6, 0.8])

    with c1:
        periodo_sel = st.selectbox("Periodo", periodos, index=0)

    cats_df = load_categorias_disponibles(periodo_sel)
    cat_labels = cats_df["categoria_producto"].tolist() if not cats_df.empty else []
    cat_partida_map = dict(zip(cat_labels, cats_df["partida"])) if not cats_df.empty else {}
    with c2:
        cat_sel = st.selectbox("Categoría de producto", ["Todas las categorías"] + cat_labels)

    paises_disp = load_paises_disponibles(periodo_sel)
    with c3:
        pais_sel = st.selectbox("País de origen", ["Todos los países"] + paises_disp)

    with c4:
        busqueda_sel = st.text_input(
            "Buscar empresa (razón social)", placeholder="Ej. POSCO, GONVAUTO, TRUPER…"
        )

    with c5:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        st.form_submit_button("Aplicar filtros", use_container_width=True, type="primary")

partida_filtro = cat_partida_map.get(cat_sel) if cat_sel != "Todas las categorías" else None
pais_filtro = pais_sel if pais_sel != "Todos los países" else None
busqueda_filtro = busqueda_sel.strip() if busqueda_sel and busqueda_sel.strip() else None
hay_filtro_bronze = bool(pais_filtro or busqueda_filtro)  # afecta categorías/países (solo BRONZE tiene esas dimensiones)

# ---------------------------------------------------------------------------
# KPIs del periodo
# ---------------------------------------------------------------------------
resumen = load_resumen(periodo_sel)
if resumen:
    volumen_ton = (resumen.get("volumen_total") or 0) / 1000
    render_kpi_row([
        {"label": "Volumen importado", "value": round(volumen_ton), "suffix": " ton", "icon": "📦"},
        {"label": "Avisos autorizados", "value": int(resumen.get("avisos_total") or 0), "icon": "📄"},
        {"label": "Empresas importadoras", "value": int(resumen.get("empresas_distintas") or 0), "icon": "🏢"},
        {"label": "Países de origen", "value": int(resumen.get("paises_distintos") or 0), "icon": "🌐"},
    ])

st.divider()

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


# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------
tab_resumen, tab_categorias, tab_paises, tab_empresas, tab_detalle = st.tabs(
    ["Resumen", "Categorías", "Países", "Empresas", "Detalle de avisos"]
)

# ── RESUMEN ──────────────────────────────────────────────────────────────────
with tab_resumen:
    col_a, col_b = st.columns([1.4, 1])

    cats_resumen = (
        load_categorias_filtradas(periodo_sel, pais=pais_filtro, busqueda=busqueda_filtro)
        if hay_filtro_bronze else load_top_categorias(periodo_sel)
    )
    paises_resumen = (
        load_paises_filtrados(periodo_sel, partida=partida_filtro, busqueda=busqueda_filtro)
        if (partida_filtro or busqueda_filtro) else load_top_paises(periodo_sel)
    )

    with col_a:
        html = _card_open("¿Qué se está importando?", "Volumen por categoría de producto (partida TIGIE)")
        html += _rank_list_html(cats_resumen, "categoria_producto", "subcategoria", max_filas=6)
        html += _CARD_CLOSE
        st.html(html)

    with col_b:
        html = _card_open("¿De dónde viene?", "% del volumen por país de origen")
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
                    f"⚠️ Los 3 países principales concentran <b>{conc3:.1f}%</b> del volumen — "
                    f"dependencia alta de pocos orígenes.</div>"
                )
        html += _CARD_CLOSE
        st.html(html)

# ── CATEGORÍAS ───────────────────────────────────────────────────────────────
with tab_categorias:
    subtitulo = "Agrupadas por partida arancelaria (catálogo oficial TIGIE, capítulos 72 y 73)"
    if hay_filtro_bronze:
        subtitulo += " — filtrado"
    html = _card_open(f"Todas las categorías ({len(cats_resumen)})", subtitulo)
    html += _rank_list_html(cats_resumen, "categoria_producto", "subcategoria")
    html += _CARD_CLOSE
    st.html(html)

# ── PAÍSES ───────────────────────────────────────────────────────────────────
with tab_paises:
    subtitulo = f"{len(paises_resumen)} países de origen distintos" + (" — filtrado" if (partida_filtro or busqueda_filtro) else "")
    html = _card_open("Volumen por país de origen", subtitulo)
    html += _rank_list_html(paises_resumen, "pais_origen", None)
    html += _CARD_CLOSE
    st.html(html)

# ── EMPRESAS ─────────────────────────────────────────────────────────────────
with tab_empresas:
    if partida_filtro or pais_filtro or busqueda_filtro:
        empresas_df = load_empresas_filtradas(
            periodo_sel, partida=partida_filtro, pais=pais_filtro, busqueda=busqueda_filtro,
        )
        vol_col, cat_col = "volumen_total", "categorias_distintas"
    else:
        empresas_df = load_top_empresas(periodo_sel)
        vol_col, cat_col = "volumen_total", "fracciones_distintas"

    st.markdown(f"**Ranking de empresas importadoras** ({len(empresas_df)} encontradas)")

    if empresas_df.empty:
        st.info("Sin empresas para este filtro.")
    else:
        tabla = empresas_df.head(30).copy()
        tabla["volumen_total"] = (tabla["volumen_total"] / 1000).round(1)
        tabla = tabla.rename(columns={
            "razon_social": "Razón social", "volumen_total": "Volumen (ton)",
            "avisos": "Avisos", cat_col: "Categorías", "paises_distintos": "Países",
        })
        cols_mostrar = [c for c in ["Razón social", "Volumen (ton)", "Avisos", "Categorías", "Países"] if c in tabla.columns]
        st.dataframe(tabla[cols_mostrar], hide_index=True, use_container_width=True, height=340)

        st.markdown("##### Ficha de empresa")
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
                        av["volumen_aviso"] = av["volumen_aviso"].round(0)
                        av = av.rename(columns={
                            "fraccion_arancelaria": "Fracción", "categoria_producto": "Categoría",
                            "pais_origen": "País", "volumen_aviso": "Volumen (kg)",
                            "fecha_tramite": "Fecha trámite",
                        })
                        cols = [c for c in ["Fecha trámite", "Fracción", "Categoría", "País", "Volumen (kg)"] if c in av.columns]
                        st.dataframe(av[cols], hide_index=True, use_container_width=True)
            else:
                st.caption(
                    "Sin detalle disponible para esta empresa en el periodo seleccionado "
                    "(el detalle solo se conserva ~2 meses; el histórico agregado vive en los rankings de arriba)."
                )

# ── DETALLE DE AVISOS ────────────────────────────────────────────────────────
with tab_detalle:
    if "snice_pagina" not in st.session_state:
        st.session_state.snice_pagina = 1

    TAM_PAGINA = 25
    df_detalle, total = load_avisos_detalle(
        periodo_sel, partida=partida_filtro, pais=pais_filtro,
        busqueda_empresa=busqueda_filtro, pagina=st.session_state.snice_pagina, tam_pagina=TAM_PAGINA,
    )

    st.markdown(f"**Detalle de avisos** ({total:,} registros con los filtros actuales)")

    if df_detalle.empty:
        st.info("Sin avisos para este filtro (recuerda: el detalle solo cubre los últimos 2 periodos cargados).")
    else:
        tabla = df_detalle.copy()
        tabla["volumen_aviso"] = tabla["volumen_aviso"].round(0)
        tabla = tabla.rename(columns={
            "folio_tramite": "Folio", "razon_social": "Razón social", "fraccion_arancelaria": "Fracción",
            "categoria_producto": "Categoría", "pais_origen": "País", "volumen_aviso": "Volumen (kg)",
            "fecha_tramite": "Fecha",
        })
        st.dataframe(
            tabla[["Fecha", "Folio", "Razón social", "Fracción", "Categoría", "País", "Volumen (kg)"]],
            hide_index=True, use_container_width=True, height=360,
        )

        total_paginas = max(1, -(-total // TAM_PAGINA))
        c_prev, c_info, c_next = st.columns([1, 3, 1])
        with c_prev:
            if st.button("‹ Anterior", disabled=st.session_state.snice_pagina <= 1, use_container_width=True):
                st.session_state.snice_pagina -= 1
                st.rerun()
        with c_info:
            st.markdown(
                f"<div style='text-align:center;color:{COLORS['text_light']};font-size:0.85rem;padding-top:6px;'>"
                f"Página {st.session_state.snice_pagina} de {total_paginas}</div>",
                unsafe_allow_html=True,
            )
        with c_next:
            if st.button("Siguiente ›", disabled=st.session_state.snice_pagina >= total_paginas, use_container_width=True):
                st.session_state.snice_pagina += 1
                st.rerun()

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        df_export = load_avisos_para_exportar(
            periodo_sel, partida=partida_filtro, pais=pais_filtro, busqueda_empresa=busqueda_filtro,
        )
        _boton_descarga(df_export, key=f"snice_detalle_{periodo_sel}", label="⬇ Exportar todo el filtro a Excel")

st.caption(
    f"Datos: SNICE — Secretaría de Economía · Periodo {periodo_sel} · "
    "Categorización: catálogo oficial TIGIE (capítulos 72 y 73) · Actualización mensual automática"
)
