"""
03_industria.py — Monitor de la Industria Siderúrgica — TYASA BI
Mañanera presidencial · Noticias Nacionales e Internacionales · Síntesis IA

DOM-STABLE: cero componentes condicionales.
  - st.spinner eliminado → st.empty() con HTML de estado
  - Todas las secciones de resultado usan 1 st.empty() fijo
  - st.chat_message loop eliminado → _render_chat_html() con burbujas HTML
"""
import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import json
import datetime
from pathlib import Path

import streamlit as st
from config import COLORS
from mercado_noticias.analytics.noticias import (
    buscar_noticias_industria,
    buscar_noticias_sector,
    buscar_query_libre,
    GRUPOS_INDUSTRIA,
    GRUPOS_NACIONAL,
    GRUPOS_INTERNACIONAL,
    GRUPO_STYLE_NACIONAL,
    GRUPO_STYLE_INTERNACIONAL,
    _resolve_gnews_batch,
    buscar_noticias_multifuente,
)
from mercado_noticias.analytics.ai_analysis import sintesis_industrial, _call_gemini_text, sintesis_global, cargar_cache_hoy
from mercado_noticias.analytics.mananera import analizar_mananera, MANANERA_CACHE_DIR, MANANERA_CACHE_DAYS
from mercado_noticias.analytics.detector import detectar_quiebres_automatico
from core.components.filters import sidebar_header
from core.components.kpi_cards import seccion_titulo
from mercado_noticias.loaders import load_variables_mercado
from core.components.market_summary import build_indicadores_html

# ── API key ───────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

# ── Paletas locales ───────────────────────────────────────────────────────────
ALERTA_STYLE: dict[str, tuple[str, str]] = {
    "Alto":  ("#DC2626", "#FEE2E2"),
    "Medio": ("#D97706", "#FEF3C7"),
    "Bajo":  ("#059669", "#D1FAE5"),
}

# ── Reconocimiento de fuentes periodísticas ────────────────────────────────────
# (color_texto, color_fondo, icono)
_FUENTES_DB: dict[str, tuple[str, str, str]] = {
    # ── Acero / commodities especializado ────────────────────────────────────
    "fastmarkets":       ("#7C3AED", "#EDE9FE", "⚡"),   # premium steel intel
    "cru":               ("#1B3A5C", "#DBEAFE", "📐"),   # CRU Group
    "meps":              ("#0F766E", "#CCFBF1", "📈"),   # MEPS International
    "metal bulletin":    ("#4338CA", "#E0E7FF", "⛏️"),
    "steelfirst":        ("#7C3AED", "#EDE9FE", "🔩"),
    "kallanish":         ("#4338CA", "#E0E7FF", "📊"),
    "platts":            ("#4338CA", "#E0E7FF", "📊"),
    "s&p global":        ("#4338CA", "#E0E7FF", "📊"),
    "reporteacero":      ("#DC2626", "#FEE2E2", "🔩"),
    "worldsteel":        ("#1B3A5C", "#E8EFF6", "⚙️"),
    "canacero":          ("#DC2626", "#FEE2E2", "🏭"),
    "alacero":           ("#DC2626", "#FEE2E2", "🏭"),
    # ── Nacionales México ─────────────────────────────────────────────────────
    "reforma":           ("#C8102E", "#FEE2E2", "📰"),
    "el financiero":     ("#059669", "#D1FAE5", "💼"),
    "el universal":      ("#1B3A5C", "#E8EFF6", "📰"),
    "milenio":           ("#D97706", "#FEF3C7", "📰"),
    "excélsior":         ("#4338CA", "#E0E7FF", "📰"),
    "excelsior":         ("#4338CA", "#E0E7FF", "📰"),
    "la jornada":        ("#374151", "#F3F4F6", "📰"),
    "el economista":     ("#059669", "#D1FAE5", "📈"),
    "expansión":         ("#0F766E", "#CCFBF1", "💼"),
    "expansion":         ("#0F766E", "#CCFBF1", "💼"),
    "forbes":            ("#DC2626", "#FEE2E2", "💼"),
    "líder empresarial": ("#4338CA", "#E0E7FF", "🏢"),
    "infraestructura 2030": ("#0F766E", "#CCFBF1", "🏗️"),
    "cb televisión":     ("#7C3AED", "#EDE9FE", "📺"),
    "esemanal":          ("#059669", "#D1FAE5", "💻"),
    "infobae":           ("#4338CA", "#E0E7FF", "🌎"),
    "el norte":          ("#C8102E", "#FEE2E2", "📰"),
    "vanguardia":        ("#0F766E", "#CCFBF1", "📰"),
    # ── Internacional ─────────────────────────────────────────────────────────
    "reuters":           ("#D97706", "#FEF3C7", "🌍"),
    "bloomberg":         ("#1B3A5C", "#E8EFF6", "🌍"),
    "financial times":   ("#D97706", "#FEF3C7", "📊"),
    "wall street":       ("#1B3A5C", "#E8EFF6", "🌍"),
    "economist":         ("#C8102E", "#FEE2E2", "🌍"),
    "indexbox":          ("#4338CA", "#E0E7FF", "📦"),
}


def _get_fuente_style(fuente: str) -> tuple[str, str, str]:
    """Retorna (color_texto, color_fondo, icono) para una fuente periodística."""
    fl = fuente.lower()
    for key, style in _FUENTES_DB.items():
        if key in fl:
            return style
    return ("#6B7280", "#F3F4F6", "📰")

# ════════════════════════════════════════════════════════════════════════════
# HELPERS — NOTICIAS
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def _noticias_grupo(grupo: str, max_r: int = 15) -> list[dict]:
    return buscar_noticias_sector(grupo, max_resultados=max_r)


@st.cache_data(ttl=900, show_spinner=False)
def _noticias_alerta_cached(variable: str, max_r: int = 3) -> list[dict]:
    """Noticias del Monitor de Quiebres para una variable en alerta (caché 15 min)."""
    return buscar_noticias_multifuente(variable, ventana_dias=7, max_resultados=max_r)


def _filtrar_por_fecha(noticias: list[dict], desde: str, hasta: str) -> list[dict]:
    """Filtra por rango de fechas. Artículos con fecha van primero (más reciente → más antiguo),
    artículos sin fecha van al final para no perder contenido."""
    con_fecha = []
    sin_fecha = []
    for n in noticias:
        fp = (n.get("fecha_pub") or "")[:10]
        if fp:
            if desde <= fp <= hasta:
                con_fecha.append(n)
        else:
            sin_fecha.append(n)
    # Ordenar con_fecha del más reciente al más antiguo
    con_fecha.sort(key=lambda x: x.get("fecha_pub", ""), reverse=True)
    return con_fecha + sin_fecha


_BUSQ_STYLE: dict[str, tuple[str, str]] = {
    "Búsqueda": ("#1B3A5C", "#E8EFF6"),
}


def _render_busqueda_libre(noticias: list[dict], query: str) -> str:
    """Resultados de búsqueda libre en estilo Chronicle con header especial."""
    c_txt = "#1B3A5C"
    if not noticias:
        return (
            _CHRONICLE_CSS +
            f'<div class="cn"><div class="cn-empty">'
            f'<div class="cn-empty-icon">🔍</div>'
            f'<div>No se encontraron resultados para <b>"{query}"</b></div>'
            f'<div style="font-size:11px;margin-top:6px;color:#D1D5DB;">'
            f'Intenta con términos más generales o en otro idioma</div>'
            f'</div></div>'
        )
    # Header de búsqueda
    header = (
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;'
        f'padding:12px 16px;background:#F0F4F8;border-radius:10px;border-left:4px solid {c_txt};">'
        f'<span style="font-size:18px;">🔍</span>'
        f'<div>'
        f'<div style="font-size:11px;color:#6B7280;font-weight:600;letter-spacing:.06em;">RESULTADOS DE BÚSQUEDA</div>'
        f'<div style="font-size:14px;font-weight:700;color:{c_txt};">"{query}" · {len(noticias)} artículo(s)</div>'
        f'</div></div>'
    )
    grid_html = _render_noticias_grid(noticias, "Búsqueda", _BUSQ_STYLE)
    # Extraemos solo el contenido sin el CSS (ya lo incluye _render_noticias_grid)
    return grid_html.replace('<div class="cn">', f'<div class="cn">{header}', 1)


_CHRONICLE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800&family=Inter:wght@400;500;600;700&display=swap');
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#fff;}
.cn{font-family:'Inter',sans-serif;background:#fff;color:#1b1b1d;padding:4px 0 24px 0;}
/* ── Hero layout ── */
.cn-hero{display:grid;grid-template-columns:62% 38%;gap:28px;margin-bottom:28px;padding-bottom:28px;border-bottom:1px solid #E2E8F0;}
.cn-main-art{display:flex;flex-direction:column;}
.cn-gradient{height:160px;border-radius:8px;display:flex;align-items:flex-end;padding:14px 18px;margin-bottom:14px;}
.cn-cat-pill{font-size:10px;font-weight:700;letter-spacing:.10em;background:rgba(255,255,255,.22);color:#fff;padding:4px 13px;border-radius:20px;}
.cn-featured-badge{font-size:10px;font-weight:700;color:rgba(255,255,255,.88);background:rgba(255,255,255,.15);padding:3px 10px;border-radius:10px;}
.cn-pill-row{display:flex;justify-content:space-between;align-items:center;}
.cn-date{font-size:10px;color:#9CA3AF;letter-spacing:.04em;margin-bottom:8px;}
.cn-main-title{font-family:'Playfair Display',serif;font-size:22px;font-weight:800;color:#111827;line-height:1.32;margin-bottom:10px;}
.cn-main-desc{font-size:13px;color:#4B5563;line-height:1.72;margin-bottom:16px;flex:1;}
.cn-footer{display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid #F3F4F6;}
.cn-source{font-size:10px;font-weight:700;padding:3px 10px;border-radius:14px;}
.cn-read-btn{display:inline-flex;align-items:center;gap:5px;color:#fff;font-weight:700;font-size:11px;text-decoration:none;padding:7px 16px;border-radius:20px;letter-spacing:.02em;}
/* ── Secondary sidebar ── */
.cn-sidebar{display:flex;flex-direction:column;gap:0;}
.cn-sec-item{padding:16px 0;border-bottom:1px solid #E2E8F0;}
.cn-sec-item:last-child{border-bottom:none;}
.cn-sec-cat{font-size:9px;font-weight:700;letter-spacing:.10em;display:block;margin-bottom:6px;}
.cn-sec-title{font-family:'Playfair Display',serif;font-size:15px;font-weight:700;color:#111827;line-height:1.38;margin-bottom:6px;}
.cn-sec-desc{font-size:11px;color:#6B7280;line-height:1.6;margin-bottom:8px;}
.cn-sec-footer{display:flex;justify-content:space-between;align-items:center;}
.cn-sec-date{font-size:9px;color:#9CA3AF;}
.cn-sec-read{font-size:10px;font-weight:700;text-decoration:none;}
/* ── Latest Stories header ── */
.cn-latest-hdr{display:flex;align-items:center;gap:10px;margin:4px 0 16px 0;padding-bottom:10px;border-bottom:2px solid #1b1b1d;}
.cn-latest-bar{width:4px;height:22px;border-radius:2px;flex-shrink:0;}
.cn-latest-title{font-family:'Playfair Display',serif;font-size:18px;font-weight:800;color:#111827;}
/* ── Card grid ── */
.cn-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}
.cn-card{display:flex;flex-direction:column;background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;transition:box-shadow .2s,transform .2s;}
.cn-card:hover{box-shadow:0 8px 24px rgba(0,0,0,.08);transform:translateY(-2px);}
.cn-card-top{height:3px;}
.cn-card-body{padding:14px 15px;flex:1;display:flex;flex-direction:column;}
.cn-card-meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px;}
.cn-card-cat{font-size:9px;font-weight:700;letter-spacing:.08em;padding:2px 9px;border-radius:14px;}
.cn-card-date{font-size:9px;color:#9CA3AF;}
.cn-card-title{font-family:'Playfair Display',serif;font-size:14px;font-weight:700;color:#111827;line-height:1.42;margin-bottom:7px;flex:1;}
.cn-card-desc{font-size:11px;color:#6B7280;line-height:1.62;margin-bottom:10px;}
.cn-card-footer{display:flex;justify-content:space-between;align-items:center;padding-top:9px;border-top:1px solid #F3F4F6;margin-top:auto;}
.cn-card-source{font-size:9px;font-weight:700;padding:2px 8px;border-radius:12px;}
.cn-card-read{font-size:10px;font-weight:700;text-decoration:none;}
.cn-minread{font-size:9px;color:#9CA3AF;}
/* ── Empty state ── */
.cn-empty{text-align:center;padding:48px 0;color:#9CA3AF;}
.cn-empty-icon{font-size:36px;margin-bottom:10px;}
.cn-count{font-size:11px;color:#6B7280;margin-bottom:16px;}
</style>
"""


def _min_read(titulo: str, desc: str) -> str:
    return f"{max(1, (len(titulo) + len(desc)) // 250)} min"


def _render_news_card(n: dict, grupo: str,
                      style_map: dict | None = None) -> str:
    """Mantenido por compatibilidad — delega a Chronicle card."""
    default_style = {**GRUPO_STYLE_NACIONAL, **GRUPO_STYLE_INTERNACIONAL}
    sm = style_map or default_style
    return _chronicle_card(n, grupo, sm)


def _chronicle_card(n: dict, grupo: str, sm: dict) -> str:
    c_txt, c_bg = sm.get(grupo, ("#374151", "#F9FAFB"))
    titulo = (n.get("titulo", "") or "").strip()
    desc   = (n.get("descripcion", "") or "").strip()[:180]
    fuente = (n.get("fuente", "") or "").strip()
    url    = (n.get("url", "") or "").strip()
    fecha  = (n.get("fecha_pub", "") or "").strip()
    fc, fb, fi = _get_fuente_style(fuente)
    mr    = _min_read(titulo, desc)
    leer  = f'<a href="{url}" target="_blank" class="cn-card-read" style="color:{c_txt};">Leer →</a>' if url else ""
    return (
        f'<div class="cn-card">'
        f'<div class="cn-card-top" style="background:linear-gradient(90deg,{c_txt},{c_txt}55);"></div>'
        f'<div class="cn-card-body">'
        f'<div class="cn-card-meta">'
        f'<span class="cn-card-cat" style="background:{c_bg};color:{c_txt};">{grupo.upper()}</span>'
        f'<span class="cn-card-date">📅 {fecha}</span>'
        f'</div>'
        f'<div class="cn-card-title">{titulo}</div>'
        f'<div class="cn-card-desc">{desc}</div>'
        f'<div class="cn-card-footer">'
        f'<span class="cn-card-source" style="background:{fb};color:{fc};">{fi} {fuente}</span>'
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<span class="cn-minread">⏱ {mr}</span>{leer}</div>'
        f'</div></div></div>'
    )


def _chronicle_secondary(n: dict, grupo: str, sm: dict) -> str:
    c_txt, _ = sm.get(grupo, ("#374151", "#F9FAFB"))
    titulo = (n.get("titulo", "") or "").strip()
    desc   = (n.get("descripcion", "") or "").strip()[:130]
    fuente = (n.get("fuente", "") or "").strip()
    url    = (n.get("url", "") or "").strip()
    fecha  = (n.get("fecha_pub", "") or "").strip()
    fc, fb, fi = _get_fuente_style(fuente)
    leer = f'<a href="{url}" target="_blank" class="cn-sec-read" style="color:{c_txt};">Leer →</a>' if url else ""
    return (
        f'<div class="cn-sec-item">'
        f'<span class="cn-sec-cat" style="color:{c_txt};">{grupo.upper()}</span>'
        f'<div class="cn-sec-title">{titulo}</div>'
        f'<div class="cn-sec-desc">{desc}</div>'
        f'<div class="cn-sec-footer">'
        f'<span class="cn-sec-date">📅 {fecha} · <span style="background:{fb};color:{fc};padding:1px 7px;border-radius:10px;font-size:9px;font-weight:700;">{fi} {fuente}</span></span>'
        f'{leer}</div></div>'
    )


def _render_noticias_grid(noticias: list[dict], grupo: str, sm: dict) -> str:
    """Renderiza sección completa estilo The Chronicle: hero + sidebar + grid."""
    c_txt, _ = sm.get(grupo, ("#374151", "#F9FAFB"))

    if not noticias:
        return (
            _CHRONICLE_CSS +
            f'<div class="cn"><div class="cn-empty">'
            f'<div class="cn-empty-icon">📭</div>'
            f'<div>Sin noticias para <b>{grupo}</b> en el rango seleccionado.</div>'
            f'<div style="font-size:11px;margin-top:8px;color:#D1D5DB;">Intenta ampliar el rango de fechas</div>'
            f'</div></div>'
        )

    count_txt = f'<div class="cn-count">{len(noticias)} artículo(s) en el período</div>'
    main_n   = noticias[0]
    sidebar_n = noticias[1:3]
    grid_n    = noticias[3:]

    # ── Hero principal ────────────────────────────────────────────────────────
    m_titulo = (main_n.get("titulo", "") or "").strip()
    m_desc   = (main_n.get("descripcion", "") or "").strip()[:320]
    m_fuente = (main_n.get("fuente", "") or "").strip()
    m_url    = (main_n.get("url", "") or "").strip()
    m_fecha  = (main_n.get("fecha_pub", "") or "").strip()
    m_fc, m_fb, m_fi = _get_fuente_style(m_fuente)
    m_leer = (
        f'<a href="{m_url}" target="_blank" class="cn-read-btn" style="background:{c_txt};">Leer artículo →</a>'
    ) if m_url else ""

    main_html = (
        f'<div class="cn-main-art">'
        f'<div class="cn-gradient" style="background:linear-gradient(135deg,{c_txt},{c_txt}99);">'
        f'<div class="cn-pill-row" style="width:100%;">'
        f'<span class="cn-cat-pill">{grupo.upper()}</span>'
        f'<span class="cn-featured-badge">⭐ DESTACADO</span>'
        f'</div></div>'
        f'<div class="cn-date">📅 {m_fecha}</div>'
        f'<div class="cn-main-title">{m_titulo}</div>'
        f'<div class="cn-main-desc">{m_desc}</div>'
        f'<div class="cn-footer">'
        f'<span class="cn-source" style="background:{m_fb};color:{m_fc};">{m_fi} {m_fuente}</span>'
        f'{m_leer}</div></div>'
    )

    # ── Sidebar secundario ────────────────────────────────────────────────────
    sec_items = "".join(_chronicle_secondary(n, grupo, sm) for n in sidebar_n)
    sidebar_html = f'<div class="cn-sidebar">{sec_items}</div>' if sec_items else "<div></div>"

    hero_html = f'<div class="cn-hero">{main_html}{sidebar_html}</div>'

    # ── Grid Latest Stories ───────────────────────────────────────────────────
    grid_html = ""
    if grid_n:
        cards = "".join(_chronicle_card(n, grupo, sm) for n in grid_n)
        grid_html = (
            f'<div class="cn-latest-hdr">'
            f'<div class="cn-latest-bar" style="background:{c_txt};"></div>'
            f'<span class="cn-latest-title">Últimas Noticias</span>'
            f'</div>'
            f'<div class="cn-grid">{cards}</div>'
        )

    return _CHRONICLE_CSS + f'<div class="cn">{count_txt}{hero_html}{grid_html}</div>'


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — SÍNTESIS
# ════════════════════════════════════════════════════════════════════════════

def _render_sintesis_full(result: dict | None, loading: bool = False) -> str:
    if loading:
        return (
            "<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            "padding:20px;color:#0369A1;font-size:13px;text-align:center;'>"
            "<div style='font-size:22px;margin-bottom:8px;'>⏳</div>"
            "<b>Generando síntesis industrial…</b><br>"
            "<span style='font-size:12px;color:#0284C7;'>"
            "Consultando noticias y analizando tendencias con IA.</span></div>"
        )
    if result is None:
        return (
            "<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            "padding:16px;color:#0369A1;font-size:13px;'>"
            "ℹ️ Haz clic en <b>▶ Generar síntesis</b> para obtener el resumen ejecutivo "
            "de la industria.</div>"
        )
    err = result.get("_error", "")
    if err:
        return (
            f"<div style='background:#FEF2F2;border:1px solid #FCA5A5;border-radius:8px;"
            f"padding:16px;color:#DC2626;font-size:13px;'>⚠️ {err}</div>"
        )
    nivel    = result.get("nivel_alerta", "—")
    nc_txt, nc_bg = ALERTA_STYLE.get(nivel, ("#6B7280", "#F3F4F6"))
    cached_s = result.get("_cached", False)
    cache_b  = (
        '<span style="background:#F3F4F6;color:#6B7280;padding:4px 10px;'
        'border-radius:20px;font-size:11px;">💾 Caché</span>'
    ) if cached_s else ""
    header = (
        f"<div style='display:flex;gap:10px;align-items:center;margin-bottom:14px;'>"
        f"<span style='background:{nc_bg};color:{nc_txt};padding:4px 14px;"
        f"border-radius:20px;font-size:12px;font-weight:700;'>Nivel de alerta: {nivel}</span>"
        f"{cache_b}</div>"
    )
    p_c = _sintesis_card("Impacto en Precios",  result.get("impacto_precios",""),  "#D97706","#FEF3C7","💰")
    m_c = _sintesis_card("Tendencias México",   result.get("tendencias_mexico",""),"#059669","#D1FAE5","🇲🇽")
    r_c = _sintesis_card("Riesgos Globales",    result.get("riesgos_globales",""), "#DC2626","#FEE2E2","⚠️")
    grid = (
        f"<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:12px;'>"
        f"<div>{p_c}</div><div>{m_c}</div><div>{r_c}</div></div>"
    )
    rec = result.get("recomendacion","")
    rec_html = (
        f"<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
        f"padding:12px 16px;margin-top:14px;font-size:13px;color:#1E40AF;'>"
        f"🏭 <b>Recomendación para TYASA:</b> {rec}</div>"
    ) if rec else ""
    return header + grid + rec_html


def _sintesis_card(titulo: str, texto: str, c_txt: str, c_bg: str, icon: str) -> str:
    return (
        f"<div style='background:{c_bg};border:1px solid {c_txt}33;border-radius:10px;"
        f"padding:16px;height:100%;min-height:120px;'>"
        f"<div style='font-size:11px;font-weight:800;letter-spacing:0.07em;color:{c_txt};"
        f"margin-bottom:10px;'>{icon} {titulo.upper()}</div>"
        f"<div style='font-size:13px;color:#374151;line-height:1.6;'>{texto}</div>"
        f"</div>"
    )


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — SÍNTESIS GLOBAL (nueva, 10 categorías con URLs)
# ════════════════════════════════════════════════════════════════════════════

def _render_sintesis_global(result: dict | None) -> str:
    """Render del resumen ejecutivo global con referencias clickeables."""
    if result is None:
        return (
            "<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            "padding:16px;color:#0369A1;font-size:13px;'>"
            "ℹ️ Haz clic en <b>▶ Generar síntesis ejecutiva</b> para obtener el resumen "
            "global de las 10 categorías con referencias a los artículos más relevantes.</div>"
        )
    err = result.get("_error")
    if err:
        return (
            f"<div style='background:#FEF2F2;border:1px solid #FCA5A5;border-radius:8px;"
            f"padding:16px;color:#DC2626;font-size:13px;'>⚠️ {err}</div>"
        )

    nivel    = result.get("nivel_alerta", "—")
    nc_txt, nc_bg = ALERTA_STYLE.get(nivel, ("#6B7280", "#F3F4F6"))
    cached_b = (
        '<span style="background:#F3F4F6;color:#6B7280;padding:3px 10px;'
        'border-radius:20px;font-size:11px;margin-left:6px;">💾 Caché</span>'
    ) if result.get("_cached") else ""
    fecha    = result.get("_fecha", "")

    hoy_str = str(datetime.date.today())
    stale_banner = (
        f"<div style='background:#FEF3C7;border:1px solid #F59E0B;border-radius:8px;"
        f"padding:10px 14px;font-size:12px;color:#92400E;margin-bottom:12px;'>"
        f"⚠️ <b>Datos desactualizados:</b> esta síntesis corresponde al <b>{fecha}</b>, "
        f"no al día de hoy. Haz clic en <b>▶ Generar síntesis ejecutiva</b> para actualizar.</div>"
    ) if fecha and fecha != hoy_str else ""

    header = (
        f"<div style='display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap;'>"
        f"<span style='background:{nc_bg};color:{nc_txt};padding:5px 14px;"
        f"border-radius:20px;font-size:12px;font-weight:700;'>⚡ Nivel de alerta: {nivel}</span>"
        f"<span style='background:#F3F4F6;color:#6B7280;padding:4px 12px;"
        f"border-radius:20px;font-size:11px;'>📅 {fecha}</span>"
        f"{cached_b}</div>"
    )

    estado  = result.get("estado_mercado", "") or ""
    impacto = result.get("impacto_mexico", "") or ""
    dos_col = (
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;'>"
        f"<div style='background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:16px;'>"
        f"<div style='font-size:11px;font-weight:800;color:#1B3A5C;letter-spacing:.06em;margin-bottom:8px;'>🌍 ESTADO DEL MERCADO</div>"
        f"<div style='font-size:13px;color:#374151;line-height:1.65;'>{estado}</div></div>"
        f"<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;padding:16px;'>"
        f"<div style='font-size:11px;font-weight:800;color:#1D4ED8;letter-spacing:.06em;margin-bottom:8px;'>🇲🇽 IMPACTO EN MÉXICO / TYASA</div>"
        f"<div style='font-size:13px;color:#1E40AF;line-height:1.65;'>{impacto}</div></div>"
        "</div>"
    )

    def _safe_url(u: str) -> str:
        return u.replace('"', "%22").replace("'", "%27").replace(" ", "%20")

    def _item(data: dict, color: str, bg: str) -> str:
        texto     = (data.get("texto") or "").strip()
        ref_url   = _safe_url((data.get("ref_url") or "").strip())
        ref_titulo = ((data.get("ref_titulo") or "")[:55]).strip()
        link = (
            f'<br><a href="{ref_url}" target="_blank" '
            f'style="color:{color};font-size:10px;font-weight:600;text-decoration:none;">'
            f'↗ {ref_titulo}</a>'
        ) if ref_url else ""
        return (
            f"<div style='background:{bg};border-left:3px solid {color};"
            f"border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:6px;'>"
            f"<div style='font-size:12.5px;color:#374151;line-height:1.5;'>{texto}{link}</div>"
            f"</div>"
        )

    riesgos   = result.get("riesgos", []) or []
    opors     = result.get("oportunidades", []) or []
    r_html    = "".join(_item(r, "#DC2626", "#FEF2F2") for r in riesgos)
    o_html    = "".join(_item(o, "#059669", "#F0FDF4") for o in opors)
    _vacio    = "<div style='color:#9CA3AF;font-size:12px;padding:8px 0;'>—</div>"

    two_col = (
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px;'>"
        "<div>"
        "<div style='font-size:11px;font-weight:800;color:#DC2626;letter-spacing:.06em;margin-bottom:8px;'>⚠️ RIESGOS IDENTIFICADOS</div>"
        f"{r_html or _vacio}"
        "</div>"
        "<div>"
        "<div style='font-size:11px;font-weight:800;color:#059669;letter-spacing:.06em;margin-bottom:8px;'>✅ OPORTUNIDADES</div>"
        f"{o_html or _vacio}"
        "</div>"
        "</div>"
    )

    # ── Noticias por línea de producto ───────────────────────────────────────
    _LINEA_STYLE: dict[str, tuple[str, str, str]] = {
        "Aceros Planos":          ("#1B3A5C", "#E8EFF6", "🔩"),
        "Aceros Especiales (SBQ)": ("#0F766E", "#CCFBF1", "⚙️"),
        "Aceros Largos":           ("#D97706", "#FEF3C7", "🏗️"),
        "General / Industria":     ("#6B7280", "#F3F4F6", "🌐"),
    }
    _LINEA_ORDER = ["Aceros Planos", "Aceros Especiales (SBQ)", "Aceros Largos", "General / Industria"]

    lineas_raw = result.get("noticias_por_linea") or []
    # Agrupar por línea manteniendo el orden definido
    lineas_dict: dict[str, list[dict]] = {k: [] for k in _LINEA_ORDER}
    for item in lineas_raw:
        if isinstance(item, dict):
            linea = (item.get("linea") or "").strip()
            if linea in lineas_dict:
                lineas_dict[linea].append(item)
            else:
                lineas_dict.setdefault("General / Industria", []).append(item)

    lineas_html = ""
    if any(lineas_dict.values()):
        col_cards = ["", ""]
        for i, linea in enumerate(_LINEA_ORDER):
            items = lineas_dict[linea]
            lt, lb, icon = _LINEA_STYLE.get(linea, ("#374151", "#F3F4F6", "📌"))
            items_html = ""
            for it in items:
                hallazgo  = (it.get("hallazgo") or "").strip()
                ref_url   = _safe_url((it.get("ref_url") or "").strip())
                ref_titulo = ((it.get("ref_titulo") or "")[:55]).strip()
                if not hallazgo or "sin novedades" in hallazgo.lower():
                    items_html += (
                        f"<div style='font-size:11.5px;color:#9CA3AF;"
                        f"padding:4px 0;font-style:italic;'>Sin novedades específicas hoy</div>"
                    )
                    continue
                link = (
                    f'<a href="{ref_url}" target="_blank" '
                    f'style="color:{lt};font-size:10px;font-weight:600;'
                    f'text-decoration:none;display:block;margin-top:2px;">'
                    f'↗ {ref_titulo or "Ver artículo"}</a>'
                ) if ref_url else ""
                items_html += (
                    f"<div style='border-left:2px solid {lt};padding:5px 8px;"
                    f"margin-bottom:5px;background:#fff;border-radius:0 5px 5px 0;'>"
                    f"<div style='font-size:12px;color:#374151;line-height:1.5;'>{hallazgo}</div>"
                    f"{link}"
                    f"</div>"
                )
            col_cards[i % 2] += (
                f"<div style='background:{lb};border:1px solid {lt}22;border-radius:10px;"
                f"padding:10px 12px;margin-bottom:8px;'>"
                f"<div style='font-size:11px;font-weight:800;color:{lt};"
                f"letter-spacing:.04em;margin-bottom:6px;'>{icon} {linea.upper()}</div>"
                f"{items_html or _vacio}"
                f"</div>"
            )
        lineas_html = (
            "<div style='margin-bottom:14px;'>"
            "<div style='font-size:11px;font-weight:800;color:#1B3A5C;letter-spacing:.06em;"
            "margin-bottom:8px;'>📦 NOTICIAS POR LÍNEA DE PRODUCTO</div>"
            "<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;'>"
            f"<div>{col_cards[0]}</div>"
            f"<div>{col_cards[1]}</div>"
            "</div></div>"
        )

    rec     = result.get("recomendacion", "") or ""
    rec_html = (
        f"<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
        f"padding:12px 16px;font-size:13px;color:#1E40AF;'>"
        f"🎯 <b>Recomendación para TYASA:</b> {rec}</div>"
    ) if rec else ""

    return stale_banner + header + dos_col + two_col + lineas_html + rec_html


def _render_alertas_mercado(alertas: list[dict], noticias_por_alerta: dict) -> str:
    """Sección de noticias de las variables en alerta — debajo de la síntesis."""
    if not alertas or not noticias_por_alerta:
        return "<!-- sin noticias de alertas -->"

    _SEV_STYLE = {
        "Crítico":  ("#C0392B", "#FCEBEB"),
        "Alto":     ("#D68910", "#FAEEDA"),
        "Moderado": ("#185FA5", "#E6F1FB"),
    }

    def _safe_u(u: str) -> str:
        return u.replace('"', "%22").replace("'", "%27").replace(" ", "%20")

    alerta_lookup = {a["variable"]: a for a in alertas}
    col_cards = ["", ""]
    idx = 0

    for var, nots in noticias_por_alerta.items():
        if not nots:
            continue
        a    = alerta_lookup.get(var, {})
        sev  = a.get("severidad", "Moderado")
        sigma = a.get("sigma_actual", 0.0)
        cam7  = a.get("cambio_7d_pct", 0.0)
        tend  = a.get("tendencia", "")
        ct, cb = _SEV_STYLE.get(sev, ("#6B7280", "#F3F4F6"))
        flecha = "↑" if tend == "sube" else "↓"

        items_html = ""
        for n in nots[:1]:
            tit  = (n.get("titulo") or "")[:75]
            url  = _safe_u((n.get("url") or "").strip())
            src  = (n.get("fuente") or "")
            fech = (n.get("fecha_pub") or "")[:10]
            lo   = f'<a href="{url}" target="_blank" style="font-size:12px;color:#1B3A5C;text-decoration:none;line-height:1.4;display:block;">' if url else '<span style="font-size:12px;color:#374151;">'
            lc   = "</a>" if url else "</span>"
            items_html += (
                f"<div style='border-left:2px solid {ct};padding:4px 8px;"
                f"margin-bottom:5px;background:#fff;border-radius:0 5px 5px 0;'>"
                f"{lo}{tit}{lc}"
                f"<span style='font-size:10px;color:#9CA3AF;display:block;'>"
                f"{src} · {fech}</span>"
                f"</div>"
            )

        col_cards[idx % 2] += (
            f"<div style='background:{cb};border:1px solid {ct}33;border-radius:8px;"
            f"padding:10px 12px;margin-bottom:8px;'>"
            f"<div style='font-size:11px;font-weight:700;color:{ct};"
            f"letter-spacing:.03em;margin-bottom:6px;'>"
            f"📡 {var.replace('_', ' ').upper()}&nbsp;"
            f"<span style='background:{ct};color:#fff;padding:1px 7px;"
            f"border-radius:10px;font-size:10px;font-weight:700;'>{sev}</span>"
            f"<span style='font-size:10px;font-weight:400;margin-left:6px;'>"
            f"{flecha} {cam7:+.1f}% · {sigma:+.2f}σ</span>"
            f"</div>"
            f"{items_html}"
            f"</div>"
        )
        idx += 1

    if not col_cards[0] and not col_cards[1]:
        return "<!-- sin noticias de alertas -->"

    return (
        "<div style='margin-top:14px;border-top:1px solid #E5E7EB;padding-top:14px;'>"
        "<div style='font-size:11px;font-weight:800;color:#D97706;letter-spacing:.06em;"
        "margin-bottom:4px;'>⚡ NOTICIAS DE LAS ALERTAS DE MERCADO</div>"
        "<div style='font-size:11px;color:#9CA3AF;margin-bottom:10px;'>"
        "Artículos recientes de las variables con comportamiento anómalo · "
        "Análisis detallado en <b>Monitor de Quiebres</b></div>"
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;'>"
        f"<div>{col_cards[0]}</div>"
        f"<div>{col_cards[1]}</div>"
        "</div></div>"
    )


def _email_lineas_rows(lineas_raw: list) -> str:
    """Sección de email: noticias agrupadas por línea de producto TYASA."""
    if not lineas_raw:
        return ""
    _LINEA_COLORS = {
        "Aceros Planos":           ("#1B3A5C", "🔩"),
        "Aceros Especiales (SBQ)": ("#0F766E", "⚙️"),
        "Aceros Largos":           ("#D97706", "🏗️"),
        "General / Industria":     ("#6B7280", "🌐"),
    }
    _ORDER = ["Aceros Planos", "Aceros Especiales (SBQ)", "Aceros Largos", "General / Industria"]
    grouped: dict[str, list] = {k: [] for k in _ORDER}
    for item in lineas_raw:
        if isinstance(item, dict):
            linea = (item.get("linea") or "").strip()
            grouped.setdefault(linea, []).append(item)

    rows = []
    for linea in _ORDER:
        items = grouped.get(linea, [])
        color, icon = _LINEA_COLORS.get(linea, ("#374151", "📌"))
        rows.append(
            f"<tr><td colspan='2' style='padding:6px 10px 2px;"
            f"font-size:10px;font-weight:700;color:{color};"
            f"text-transform:uppercase;letter-spacing:.06em;'>"
            f"{icon} {linea}</td></tr>"
        )
        if not items:
            rows.append(
                f"<tr><td style='padding:2px 10px 6px;border-left:3px solid {color};"
                f"background:#F8FAFC;font-size:11px;color:#9CA3AF;'>"
                f"Sin novedades específicas hoy</td></tr>"
            )
            continue
        for it in items:
            hallazgo  = (it.get("hallazgo") or "").strip()
            url       = (it.get("ref_url") or "").strip()
            titulo    = ((it.get("ref_titulo") or "Ver artículo")[:55]).strip()
            if "sin novedades" in hallazgo.lower():
                continue
            link = f'<br><a href="{url}" style="color:{color};font-size:10px;">↗ {titulo}</a>' if url else ""
            rows.append(
                f"<tr><td style='padding:3px 10px 6px;border-left:3px solid {color};"
                f"background:#F8FAFC;font-size:12px;color:#374151;'>"
                f"{hallazgo}{link}</td></tr>"
            )
    return (
        '<div style="padding:0 28px 16px;">'
        '<div style="font-size:11px;font-weight:700;color:#1B3A5C;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:8px;">📦 Noticias por Línea de Producto</div>'
        '<table style="width:100%;border-collapse:separate;border-spacing:0 3px;">'
        + "".join(rows)
        + "</table></div>"
    )


def _email_alertas_rows(alertas: list[dict], noticias_por_alerta: dict) -> str:
    """Sección de email: una noticia por cada variable en alerta."""
    if not alertas or not noticias_por_alerta:
        return ""
    _SEV_COLORS = {
        "Crítico":  "#C0392B",
        "Alto":     "#D68910",
        "Moderado": "#185FA5",
    }
    rows = []
    for a in alertas[:8]:
        var  = a.get("variable", "")
        sev  = a.get("severidad", "Moderado")
        sigma = a.get("sigma_actual", 0.0)
        cam7  = a.get("cambio_7d_pct", 0.0)
        tend  = a.get("tendencia", "")
        nots  = noticias_por_alerta.get(var, [])
        if not nots:
            continue
        color  = _SEV_COLORS.get(sev, "#6B7280")
        flecha = "↑" if tend == "sube" else "↓"
        n      = nots[0]
        tit    = (n.get("titulo") or "")[:75]
        url    = (n.get("url") or "").strip()
        src    = (n.get("fuente") or "")
        fech   = (n.get("fecha_pub") or "")[:10]
        link   = f'<br><a href="{url}" style="color:{color};font-size:10px;">↗ {src} · {fech}</a>' if url else f"<br><span style='font-size:10px;color:#9CA3AF;'>{src} · {fech}</span>"
        rows.append(
            f"<tr><td style='padding:5px 10px 5px 0;vertical-align:top;width:130px;"
            f"font-size:11px;font-weight:700;color:{color};white-space:nowrap;'>"
            f"📡 {var.replace('_',' ')}<br>"
            f"<span style='font-weight:400;'>{flecha} {cam7:+.1f}% · {sigma:+.2f}σ</span></td>"
            f"<td style='padding:5px 10px;border-left:3px solid {color};"
            f"background:#FAFAFA;font-size:12px;color:#374151;'>"
            f"{tit}{link}</td></tr>"
        )
    if not rows:
        return ""
    return (
        '<div style="padding:0 28px 16px;">'
        '<div style="font-size:11px;font-weight:700;color:#D97706;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:8px;">⚡ Noticias de las Alertas de Mercado</div>'
        '<table style="width:100%;border-collapse:separate;border-spacing:0 4px;">'
        + "".join(rows)
        + "</table></div>"
    )


def _build_indicadores_section(df_vars) -> str:
    """Wrapper para el correo — envuelve en padding de email."""
    html = build_indicadores_html(df_vars)
    if not html:
        return ""
    return f"<div style='padding:0 28px 16px;'>{html}</div>"


def _find_logo_path() -> tuple[str | None, str, str]:
    """Busca el logo TYASA en assets/img. Retorna (path, mime, subtype) o (None, "", "")."""
    for fname, mime, subtype in [
        ("tyasa_logo.webp", "image/webp", "webp"),
        ("tyasa_logo.png",  "image/png",  "png"),
        ("tyasa_logo.jpg",  "image/jpeg", "jpeg"),
    ]:
        path = os.path.join(_root, "assets", "img", fname)
        if os.path.exists(path):
            return path, mime, subtype
    return None, "", ""


def _build_email_html(result: dict, df_vars=None,
                       alertas: list | None = None,
                       alertas_nots: dict | None = None) -> str:
    """Genera el HTML del digest ejecutivo para envío por correo."""
    nivel      = result.get("nivel_alerta", "—")
    fecha      = result.get("_fecha", "")
    estado     = result.get("estado_mercado", "") or ""
    impacto    = result.get("impacto_mexico", "") or ""
    riesgos    = result.get("riesgos", []) or []
    opors      = result.get("oportunidades", []) or []
    rec        = result.get("recomendacion", "") or ""
    lineas_raw = result.get("noticias_por_linea") or []

    nc_colors = {
        "Alto":  ("#DC2626", "#FEE2E2"),
        "Medio": ("#D97706", "#FEF3C7"),
        "Bajo":  ("#059669", "#D1FAE5"),
    }
    nc_txt, nc_bg = nc_colors.get(nivel, ("#6B7280", "#F3F4F6"))

    def _rows(items: list[dict], color: str) -> str:
        if not items:
            return "<tr><td style='padding:8px 14px;color:#9CA3AF;'>—</td></tr>"
        out = ""
        for item in items:
            texto     = (item.get("texto") or "").strip()
            ref_url   = (item.get("ref_url") or "").strip()
            ref_titulo = ((item.get("ref_titulo") or "")[:60]).strip()
            link = (
                f'<br><a href="{ref_url}" style="color:{color};font-size:11px;">'
                f'↗ {ref_titulo}</a>'
            ) if ref_url else ""
            out += (
                f"<tr><td style='padding:8px 14px;border-left:3px solid {color};"
                f"background:#FAFAFA;font-size:13px;color:#374151;margin-bottom:4px;'>"
                f"{texto}{link}</td></tr>"
            )
        return out

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Segoe UI,Arial,sans-serif;background:#F3F4F6;margin:0;padding:20px;">
<div style="max-width:680px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;
     box-shadow:0 2px 8px rgba(0,0,0,.08);">
  <div style="background:#1B3A5C;padding:22px 28px;">
    <table role="presentation" style="border-collapse:collapse;">
      <tr>
        <td style="padding-right:14px;vertical-align:middle;">
          <img src="cid:tyasa_logo" alt="TYASA" style="height:40px;width:auto;display:block;object-fit:contain;">
        </td>
        <td style="vertical-align:middle;">
          <h1 style="color:#fff;margin:0;font-size:26px;font-weight:800;letter-spacing:.02em;">TYASA BI</h1>
          <div style="font-size:11px;color:rgba(255,255,255,.55);text-transform:uppercase;
               letter-spacing:.08em;margin-top:2px;">Monitor Siderúrgico · {fecha}</div>
        </td>
      </tr>
    </table>
  </div>
  <div style="padding:18px 28px 0;">
    <span style="background:{nc_bg};color:{nc_txt};padding:5px 14px;border-radius:20px;
          font-size:12px;font-weight:700;">⚡ Nivel de alerta: {nivel}</span>
  </div>
  <div style="padding:16px 28px;">
    <div style="font-size:11px;font-weight:700;color:#6B7280;text-transform:uppercase;
         letter-spacing:.06em;margin-bottom:6px;">🌍 Estado del Mercado</div>
    <p style="font-size:13px;color:#374151;line-height:1.65;margin:0;">{estado}</p>
  </div>
  <div style="padding:0 28px 16px;">
    <div style="background:#EFF6FF;border-radius:8px;padding:14px 16px;">
      <div style="font-size:11px;font-weight:700;color:#1D4ED8;text-transform:uppercase;
           letter-spacing:.06em;margin-bottom:6px;">🇲🇽 Impacto en México / TYASA</div>
      <p style="font-size:13px;color:#1E40AF;line-height:1.65;margin:0;">{impacto}</p>
    </div>
  </div>
  <div style="padding:0 28px 16px;">
    <div style="font-size:11px;font-weight:700;color:#DC2626;text-transform:uppercase;
         letter-spacing:.06em;margin-bottom:8px;">⚠️ Riesgos Identificados</div>
    <table style="width:100%;border-collapse:separate;border-spacing:0 4px;">{_rows(riesgos,"#DC2626")}</table>
  </div>
  <div style="padding:0 28px 16px;">
    <div style="font-size:11px;font-weight:700;color:#059669;text-transform:uppercase;
         letter-spacing:.06em;margin-bottom:8px;">✅ Oportunidades</div>
    <table style="width:100%;border-collapse:separate;border-spacing:0 4px;">{_rows(opors,"#059669")}</table>
  </div>
  {_email_lineas_rows(lineas_raw)}
  <div style="padding:0 28px 22px;">
    <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;padding:14px 16px;">
      <div style="font-size:11px;font-weight:700;color:#1D4ED8;text-transform:uppercase;
           letter-spacing:.06em;margin-bottom:6px;">🎯 Recomendación para TYASA</div>
      <p style="font-size:13px;color:#1E40AF;line-height:1.65;margin:0;">{rec}</p>
    </div>
  </div>
  {_email_alertas_rows(alertas or [], alertas_nots or {})}
  {_build_indicadores_section(df_vars)}
  <div style="background:#F9FAFB;padding:14px 28px;border-top:1px solid #E5E7EB;">
    <div style="font-size:11px;color:#9CA3AF;">Generado automáticamente por TYASA BI · No responder este mensaje</div>
  </div>
</div>
</body></html>"""


def _enviar_email_digest(html_body: str, subject: str) -> tuple[bool, str]:
    """
    Envía el digest por Gmail SMTP (SSL, puerto 465).
    Requiere en .streamlit/secrets.toml:
      GMAIL_USER         = "tu@gmail.com"
      GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"   # App Password de Google
      DIGEST_EMAIL_TO    = ["dest1@gmail.com", "dest2@hotmail.com"]  # lista o string
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    try:
        gmail_user = st.secrets.get("GMAIL_USER", "")
        gmail_pass = st.secrets.get("GMAIL_APP_PASSWORD", "")
        if not gmail_user or not gmail_pass:
            return (
                False,
                "Agrega GMAIL_USER y GMAIL_APP_PASSWORD en .streamlit/secrets.toml "
                "(usa una App Password de Google, no tu contraseña normal).",
            )
        # Soporte para lista de destinatarios o string simple/coma-separado
        to_raw = st.secrets.get("DIGEST_EMAIL_TO", gmail_user)
        if isinstance(to_raw, (list, tuple)):
            to_list = [e.strip() for e in to_raw if e.strip()]
        elif isinstance(to_raw, str) and "," in to_raw:
            to_list = [e.strip() for e in to_raw.split(",") if e.strip()]
        else:
            to_list = [str(to_raw).strip() or gmail_user]

        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"]    = gmail_user
        msg["To"]      = ", ".join(to_list)

        msg_alt = MIMEMultipart("alternative")
        msg_alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(msg_alt)

        logo_path, _logo_mime, logo_subtype = _find_logo_path()
        if logo_path:
            with open(logo_path, "rb") as f:
                logo_img = MIMEImage(f.read(), _subtype=logo_subtype)
            logo_img.add_header("Content-ID", "<tyasa_logo>")
            logo_img.add_header("Content-Disposition", "inline", filename=os.path.basename(logo_path))
            msg.attach(logo_img)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as srv:
            srv.login(gmail_user, gmail_pass)
            srv.sendmail(gmail_user, to_list, msg.as_string())
        dest_str = ", ".join(to_list)
        return True, f"Digest enviado a {dest_str}"
    except Exception as exc:
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — MAÑANERA
# ════════════════════════════════════════════════════════════════════════════

_TIPO_STYLE: dict[str, tuple[str, str]] = {
    "Regulación":   ("#7C3AED", "#EDE9FE"),
    "Energía":      ("#D97706", "#FEF3C7"),
    "Demanda":      ("#2563EB", "#DBEAFE"),
    "Riesgo":       ("#DC2626", "#FEE2E2"),
    "Oportunidad":  ("#059669", "#D1FAE5"),
    "Macroeconomía":("#0F766E", "#CCFBF1"),
}
_IMP_STYLE: dict[str, tuple[str, str]] = {
    "Alto":  ("#DC2626", "#FEE2E2"),
    "Medio": ("#D97706", "#FEF3C7"),
    "Bajo":  ("#059669", "#D1FAE5"),
}
_DIR_ICON  = {"Positivo": "↑", "Negativo": "↓", "Neutral": "→"}
_DIR_COLOR = {"Positivo": "#059669", "Negativo": "#DC2626", "Neutral": "#6B7280"}
_PROD_STYLE: dict[str, tuple[str, str]] = {
    "Tubería OCTG":       ("#92400E", "#FEF3C7"),
    "Tubería Mecánica":   ("#1B3A5C", "#E8EFF6"),
    "Perfiles":           ("#0F766E", "#CCFBF1"),
    "SBQ":                ("#4338CA", "#E0E7FF"),
    "Lámina Negra":       ("#374151", "#F3F4F6"),
    "Galvanizado":        ("#065F46", "#D1FAE5"),
}
_AREA_STYLE: dict[str, tuple[str, str]] = {
    "SBQ":            ("#1B3A5C", "#E8EFF6"),
    "Aceros Planos":  ("#0F766E", "#CCFBF1"),
    "Aceros Largos":  ("#4338CA", "#E0E7FF"),
    "Energía/Costos": ("#D97706", "#FEF3C7"),
    "Comercial":      ("#059669", "#D1FAE5"),
}


def _render_mananera_full(result: dict | None, loading: bool = False) -> str:
    if loading:
        return (
            "<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            "padding:24px;color:#0369A1;font-size:13px;text-align:center;'>"
            "<div style='font-size:28px;margin-bottom:10px;'>⏳</div>"
            "<b>Analizando la conferencia mañanera…</b><br>"
            "<span style='font-size:12px;color:#0284C7;'>"
            "Buscando el video en YouTube → obteniendo transcripción → "
            "procesando con IA. Puede tardar entre 20 y 60 segundos.</span></div>"
        )
    if result is None:
        return (
            "<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            "padding:16px;color:#0369A1;font-size:13px;'>"
            "ℹ️ Haz clic en <b>▶ Analizar</b> para que la IA procese la conferencia "
            "presidencial y extraiga solo la información relevante para TYASA."
            "</div>"
        )
    err = result.get("_error", "")
    is_live = result.get("_is_live", False)
    if err:
        vid_id = result.get("_video_id", "")
        yt = (
            f" &nbsp;<a href='https://www.youtube.com/watch?v={vid_id}' target='_blank'"
            f" style='color:#4A7BA7;font-size:11px;'>▶ Ver video</a>"
        ) if vid_id else ""
        live_badge = (
            "<span style='background:#FEF3C7;color:#92400E;padding:2px 8px;"
            "border-radius:10px;font-size:10px;font-weight:700;'>🔴 EN VIVO</span> "
        ) if is_live else ""
        return (
            f"<div style='background:#FEF2F2;border:1px solid #FCA5A5;border-radius:8px;"
            f"padding:16px;color:#DC2626;font-size:13px;'>"
            f"{live_badge}⚠️ {err}{yt}</div>"
        )
    if not result.get("tiene_contenido_relevante"):
        fecha  = result.get("fecha", "")
        vid_id = result.get("_video_id", "")
        yt = (
            f" &nbsp;<a href='https://www.youtube.com/watch?v={vid_id}' target='_blank'"
            f" style='color:#4A7BA7;font-size:11px;'>▶ Ver video</a>"
        ) if vid_id else ""
        return (
            f"<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            f"padding:16px;color:#0369A1;font-size:13px;'>"
            f"ℹ️ La conferencia del <b>{fecha}</b> no contiene información relevante "
            f"para TYASA según el análisis de IA.{yt}</div>"
        )
    resumen  = result.get("resumen_ejecutivo", [])
    impactos = result.get("analisis_impacto", [])
    alertas  = result.get("alertas_criticas", [])
    insight  = result.get("insight_estrategico", "")
    rec      = result.get("recomendacion", "")
    cached   = result.get("_cached", False)
    vid_id   = result.get("_video_id", "")
    parts = []
    if resumen:
        parts.append(_man_resumen_html(resumen, cached, vid_id))
    if impactos:
        parts.append(_man_impacto_html(impactos))
    if alertas:
        parts.append(_man_alertas_html(alertas))
    ir = _man_insight_rec_html(insight, rec)
    if ir:
        parts.append(ir)
    return "".join(parts) or "<div></div>"


def _man_resumen_html(puntos: list[str], cached: bool, video_id: str) -> str:
    cached_badge = (
        "<span style='background:#F3F4F6;color:#6B7280;padding:2px 8px;"
        "border-radius:10px;font-size:10px;'>💾 Caché</span>"
    ) if cached else (
        "<span style='background:#D1FAE5;color:#065F46;padding:2px 8px;"
        "border-radius:10px;font-size:10px;'>✓ Nuevo</span>"
    )
    yt_link = (
        f"<a href='https://www.youtube.com/watch?v={video_id}' target='_blank' "
        f"style='font-size:10px;color:#4A7BA7;text-decoration:none;'>▶ Ver video</a>"
    ) if video_id else ""
    items = "".join(f"<li style='margin-bottom:5px;'>{p}</li>" for p in puntos)
    return (
        f"<div style='background:#F0F4F8;border-left:4px solid #1B3A5C;"
        f"border-radius:0 10px 10px 0;padding:16px 20px;margin-bottom:16px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>"
        f"<span style='font-size:12px;font-weight:800;letter-spacing:0.06em;color:#1B3A5C;'>"
        f"📋 RESUMEN EJECUTIVO</span>"
        f"<span style='display:flex;gap:8px;align-items:center;'>{cached_badge} {yt_link}</span>"
        f"</div>"
        f"<ol style='margin:0;padding-left:18px;font-size:13px;color:#374151;line-height:1.75;'>"
        f"{items}</ol></div>"
    )


def _man_impacto_html(items: list[dict]) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        tipo     = item.get("tipo", "")
        imp      = item.get("impacto", "")
        dire     = item.get("direccion", "")
        areas    = item.get("areas_afectadas", [])
        productos= item.get("productos_afectados", [])
        punto    = item.get("punto", "")
        expl     = item.get("explicacion", "")

        tc, tb = _TIPO_STYLE.get(tipo, ("#6B7280", "#F3F4F6"))
        ic, ib = _IMP_STYLE.get(imp,  ("#6B7280", "#F3F4F6"))
        dc     = _DIR_COLOR.get(dire, "#6B7280")
        di     = _DIR_ICON.get(dire, "→")

        prod_tags = "".join(
            f"<span style='background:{_PROD_STYLE.get(p, ('#1B3A5C','#E8EFF6'))[1]};"
            f"color:{_PROD_STYLE.get(p, ('#1B3A5C','#E8EFF6'))[0]};"
            f"padding:1px 7px;border-radius:10px;font-size:10px;font-weight:600;'>"
            f"📦 {p}</span>"
            for p in productos
        )
        area_tags = "".join(
            f"<span style='background:{_AREA_STYLE.get(a, ('#6B7280','#F3F4F6'))[1]};"
            f"color:{_AREA_STYLE.get(a, ('#6B7280','#F3F4F6'))[0]};"
            f"padding:1px 7px;border-radius:10px;font-size:10px;font-weight:600;'>{a}</span>"
            for a in areas
        )
        cards.append(
            f"<div style='border:1px solid #E5E7EB;border-radius:10px;padding:14px;"
            f"background:white;box-shadow:0 1px 3px rgba(0,0,0,0.06);'>"
            f"<div style='font-size:12px;font-weight:700;color:#111827;margin-bottom:10px;"
            f"line-height:1.4;'>{punto}</div>"
            f"<div style='display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px;'>"
            f"<span style='background:{tb};color:{tc};padding:2px 8px;border-radius:10px;"
            f"font-size:10px;font-weight:700;'>{tipo}</span>"
            f"<span style='background:{ib};color:{ic};padding:2px 8px;border-radius:10px;"
            f"font-size:10px;font-weight:700;'>⚡ {imp}</span>"
            f"<span style='background:#F9FAFB;color:{dc};padding:2px 8px;border-radius:10px;"
            f"font-size:10px;font-weight:700;border:1px solid #E5E7EB;'>{di} {dire}</span>"
            f"</div>"
            + (f"<div style='display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px;'>{prod_tags}</div>" if prod_tags else "")
            + (f"<div style='display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;'>{area_tags}</div>" if area_tags else "")
            + f"<div style='font-size:12px;color:#6B7280;line-height:1.55;'>{expl}</div>"
            f"</div>"
        )
    grid = "".join(f"<div>{c}</div>" for c in cards)
    return (
        f"<div style='margin-bottom:6px;'>"
        f"<span style='font-size:12px;font-weight:800;letter-spacing:0.06em;"
        f"color:#1B3A5C;'>🔍 ANÁLISIS DE IMPACTO PARA TYASA</span></div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));"
        f"gap:12px;margin-bottom:16px;'>{grid}</div>"
    )


def _man_alertas_html(alertas: list[str]) -> str:
    if not alertas:
        return ""
    items = "".join(f"<li style='margin-bottom:4px;'>{a}</li>" for a in alertas)
    return (
        f"<div style='background:#FEF2F2;border:1px solid #FCA5A5;border-radius:8px;"
        f"padding:14px 18px;margin-bottom:16px;'>"
        f"<div style='font-size:12px;font-weight:800;color:#DC2626;margin-bottom:8px;'>"
        f"⚠️ ALERTAS CRÍTICAS</div>"
        f"<ul style='margin:0;padding-left:18px;font-size:12px;color:#991B1B;"
        f"line-height:1.65;'>{items}</ul></div>"
    )


def _man_insight_rec_html(insight: str, rec: str) -> str:
    if not insight and not rec:
        return ""
    col_ins = (
        f"<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;padding:14px 16px;'>"
        f"<div style='font-size:12px;font-weight:800;color:#1D4ED8;margin-bottom:8px;'>"
        f"💡 INSIGHT ESTRATÉGICO</div>"
        f"<div style='font-size:13px;color:#1E40AF;line-height:1.65;'>{insight}</div></div>"
    ) if insight else ""
    col_rec = (
        f"<div style='background:#F0FDF4;border:1px solid #86EFAC;border-radius:8px;padding:14px 16px;'>"
        f"<div style='font-size:12px;font-weight:800;color:#15803D;margin-bottom:8px;'>"
        f"🎯 RECOMENDACIÓN PARA TYASA</div>"
        f"<div style='font-size:13px;color:#166534;line-height:1.65;'>{rec}</div></div>"
    ) if rec else ""
    cols = "".join(f"<div>{c}</div>" for c in [col_ins, col_rec] if c)
    n = sum(1 for c in [col_ins, col_rec] if c)
    return (
        f"<div style='display:grid;grid-template-columns:repeat({n},1fr);"
        f"gap:12px;margin-top:4px;'>{cols}</div>"
    )


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — CHAT
# ════════════════════════════════════════════════════════════════════════════

def _render_chat_html(msgs: list[dict], has_key: bool) -> str:
    if not has_key:
        return (
            "<div style='background:#FEF3C7;border:1px solid #FCD34D;border-radius:8px;"
            "padding:16px;color:#92400E;font-size:13px;'>"
            "⚙️ Configura <b>GEMINI_API_KEY</b> en <code>.streamlit/secrets.toml</code> "
            "para usar el chat con el analista.</div>"
        )
    if not msgs:
        return (
            "<div style='background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;"
            "padding:36px 24px;text-align:center;color:#9CA3AF;font-size:13px;'>"
            "💬 Escribe una pregunta sobre la industria siderúrgica para comenzar."
            "</div>"
        )
    bubbles = []
    for m in msgs:
        content = (m.get("content") or "").replace("<", "&lt;").replace(">", "&gt;")
        if m.get("role") == "user":
            bubbles.append(
                f"<div style='display:flex;justify-content:flex-end;margin-bottom:10px;'>"
                f"<div style='background:#1B3A5C;color:white;border-radius:18px 18px 4px 18px;"
                f"padding:10px 16px;max-width:76%;font-size:13px;line-height:1.55;'>"
                f"{content}</div></div>"
            )
        else:
            bubbles.append(
                f"<div style='display:flex;justify-content:flex-start;margin-bottom:10px;'>"
                f"<div style='background:#F0F4F8;color:#374151;border-radius:18px 18px 18px 4px;"
                f"padding:10px 16px;max-width:76%;font-size:13px;line-height:1.55;'>"
                f"🤖 {content}</div></div>"
            )
    return (
        "<div style='background:white;border:1px solid #E5E7EB;border-radius:8px;"
        "padding:16px 20px;max-height:340px;overflow-y:auto;'>"
        + "".join(bubbles)
        + "</div>"
    )


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
sidebar_header("Industria Siderúrgica", "🏭")

# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════
st.html(
    f"<h2 style='color:{COLORS['primary']};margin-bottom:0;'>🏭 Monitor de la Industria Siderúrgica</h2>"
)
st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN 0 — ANALISTA DE LA MAÑANERA PRESIDENCIAL
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo("🇲🇽 Analista de la Mañanera Presidencial")

hoy_man = datetime.date.today()
with st.form("form_mananera", border=False):
    col_fman, col_bman, col_frzman = st.columns([3, 1, 1])
    with col_fman:
        fecha_man = st.date_input(
            "Fecha de la conferencia",
            value=hoy_man,
            min_value=hoy_man - datetime.timedelta(days=MANANERA_CACHE_DAYS),
            max_value=hoy_man,
            format="DD/MM/YYYY",
        )
    with col_bman:
        st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
        run_man = st.form_submit_button("▶ Analizar", use_container_width=True)
    with col_frzman:
        st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
        frz_man = st.checkbox("Regenerar", value=False)

fecha_man_str = str(fecha_man)
skey_man = f"mananera_{fecha_man_str}"

if skey_man not in st.session_state:
    cache_path_man = MANANERA_CACHE_DIR / f"{fecha_man_str}.json"
    if cache_path_man.exists():
        try:
            with open(cache_path_man, encoding="utf-8") as _f:
                _d = json.load(_f)
                _d["_cached"] = True
                st.session_state[skey_man] = _d
        except Exception:
            pass

if run_man and _GEMINI_KEY:
    st.session_state[skey_man] = analizar_mananera(_GEMINI_KEY, fecha_man_str, force_refresh=frz_man)
elif run_man:
    st.session_state[skey_man] = {
        "tiene_contenido_relevante": False,
        "_error": "Configura GEMINI_API_KEY en .streamlit/secrets.toml",
    }

st.html(_render_mananera_full(st.session_state.get(skey_man)))

# ── Exportar mañanera al contexto acumulativo del sistema ─────────────────────
_man_data = st.session_state.get(skey_man) or {}
if _man_data.get("tiene_contenido_relevante"):
    try:
        from core.chat_widget import actualizar_contexto_sistema
        actualizar_contexto_sistema("mananera", {
            "mananera_fecha":        fecha_man_str,
            "mananera_resumen":      _man_data.get("resumen_ejecutivo", []),
            "mananera_impactos":     [i.get("punto", "") for i in _man_data.get("analisis_impacto", [])],
            "mananera_insight":      _man_data.get("insight_estrategico", ""),
            "mananera_recomendacion":_man_data.get("recomendacion", ""),
        })
    except Exception:
        pass

st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN A — SÍNTESIS EJECUTIVA GLOBAL (10 categorías + URLs + correo)
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo("🤖 Síntesis Ejecutiva Global")

_ALERTAS_CAT_KEY = "Alertas de Mercado"

# Auto-cargar desde caché si la sesión acaba de iniciar (botón correo siempre habilitado)
if "sint_result" not in st.session_state:
    _all_cat_keys = list(GRUPOS_NACIONAL.keys()) + list(GRUPOS_INTERNACIONAL.keys()) + [_ALERTAS_CAT_KEY]
    # 1) Buscar caché de hoy (mismas categorías)
    _cached_hoy = cargar_cache_hoy("sintesis_global", cat_keys=_all_cat_keys)
    # Solo cargamos caché del día actual — no mostrar datos de días anteriores
    if _cached_hoy and not _cached_hoy.get("_error"):
        st.session_state["sint_result"] = _cached_hoy

# Alertas activas: computar una vez por sesión (necesario para la sección de alertas)
if "sint_alertas" not in st.session_state:
    try:
        _df_a = load_variables_mercado(dias=400)
        st.session_state["sint_alertas"] = (
            detectar_quiebres_automatico(_df_a, umbral_sigma=2.0)
            if not _df_a.empty else []
        )
    except Exception:
        st.session_state["sint_alertas"] = []

# Noticias de las alertas: computar una vez por sesión (caché 15 min por variable)
if "sint_alertas_nots" not in st.session_state:
    _sn: dict[str, list] = {}
    for _a in st.session_state["sint_alertas"][:8]:
        _v = _a.get("variable", "")
        if _v:
            _nts = _noticias_alerta_cached(_v, max_r=3)
            if _nts:
                _sn[_v] = _nts
    st.session_state["sint_alertas_nots"] = _sn

col_btn_s, col_frz_s, col_email_b = st.columns([2, 1, 1])
with col_btn_s:
    run_sint = st.button("▶ Generar síntesis ejecutiva", key="sint_run",
                         use_container_width=True)
with col_frz_s:
    frz_sint = st.checkbox("Regenerar", key="sint_frz", value=False)
with col_email_b:
    enviar_email_clicked = st.button(
        "📧 Enviar por correo", key="sint_email",
        use_container_width=True,
        disabled=(st.session_state.get("sint_result") is None
                  or bool((st.session_state.get("sint_result") or {}).get("_error"))),
    )

# Generar síntesis solo con noticias de hoy (12 artículos por grupo para mejor cobertura)
if run_sint and _GEMINI_KEY:
    _hoy_str = str(datetime.date.today())
    all_nots = {}
    _arts_para_resolver: list[dict] = []
    for g in list(GRUPOS_NACIONAL.keys()) + list(GRUPOS_INTERNACIONAL.keys()):
        nots_raw = _noticias_grupo(g, 12)
        # Para la síntesis: solo artículos CON fecha de hoy (excluir sin fecha y días anteriores)
        nots_hoy = [
            n for n in nots_raw
            if (n.get("fecha_pub") or "")[:10] == _hoy_str
        ]
        # Si no hay noticias de hoy, buscar en los últimos 3 días (no semanas anteriores)
        if not nots_hoy:
            _hace_3d = (datetime.date.today() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
            nots_hoy = sorted(
                [n for n in nots_raw if (n.get("fecha_pub") or "")[:10] >= _hace_3d],
                key=lambda x: x.get("fecha_pub", ""),
                reverse=True,
            )[:3]
        all_nots[g] = nots_hoy
        _arts_para_resolver.extend(nots_hoy)

    # Incorporar la primera noticia (no repetida) de cada alerta activa del
    # Monitor de Quiebres, para que la síntesis global refleje también esas alertas.
    _urls_ya_usadas = {
        (n.get("url") or "").strip()
        for _nots in all_nots.values() for n in _nots if n.get("url")
    }
    _titulos_ya_usados = {
        (n.get("titulo") or "").strip().lower()
        for _nots in all_nots.values() for n in _nots if n.get("titulo")
    }
    _noticias_alertas: list[dict] = []
    try:
        _df_vars_alertas = load_variables_mercado(dias=400)
        _alertas_activas = (
            detectar_quiebres_automatico(_df_vars_alertas, umbral_sigma=2.0)
            if not _df_vars_alertas.empty else []
        )
    except Exception:
        _alertas_activas = []
    for _alerta in _alertas_activas[:10]:
        _var_alerta = _alerta.get("variable", "")
        if not _var_alerta:
            continue
        for _n in _noticias_alerta_cached(_var_alerta):
            _url_n    = (_n.get("url") or "").strip()
            _titulo_n = (_n.get("titulo") or "").strip().lower()
            if not _titulo_n or _titulo_n in _titulos_ya_usados:
                continue
            if _url_n and _url_n in _urls_ya_usadas:
                continue
            _noticias_alertas.append(_n)
            _titulos_ya_usados.add(_titulo_n)
            if _url_n:
                _urls_ya_usadas.add(_url_n)
            break  # solo la primera noticia nueva de esta alerta
    all_nots[_ALERTAS_CAT_KEY] = _noticias_alertas
    _arts_para_resolver.extend(_noticias_alertas)

    # Resolver URLs de Google News (redirect → URL real) solo para artículos de la síntesis
    _resolve_gnews_batch(_arts_para_resolver)
    st.session_state["sint_result"]  = sintesis_global(all_nots, _GEMINI_KEY, force_refresh=frz_sint)
    st.session_state["sint_alertas"] = _alertas_activas
    # Actualizar noticias de alertas con datos frescos (ya se resolvieron URLs arriba)
    _sn_new: dict[str, list] = {}
    for _a in _alertas_activas[:8]:
        _v = _a.get("variable", "")
        if _v:
            _nts = _noticias_alerta_cached(_v, max_r=3)
            if _nts:
                _sn_new[_v] = _nts
    st.session_state["sint_alertas_nots"] = _sn_new
elif run_sint:
    st.session_state["sint_result"] = {
        "_error": "Configura GEMINI_API_KEY en .streamlit/secrets.toml",
    }

# Enviar por correo
_EMAIL_ST_KEY = "sint_email_status"
if enviar_email_clicked:
    _res = st.session_state.get("sint_result") or {}
    if not _res.get("_error"):
        try:
            _df_vars_email = load_variables_mercado(dias=30)
        except Exception:
            _df_vars_email = None
        _html_mail = _build_email_html(
            _res,
            df_vars=_df_vars_email,
            alertas=st.session_state.get("sint_alertas") or [],
            alertas_nots=st.session_state.get("sint_alertas_nots") or {},
        )
        _ok, _msg  = _enviar_email_digest(
            _html_mail,
            f"Digest Siderúrgico TYASA · {_res.get('_fecha', '')} · Alerta {_res.get('nivel_alerta','—')}",
        )
        st.session_state[_EMAIL_ST_KEY] = {"ok": _ok, "msg": _msg}

# DOM-STABLE: slot de estado de correo (siempre presente)
_email_st = st.session_state.get(_EMAIL_ST_KEY)
if _email_st:
    _em_color  = "#D1FAE5" if _email_st["ok"] else "#FEE2E2"
    _em_border = "#86EFAC" if _email_st["ok"] else "#FCA5A5"
    _em_text   = "#065F46" if _email_st["ok"] else "#DC2626"
    _em_icon   = "✅" if _email_st["ok"] else "⚠️"
    _email_html = (
        f"<div style='background:{_em_color};border:1px solid {_em_border};"
        f"border-radius:8px;padding:10px 14px;font-size:13px;color:{_em_text};margin-top:6px;'>"
        f"{_em_icon} {_email_st['msg']}</div>"
    )
else:
    _email_html = "<!-- -->"
st.html(_email_html)

# Render del resultado
st.html(_render_sintesis_global(st.session_state.get("sint_result")))

# Sección de noticias de alertas de mercado (debajo de la síntesis)
_sint_ok = (st.session_state.get("sint_result") or {})
if _sint_ok and not _sint_ok.get("_error") and _sint_ok.get("nivel_alerta"):
    _alertas_render    = st.session_state.get("sint_alertas") or []
    _alertas_nots_render = st.session_state.get("sint_alertas_nots") or {}
    if _alertas_render and _alertas_nots_render:
        st.html(_render_alertas_mercado(_alertas_render, _alertas_nots_render))

# ── Exportar síntesis al contexto del chat ───────────────────────────────────
_sint_data = st.session_state.get("sint_result") or {}
if _sint_data and not _sint_data.get("_error") and _sint_data.get("nivel_alerta"):
    try:
        from core.chat_widget import actualizar_contexto_sistema
        actualizar_contexto_sistema("sintesis_industria", {
            "sintesis_nivel_alerta":     _sint_data.get("nivel_alerta", ""),
            "sintesis_estado_mercado":   _sint_data.get("estado_mercado", ""),
            "sintesis_impacto_mexico":   _sint_data.get("impacto_mexico", ""),
            "sintesis_recomendacion":    _sint_data.get("recomendacion", ""),
        })
    except Exception:
        pass

st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN B — NOTICIAS (Nacionales + Internacionales)
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo("📰 Noticias de la Industria")

hoy      = datetime.date.today()
hace_7d  = hoy - datetime.timedelta(days=7)
hace_30d = hoy - datetime.timedelta(days=30)

# ── Fila 1: rango de fechas + Hoy + Actualizar ───────────────────────────────
col_rng, col_hoy, col_act = st.columns([3, 1, 1])
with col_rng:
    rango = st.date_input(
        "Rango de fechas",
        value=(hace_7d, hoy),
        min_value=hace_30d,
        max_value=hoy,
        key="ind_fecha_rango",
        format="DD/MM/YYYY",
    )
with col_hoy:
    st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
    hoy_clicked = st.button("📅 Hoy", key="ind_hoy", use_container_width=True,
                            help="Ver solo noticias de hoy")
with col_act:
    st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Actualizar", key="ind_refresh", use_container_width=True):
        st.cache_data.clear()

# Fechas efectivas — "Hoy" sobreescribe el date_input
if hoy_clicked:
    fecha_desde = fecha_hasta = str(hoy)
elif isinstance(rango, (list, tuple)) and len(rango) == 2:
    fecha_desde, fecha_hasta = str(rango[0]), str(rango[1])
else:
    fecha_desde = str(hace_7d)
    fecha_hasta = str(hoy)

st.caption(
    f"Mostrando noticias del **{fecha_desde}** al **{fecha_hasta}**"
    + (" · 📅 *Solo hoy*" if hoy_clicked else "")
)

# ── Fila 2: buscador libre ────────────────────────────────────────────────────
col_busq, col_busq_btn = st.columns([4, 1])
with col_busq:
    query_libre = st.text_input(
        "busqueda",
        placeholder="🔍  Buscar noticias por tema, empresa o fuente…  ej: HRC México, T-MEC acero, Fastmarkets",
        key="ind_query_libre",
        label_visibility="collapsed",
    )
with col_busq_btn:
    buscar_clicked = st.button("🔍 Buscar", key="ind_buscar_btn", use_container_width=True)

# ── Lógica de búsqueda libre ─────────────────────────────────────────────────
_BUSQ_RES_KEY   = "busq_libre_resultado"
_BUSQ_QUERY_KEY = "busq_libre_query"

if buscar_clicked and query_libre.strip():
    with st.spinner(f'Buscando "{query_libre.strip()}"…'):
        st.session_state[_BUSQ_RES_KEY]   = buscar_query_libre(query_libre.strip(), max_resultados=30)
        st.session_state[_BUSQ_QUERY_KEY] = query_libre.strip()

_busq_res   = st.session_state.get(_BUSQ_RES_KEY)
_busq_query = st.session_state.get(_BUSQ_QUERY_KEY, "")

# DOM-STABLE: botón siempre presente (disabled cuando no hay resultados)
_, col_clear = st.columns([5, 1])
with col_clear:
    if st.button(
        "✕ Limpiar búsqueda",
        key="ind_busq_clear",
        use_container_width=True,
        disabled=(_busq_res is None),
    ):
        st.session_state.pop(_BUSQ_RES_KEY, None)
        st.session_state.pop(_BUSQ_QUERY_KEY, None)
        _busq_res   = None
        _busq_query = ""

# DOM-STABLE: st.html() siempre presente — comentario vacío cuando no hay resultados
st.html(_render_busqueda_libre(_busq_res, _busq_query) if _busq_res else "<!-- -->")

# ── Nacionales ────────────────────────────────────────────────────────────────
st.html(
    "<div style='border-bottom:2px solid #1B3A5C;margin:20px 0 16px 0;padding-bottom:10px;"
    "display:flex;align-items:center;gap:10px;'>"
    "<div style='width:4px;height:26px;background:#DC2626;border-radius:2px;flex-shrink:0;'></div>"
    "<span style='font-size:18px;font-weight:900;color:#1B3A5C;letter-spacing:-0.02em;'>🇲🇽 Nacionales</span>"
    "<span style='margin-left:auto;font-size:10px;color:#9CA3AF;font-style:italic;'>"
    "Reforma · El Financiero · El Universal · Milenio · El Economista · ReporteAcero · +</span>"
    "</div>"
)

nac_grupos = list(GRUPOS_NACIONAL.keys())
nac_icons  = {
    "T-MEC y Tratados":    "🤝",
    "Nearshoring":         "🏭",
    "Sustentabilidad":     "♻️",
    "Socios Siderúrgicos": "⚙️",
    "Macroeconomía":       "📊",
    "Logística Nacional":  "🚛",
}
tabs_nac = st.tabs([f"{nac_icons.get(g,'')} {g}" for g in nac_grupos])

for tab, grupo in zip(tabs_nac, nac_grupos):
    with tab:
        noticias_raw = _noticias_grupo(grupo, 15)
        noticias_g   = _filtrar_por_fecha(noticias_raw, fecha_desde, fecha_hasta)
        st.html(_render_noticias_grid(noticias_g, grupo, GRUPO_STYLE_NACIONAL))

# ── Internacionales ───────────────────────────────────────────────────────────
st.html(
    "<div style='border-bottom:2px solid #1B3A5C;margin:24px 0 16px 0;padding-bottom:10px;"
    "display:flex;align-items:center;gap:10px;'>"
    "<div style='width:4px;height:26px;background:#4338CA;border-radius:2px;flex-shrink:0;'></div>"
    "<span style='font-size:18px;font-weight:900;color:#1B3A5C;letter-spacing:-0.02em;'>🌐 Internacionales</span>"
    "<span style='margin-left:auto;font-size:10px;color:#9CA3AF;font-style:italic;'>"
    "Fastmarkets · Reuters · Bloomberg · WorldSteel · S&amp;P Global · CRU · +</span>"
    "</div>"
)

int_grupos = list(GRUPOS_INTERNACIONAL.keys())
int_icons  = {
    "Precios y Commodities":   "💰",
    "Geopolítica y Logística": "🌍",
    "Defensa Comercial":       "🛡️",
    "Descarbonización":        "🌿",
    "Sectores Consumidores":   "🏗️",
}
tabs_int = st.tabs([f"{int_icons.get(g,'')} {g}" for g in int_grupos])

for tab, grupo in zip(tabs_int, int_grupos):
    with tab:
        noticias_raw = _noticias_grupo(grupo, 15)
        noticias_g   = _filtrar_por_fecha(noticias_raw, fecha_desde, fecha_hasta)
        st.html(_render_noticias_grid(noticias_g, grupo, GRUPO_STYLE_INTERNACIONAL))

st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN C — CHAT SOBRE LA INDUSTRIA
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo("💬 Chat con el Analista Siderúrgico")

CHAT_KEY_IND = "chat_industria_msgs"
if CHAT_KEY_IND not in st.session_state:
    st.session_state[CHAT_KEY_IND] = []

# Reserve visual slot above the input controls — filled after processing
chat_placeholder = st.container()

prompt_ind = st.chat_input(
    "Pregunta sobre la industria siderúrgica...",
    key="chat_input_industria",
)

if st.button("🗑 Limpiar conversación", key="chat_ind_clear"):
    st.session_state[CHAT_KEY_IND] = []
    # no st.rerun() — placeholder below will render empty list

# Process new message synchronously (no spinner, no rerun)
if prompt_ind and _GEMINI_KEY:
    msgs = st.session_state[CHAT_KEY_IND]
    msgs.append({"role": "user", "content": prompt_ind})
    hist_txt = "\n".join(
        ("Analista" if m['role'] == 'assistant' else "Usuario") + ": " + m['content']
        for m in msgs[:-1]
    )
    conv_block_ind = ("Conversación previa:\n" + hist_txt + "\n") if hist_txt else ""
    full_prompt_ind = (
        "Contexto: Analista de la industria siderúrgica para TYASA México.\n\n"
        f"{conv_block_ind}"
        f"Usuario: {prompt_ind}"
    )
    resp_ind = _call_gemini_text(full_prompt_ind, _GEMINI_KEY)
    msgs.append({"role": "assistant", "content": resp_ind})

# Render final chat state into the reserved slot (above the input)
with chat_placeholder:
    st.html(_render_chat_html(st.session_state[CHAT_KEY_IND], bool(_GEMINI_KEY)))
