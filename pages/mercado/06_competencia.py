"""
06_competencia.py — Monitor de Competencia Siderúrgica — TYASA BI

Google News + LinkedIn · Facebook · Instagram · Twitter/X (Scrapingdog)
UI: estilo IntelCore — filtros en barra superior, card grid 3 columnas.
DOM-STABLE: todo HTML dinámico usa st.html().
"""
import os
import sys
import datetime
import json
import hashlib
from pathlib import Path

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
from config import COLORS
from core.components.filters import sidebar_header
from core.components.kpi_cards import seccion_titulo
from mercado_noticias.analytics.competencia import (
    EMPRESAS_COMPETENCIA,
    buscar_noticias_empresa,
    get_apify_feed,
    get_apify_posts,
    calcular_metricas_benchmarking,
    clasificar_temas_ia,
    render_feed_noticias,
    render_feed_social,
    limpiar_cache_social,
    _TEMAS_SIDERURGICOS,
)
from mercado_noticias.analytics.ai_analysis import _call_gemini_text

# ── API Keys ──────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

try:
    _APIFY_KEY = st.secrets["APIFY_API_TOKEN"]
except Exception:
    _APIFY_KEY = ""

_ROOT_DIR  = Path(_root)
_CACHE_DIR = _ROOT_DIR / "cache" / "ai_summaries"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — NOTICIAS
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def _noticias_empresa_cached(empresa: str, max_r: int = 8) -> list[dict]:
    return buscar_noticias_empresa(empresa, max_r=max_r)


def _get_todas_noticias(empresas: list[str], max_r: int = 8) -> list[dict]:
    todas: list[dict] = []
    seen:  set[str]   = set()
    for emp in empresas:
        for n in _noticias_empresa_cached(emp, max_r):
            url = n.get("url", "")
            if url and url not in seen:
                seen.add(url)
                todas.append(n)
    todas.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return todas


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — REDES SOCIALES (Apify)
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=14400, show_spinner=False)
def _feed_apify_cached(empresas_key: str, api_key: str, redes_key: str, n: int = 8) -> list[dict]:
    empresas = empresas_key.split("|")
    redes    = redes_key.split("|") if redes_key else ["linkedin", "instagram", "facebook", "twitter"]
    return get_apify_feed(empresas, api_key, redes=redes, n_por_empresa=n)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — SÍNTESIS IA
# ════════════════════════════════════════════════════════════════════════════

def _cache_key_sint(empresas: list[str]) -> str:
    hoy = datetime.date.today().isoformat()
    raw = f"competencia|{hoy}|{'_'.join(sorted(empresas))}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _cache_load_sint(key: str) -> dict | None:
    path = _CACHE_DIR / f"comp_{key}.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _cache_save_sint(key: str, data: dict) -> None:
    path = _CACHE_DIR / f"comp_{key}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _generar_sintesis(noticias: list[dict], posts: list[dict],
                      empresas: list[str], api_key: str,
                      force_refresh: bool = False) -> dict:
    ckey   = _cache_key_sint(empresas)
    cached = _cache_load_sint(ckey)
    if cached and not force_refresh:
        cached["_cached"] = True
        return cached

    lineas_n = [
        f"[{n.get('empresa','')} | {n.get('fecha_pub','')}] {(n.get('titulo','') or '')[:120]}"
        for n in noticias[:20]
    ]
    lineas_s = [
        f"[{p.get('empresa','')} | {p.get('red','')} | {p.get('fecha_pub','')}] "
        f"{(p.get('texto','') or '')[:200]}"
        for p in posts[:20]
    ]

    prompt = f"""Eres un analista de inteligencia competitiva para TYASA, fabricante mexicano de acero.
Analiza la actividad reciente de estos competidores: {', '.join(empresas)}.

NOTICIAS EN MEDIOS:
{chr(10).join(lineas_n) if lineas_n else 'Sin noticias disponibles.'}

POSTS REDES SOCIALES:
{chr(10).join(lineas_s) if lineas_s else 'Sin posts disponibles.'}

Genera análisis ejecutivo en JSON con esta estructura EXACTA:
{{
  "nivel_actividad_general": "Alto | Medio | Bajo",
  "resumen_ejecutivo": "2-3 oraciones sobre el panorama competitivo actual",
  "por_empresa": [
    {{
      "empresa": "nombre",
      "nivel_actividad": "Alto | Medio | Bajo",
      "hallazgo_principal": "1 oración, máx 25 palabras",
      "tipo": "Expansión | Nuevo producto | Movimiento ejecutivo | Financiero | Marketing | Otro"
    }}
  ],
  "alertas_para_tyasa": ["Alerta 1 (máx 20 palabras)", "Alerta 2"],
  "oportunidades": ["Oportunidad 1 (máx 20 palabras)"],
  "recomendacion": "Acción específica para TYASA (máx 30 palabras)"
}}
Solo JSON, sin texto adicional."""

    texto = _call_gemini_text(prompt, api_key)
    if not texto:
        return {"_error": "No se pudo generar el análisis. Verifica la API key de Gemini."}

    import re
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if not match:
        return {"_error": "Respuesta de Gemini no contiene JSON válido."}

    try:
        resultado = json.loads(match.group())
        resultado["_cached"] = False
        resultado["_fecha"]  = datetime.date.today().isoformat()
        _cache_save_sint(ckey, resultado)
        return resultado
    except Exception:
        return {"_error": "No se pudo parsear la respuesta de Gemini."}


_NIVEL_STYLE = {
    "Alto":  ("#DC2626", "#FEE2E2"),
    "Medio": ("#D97706", "#FEF3C7"),
    "Bajo":  ("#059669", "#D1FAE5"),
}
_TIPO_COLOR = {
    "Expansión":            ("#1B3A5C", "#E8EFF6"),
    "Nuevo producto":       ("#059669", "#D1FAE5"),
    "Movimiento ejecutivo": ("#7C3AED", "#EDE9FE"),
    "Financiero":           ("#D97706", "#FEF3C7"),
    "Marketing":            ("#0F766E", "#CCFBF1"),
    "Otro":                 ("#6B7280", "#F3F4F6"),
}


def _render_sintesis(result: dict | None) -> str:
    if result is None:
        return (
            "<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            "padding:16px;color:#0369A1;font-size:13px;'>"
            "ℹ️ Haz clic en <b>▶ Generar síntesis</b> para obtener el análisis "
            "ejecutivo de la competencia con IA.</div>"
        )
    err = result.get("_error")
    if err:
        return (
            f"<div style='background:#FEF2F2;border:1px solid #FCA5A5;border-radius:8px;"
            f"padding:16px;color:#DC2626;font-size:13px;'>⚠️ {err}</div>"
        )

    nivel  = result.get("nivel_actividad_general", "—")
    nc, nb = _NIVEL_STYLE.get(nivel, ("#6B7280", "#F3F4F6"))
    resumen = result.get("resumen_ejecutivo", "")
    fecha   = result.get("_fecha", "")
    cached  = result.get("_cached", False)
    cache_b = (
        '<span style="background:#F3F4F6;color:#6B7280;padding:3px 10px;'
        'border-radius:20px;font-size:11px;margin-left:6px;">💾 Caché</span>'
    ) if cached else ""

    header = (
        f"<div style='display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap;'>"
        f"<span style='background:{nb};color:{nc};padding:5px 14px;border-radius:20px;"
        f"font-size:12px;font-weight:700;'>⚡ Actividad competitiva: {nivel}</span>"
        f"<span style='background:#F3F4F6;color:#6B7280;padding:4px 12px;"
        f"border-radius:20px;font-size:11px;'>📅 {fecha}</span>{cache_b}"
        f"</div>"
    )

    resumen_html = (
        f"<div style='background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;"
        f"padding:16px;margin-bottom:14px;font-size:13px;color:#374151;line-height:1.65;'>"
        f"🌐 {resumen}</div>"
    ) if resumen else ""

    por_empresa = result.get("por_empresa", []) or []
    filas = []
    for e in por_empresa:
        emp  = e.get("empresa", "")
        niv  = e.get("nivel_actividad", "Bajo")
        hall = e.get("hallazgo_principal", "")
        tipo = e.get("tipo", "Otro")
        ec, eb = _NIVEL_STYLE.get(niv, ("#6B7280", "#F3F4F6"))
        tc, tb = _TIPO_COLOR.get(tipo, ("#6B7280", "#F3F4F6"))
        meta   = EMPRESAS_COMPETENCIA.get(emp, {})
        emp_c  = meta.get("color", "#374151")
        emp_bg = meta.get("bg", "#F3F4F6")
        emp_ico = meta.get("icon", "🏭")
        filas.append(
            f"<tr>"
            f"<td style='padding:10px 12px;'>"
            f"<span style='background:{emp_bg};color:{emp_c};padding:3px 10px;"
            f"border-radius:14px;font-size:10px;font-weight:700;'>{emp_ico} {emp}</span></td>"
            f"<td style='padding:10px 12px;'>"
            f"<span style='background:{eb};color:{ec};padding:2px 9px;border-radius:14px;"
            f"font-size:10px;font-weight:700;'>{niv}</span></td>"
            f"<td style='padding:10px 12px;font-size:12px;color:#374151;'>{hall}</td>"
            f"<td style='padding:10px 12px;'>"
            f"<span style='background:{tb};color:{tc};padding:2px 8px;border-radius:10px;"
            f"font-size:10px;font-weight:600;'>{tipo}</span></td>"
            f"</tr>"
        )

    tabla_html = ""
    if filas:
        tabla_html = (
            "<div style='margin-bottom:14px;overflow-x:auto;'>"
            "<div style='font-size:11px;font-weight:800;color:#1B3A5C;"
            "letter-spacing:.06em;margin-bottom:8px;'>📊 ACTIVIDAD POR EMPRESA</div>"
            "<table style='width:100%;border-collapse:collapse;'>"
            "<thead><tr style='background:#F8FAFC;border-bottom:2px solid #E2E8F0;'>"
            "<th style='padding:8px 12px;font-size:10px;color:#6B7280;font-weight:700;'>EMPRESA</th>"
            "<th style='padding:8px 12px;font-size:10px;color:#6B7280;font-weight:700;'>ACTIVIDAD</th>"
            "<th style='padding:8px 12px;font-size:10px;color:#6B7280;font-weight:700;'>HALLAZGO</th>"
            "<th style='padding:8px 12px;font-size:10px;color:#6B7280;font-weight:700;'>TIPO</th>"
            "</tr></thead>"
            f"<tbody>{''.join(filas)}</tbody>"
            "</table></div>"
        )

    alertas = result.get("alertas_para_tyasa", []) or []
    opors   = result.get("oportunidades", []) or []
    _vacio  = "<div style='color:#9CA3AF;font-size:12px;padding:6px 0;'>—</div>"

    def _items(lst, color, bg):
        if not lst:
            return _vacio
        return "".join(
            f"<div style='background:{bg};border-left:3px solid {color};"
            f"border-radius:0 8px 8px 0;padding:8px 14px;margin-bottom:5px;"
            f"font-size:12.5px;color:#374151;line-height:1.5;'>{item}</div>"
            for item in lst
        )

    dos_col = (
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;'>"
        "<div><div style='font-size:11px;font-weight:800;color:#DC2626;"
        "letter-spacing:.06em;margin-bottom:8px;'>⚠️ ALERTAS PARA TYASA</div>"
        f"{_items(alertas,'#DC2626','#FEF2F2')}</div>"
        "<div><div style='font-size:11px;font-weight:800;color:#059669;"
        "letter-spacing:.06em;margin-bottom:8px;'>✅ OPORTUNIDADES</div>"
        f"{_items(opors,'#059669','#F0FDF4')}</div>"
        "</div>"
    )

    rec = result.get("recomendacion", "") or ""
    rec_html = (
        f"<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
        f"padding:12px 16px;font-size:13px;color:#1E40AF;'>"
        f"🎯 <b>Recomendación para TYASA:</b> {rec}</div>"
    ) if rec else ""

    return header + resumen_html + tabla_html + dos_col + rec_html


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
sidebar_header("Competencia", "🎯")

# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════
st.html(
    f"<h2 style='color:{COLORS['primary']};margin-bottom:4px;'>🎯 Monitor de Competencia</h2>"
    f"<p style='color:#6B7280;font-size:13px;margin-bottom:0;'>"
    f"ArcelorMittal · Ternium · Deacero · Tenaris TAMSA · SIMEC · AHMSA · Gerdau · Corsa Acero</p>"
)
st.divider()

# ════════════════════════════════════════════════════════════════════════════
# CONTROLES GLOBALES — empresa + fechas
# ════════════════════════════════════════════════════════════════════════════
hoy        = datetime.date.today()
hace_90d   = hoy - datetime.timedelta(days=90)
hace_7d    = hoy - datetime.timedelta(days=7)
todas_empresas = list(EMPRESAS_COMPETENCIA.keys())

col_emp, col_rng, col_act = st.columns([3, 3, 1])

with col_emp:
    empresas_sel = st.multiselect(
        "Empresas a monitorear",
        options=todas_empresas,
        default=todas_empresas,
        key="comp_empresas",
        placeholder="Selecciona competidores…",
    )

with col_rng:
    rango = st.date_input(
        "Período",
        value=(hace_7d, hoy),
        min_value=hace_90d,
        max_value=hoy,
        key="comp_rango",
        format="DD/MM/YYYY",
    )

with col_act:
    st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Actualizar", key="comp_refresh", width="stretch"):
        limpiar_cache_social()
        st.cache_data.clear()

if isinstance(rango, (list, tuple)) and len(rango) == 2:
    fecha_desde, fecha_hasta = str(rango[0]), str(rango[1])
else:
    fecha_desde = str(hace_7d)
    fecha_hasta = str(hoy)

if not empresas_sel:
    st.warning("Selecciona al menos una empresa para ver resultados.")
    st.stop()

st.caption(
    f"Monitoreando **{len(empresas_sel)}** empresa(s) · período {fecha_desde} al {fecha_hasta}"
)

# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab_noticias, tab_pub, tab_bench, tab_temas, tab_sintesis = st.tabs([
    "📰 Noticias en Medios",
    "📌 Publicaciones Reales",
    "📊 Evaluación Comparativa",
    "🏷️ Análisis de Contenido IA",
    "🤖 Síntesis Ejecutiva",
])


# ── Tab 1: Noticias ───────────────────────────────────────────────────────────
with tab_noticias:
    with st.spinner("Buscando noticias en Google News…"):
        noticias_all = _get_todas_noticias(empresas_sel, max_r=8)
    st.html(render_feed_noticias(noticias_all, empresas_sel, fecha_desde, fecha_hasta))


# ── Tab 2: Publicaciones Reales (Apify) ──────────────────────────────────────
with tab_pub:
    if not _APIFY_KEY:
        st.html(
            "<div style='background:#FFF7ED;border:1px solid #FED7AA;border-radius:12px;"
            "padding:24px;max-width:640px;margin:24px auto;'>"
            "<div style='font-size:18px;font-weight:800;color:#92400E;margin-bottom:12px;'>"
            "📌 Publicaciones Reales — Configuración requerida</div>"
            "<p style='font-size:13px;color:#78350F;margin-bottom:16px;line-height:1.65;'>"
            "Para ver las publicaciones reales (contenido, likes, fecha) de "
            "Instagram, Facebook y Twitter/X de tus competidores necesitas "
            "una cuenta de <b>Apify</b> (~$49/mes).</p>"
            "<div style='background:#fff;border:1px solid #FED7AA;border-radius:8px;"
            "padding:16px;margin-bottom:14px;font-size:12.5px;color:#374151;line-height:1.8;'>"
            "<b>Pasos para activarlo:</b><br>"
            "1. Crea cuenta en <b>https://apify.com</b> (plan Starter)<br>"
            "2. Ve a <b>Settings → Integrations</b> → copia tu <b>API Token</b><br>"
            "3. Pega el token en <code>.streamlit/secrets.toml</code>:<br>"
            "<code style='background:#F3F4F6;padding:4px 8px;border-radius:4px;display:block;"
            "margin-top:6px;'>APIFY_API_TOKEN = \"apify_api_xxxxxxxxxxxx\"</code><br>"
            "4. Reinicia la app — las publicaciones aparecerán aquí automáticamente."
            "</div>"
            "<div style='font-size:11.5px;color:#92400E;margin-top:10px;'>"
            "<b>Qué obtendrás:</b> Texto de publicación · Fecha · Likes · Comentarios · "
            "Compartidos · Link directo<br>"
            "<b>Confiabilidad:</b> Instagram ✅ Alta · Facebook ✅ Alta · "
            "Twitter/X ⚠️ Media · LinkedIn ⚠️ Media<br><br>"
            "<b>LinkedIn (paso extra):</b> Para ver posts de LinkedIn además del API Token "
            "necesitas tu cookie de sesión: abre linkedin.com → F12 → Application → Cookies "
            "→ copia el valor de <code>li_at</code> → pégalo en secrets.toml como "
            "<code>LINKEDIN_LI_AT_COOKIE</code>.</div>"
            "</div>"
        )
    else:
        # Mostrar estado de configuración por red
        _red_status = [
            ("📸 Instagram", True, "Alta"),
            ("📘 Facebook",  True, "Alta"),
            ("𝕏 Twitter",   True, "Media"),
            ("💼 LinkedIn",  True, "Alta"),
        ]
        status_html = "<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;'>"
        for red_n, ok, conf in _red_status:
            bg = "#D1FAE5" if ok else "#FEF3C7"
            tc = "#065F46" if ok else "#92400E"
            ico = "✅" if ok else "⚙️"
            status_html += (
                f"<span style='background:{bg};color:{tc};padding:4px 12px;"
                f"border-radius:20px;font-size:11px;font-weight:600;'>"
                f"{ico} {red_n} — {conf}</span>"
            )
        status_html += "</div>"
        st.html(status_html)

        # Las 4 redes disponibles sin cookies
        _ap_redes_opts = {
            "Todas":          None,
            "📸 Instagram":   "instagram",
            "📘 Facebook":    "facebook",
            "𝕏 Twitter":     "twitter",
            "💼 LinkedIn":    "linkedin",
        }

        apc1, apc2, apc3 = st.columns([2, 2, 1])
        with apc1:
            ap_red_label = st.selectbox("Red Social", list(_ap_redes_opts), key="ap_red")
        with apc2:
            ap_emp_opts  = ["Todas las empresas"] + empresas_sel
            ap_emp_label = st.selectbox("Empresa", ap_emp_opts, key="ap_emp")
        with apc3:
            st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
            ap_refresh = st.button("🔄", key="ap_refresh", help="Forzar recarga desde Apify")

        ap_red_val = _ap_redes_opts[ap_red_label]
        ap_redes   = [ap_red_val] if ap_red_val else ["instagram", "facebook", "twitter", "linkedin"]
        ap_empresas   = [ap_emp_label] if ap_emp_label != "Todas las empresas" else empresas_sel

        with st.spinner(f"Obteniendo publicaciones reales de {', '.join(ap_empresas)}…"):
            apify_posts: list[dict] = []
            for _emp in ap_empresas:
                apify_posts.extend(
                    get_apify_posts(_emp, _APIFY_KEY, ap_redes, n=8,
                                    force_refresh=ap_refresh)
                )
            apify_posts.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)

        # Filtrar por período
        apify_filtrados = [
            p for p in apify_posts
            if fecha_desde <= (p.get("fecha_pub", "") or "")[:10] <= fecha_hasta
        ]

        st.caption(f"**{len(apify_filtrados)}** publicaciones encontradas en el período "
                   f"{fecha_desde} → {fecha_hasta} (total cargadas: {len(apify_posts)})")

        if not apify_filtrados and apify_posts:
            st.info(f"Hay {len(apify_posts)} publicaciones pero ninguna cae en el período seleccionado. "
                    "Amplía el rango de fechas.")
        elif not apify_posts:
            st.warning("No se encontraron publicaciones. Verifica que el token de Apify es válido "
                       "y que las empresas tienen usuarios configurados.")
        else:
            # Render de cards de publicaciones
            _RED_COLORS = {
                "instagram": ("#E1306C", "#FDF2F8"),
                "facebook":  ("#1877F2", "#EFF6FF"),
                "twitter":   ("#000000", "#F9FAFB"),
                "linkedin":  ("#0A66C2", "#EFF6FF"),
            }
            cards_html = "<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:8px;'>"
            for p in apify_filtrados[:24]:
                emp   = p.get("empresa", "")
                red   = p.get("red", "")
                texto = (p.get("texto", "") or "").strip()
                fecha = (p.get("fecha_pub", "") or "")[:10]
                likes = p.get("likes", 0) or 0
                coms  = p.get("comentarios", 0) or 0
                shares= p.get("compartidos", 0) or 0
                views = p.get("vistas", 0) or 0
                url   = p.get("url", "") or ""
                img   = p.get("imagen", "") or ""
                meta  = EMPRESAS_COMPETENCIA.get(emp, {})
                ec    = meta.get("color", "#374151")
                eb    = meta.get("bg", "#F3F4F6")
                ico   = meta.get("icon", "🏭")
                rc, rb = _RED_COLORS.get(red, ("#6B7280", "#F3F4F6"))
                red_label_map = {"instagram": "Instagram", "facebook": "Facebook", "twitter": "X/Twitter", "linkedin": "LinkedIn"}
                red_label = red_label_map.get(red, red)

                img_html = (
                    f"<img src='{img}' style='width:100%;height:140px;object-fit:cover;"
                    f"border-radius:6px;margin-bottom:8px;display:block;' />"
                ) if img else ""
                texto_preview = (texto[:240] + "…") if len(texto) > 240 else texto
                texto_html = (
                    f"<div style='font-size:12.5px;color:#374151;line-height:1.6;"
                    f"margin-bottom:10px;min-height:48px;'>{texto_preview}</div>"
                ) if texto_preview else ""

                stats_parts = []
                if likes:   stats_parts.append(f"❤️ {likes:,}")
                if coms:    stats_parts.append(f"💬 {coms:,}")
                if shares:  stats_parts.append(f"🔁 {shares:,}")
                if views:   stats_parts.append(f"👁 {views:,}")
                stats_html_str = (
                    f"<div style='display:flex;gap:10px;flex-wrap:wrap;font-size:11px;"
                    f"color:#6B7280;margin-bottom:8px;'>{'  '.join(stats_parts)}</div>"
                ) if stats_parts else ""

                link_html = (
                    f"<a href='{url}' target='_blank' style='font-size:11px;color:{rc};"
                    f"text-decoration:none;font-weight:600;'>Ver publicación →</a>"
                ) if url else ""

                cards_html += (
                    f"<div style='background:#fff;border:1px solid #E5E7EB;border-radius:12px;"
                    f"padding:14px;display:flex;flex-direction:column;'>"
                    f"<div style='display:flex;gap:6px;align-items:center;margin-bottom:10px;flex-wrap:wrap;'>"
                    f"<span style='background:{eb};color:{ec};padding:2px 9px;border-radius:14px;"
                    f"font-size:10px;font-weight:700;'>{ico} {emp}</span>"
                    f"<span style='background:{rb};color:{rc};padding:2px 8px;border-radius:14px;"
                    f"font-size:10px;font-weight:600;'>{red_label}</span>"
                    f"<span style='background:#F3F4F6;color:#9CA3AF;padding:2px 8px;border-radius:14px;"
                    f"font-size:10px;'>📅 {fecha}</span>"
                    f"</div>"
                    f"{img_html}{texto_html}{stats_html_str}{link_html}"
                    f"</div>"
                )
            cards_html += "</div>"
            st.html(cards_html)


# ── Tab 3: Evaluación Comparativa ────────────────────────────────────────────
with tab_bench:
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go

    with st.spinner("Calculando benchmarking…"):
        noticias_bm  = _get_todas_noticias(empresas_sel, max_r=8)
        _emp_key_bm  = "|".join(sorted(empresas_sel))
        posts_bm     = _feed_apify_cached(_emp_key_bm, _APIFY_KEY, "linkedin|instagram|facebook|twitter", n=8)

    metricas = calcular_metricas_benchmarking(posts_bm, noticias_bm, empresas_sel, fecha_desde, fecha_hasta)

    # ── Nivel 1: KPIs ─────────────────────────────────────────────────────────
    seccion_titulo("📊 Nivel 1 — Actividad")

    emp_mas_activo = max(metricas.items(), key=lambda x: x[1].get("total_posts", 0), default=("—", {}))
    emp_mas_eng    = max(metricas.items(), key=lambda x: x[1].get("avg_engagement", 0), default=("—", {}))
    total_posts_bm = sum(m.get("total_posts", 0) for m in metricas.values())
    total_nots_bm  = sum(m.get("noticias", 0) for m in metricas.values())

    st.html(
        "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;'>"
        + "".join([
            f"<div style='background:#fff;border:1px solid #E5E7EB;border-radius:10px;padding:14px 16px;'>"
            f"<div style='font-size:10px;font-weight:700;color:#6B7280;letter-spacing:.05em;margin-bottom:4px;'>{lbl}</div>"
            f"<div style='font-size:20px;font-weight:800;color:{clr};'>{val}</div>"
            f"<div style='font-size:11px;color:#9CA3AF;margin-top:2px;'>{sub}</div>"
            f"</div>"
            for lbl, val, clr, sub in [
                ("🏆 EMPRESA MÁS ACTIVA",   emp_mas_activo[0], "#1B3A5C",
                 f"{emp_mas_activo[1].get('total_posts', 0)} posts en período"),
                ("⚡ MAYOR ENGAGEMENT",      emp_mas_eng[0],    "#DC2626",
                 f"~{emp_mas_eng[1].get('avg_engagement', 0):.0f} por post"),
                ("📌 TOTAL PUBLICACIONES",   str(total_posts_bm), "#059669",
                 f"{len(empresas_sel)} empresas · todas las redes"),
                ("📰 MENCIONES EN MEDIOS",   str(total_nots_bm), "#D97706",
                 "Google News últimos 30 días"),
            ]
        ])
        + "</div>"
    )

    df_freq = pd.DataFrame([
        {
            "Empresa":   emp,
            "Posts":     m.get("total_posts", 0),
            "Instagram": m.get("por_red", {}).get("instagram", 0),
            "Facebook":  m.get("por_red", {}).get("facebook",  0),
            "Twitter":   m.get("por_red", {}).get("twitter",   0),
            "LinkedIn":  m.get("por_red", {}).get("linkedin",  0),
        }
        for emp, m in metricas.items()
    ]).sort_values("Posts", ascending=False)

    if not df_freq.empty and df_freq["Posts"].sum() > 0:
        fig_freq = go.Figure()
        for red_n, red_c in [("Instagram","#E1306C"),("Facebook","#1877F2"),("Twitter","#111827"),("LinkedIn","#0A66C2")]:
            if red_n in df_freq.columns:
                fig_freq.add_trace(go.Bar(name=red_n, x=df_freq["Empresa"], y=df_freq[red_n], marker_color=red_c))
        fig_freq.update_layout(
            barmode="stack", title="Frecuencia de publicación por empresa y red",
            title_font_size=14, font_family="Inter, sans-serif",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template="simple_white", margin=dict(t=60, b=20, l=0, r=0),
            yaxis_title="# Publicaciones",
        )
        st.plotly_chart(fig_freq, use_container_width=True)
    else:
        st.info("No hay datos de publicaciones para el período seleccionado. "
                "Ve a 📌 Publicaciones Reales y carga datos primero.")

    # ── Nivel 2: Engagement ────────────────────────────────────────────────────
    st.markdown("---")
    seccion_titulo("📈 Nivel 2 — Engagement")

    df_eng = pd.DataFrame([
        {
            "Empresa":         emp,
            "Avg Likes":       round(m.get("avg_likes", 0), 1),
            "Avg Comentarios": round(m.get("avg_comentarios", 0), 1),
            "Avg Compartidos": round(m.get("avg_compartidos", 0), 1),
        }
        for emp, m in metricas.items()
    ]).sort_values("Avg Likes", ascending=False)

    if not df_eng.empty and df_eng["Avg Likes"].sum() > 0:
        fig_eng = go.Figure()
        for col_n, col_c in [("Avg Likes","#DC2626"),("Avg Comentarios","#D97706"),("Avg Compartidos","#059669")]:
            fig_eng.add_trace(go.Bar(name=col_n, x=df_eng["Empresa"], y=df_eng[col_n], marker_color=col_c))
        fig_eng.update_layout(
            barmode="group", title="Engagement promedio por empresa",
            title_font_size=14, font_family="Inter, sans-serif",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template="simple_white", margin=dict(t=60, b=20, l=0, r=0),
            yaxis_title="Promedio por post",
        )
        st.plotly_chart(fig_eng, use_container_width=True)

    top_posts_all: list[dict] = []
    for emp_t, m_t in metricas.items():
        for tp in (m_t.get("top_posts") or [])[:3]:
            top_posts_all.append({
                "Empresa":     emp_t,
                "Red":         tp.get("red", ""),
                "Fecha":       (tp.get("fecha_pub", "") or "")[:10],
                "Likes":       tp.get("likes", 0),
                "Comentarios": tp.get("comentarios", 0),
                "Compartidos": tp.get("compartidos", 0),
                "Texto":       (tp.get("texto", "") or "")[:80],
            })

    if top_posts_all:
        st.markdown("**🏅 Top posts por empresa**")
        df_top = pd.DataFrame(top_posts_all).sort_values("Likes", ascending=False)
        st.dataframe(df_top, use_container_width=True, hide_index=True)

    _dias_full  = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    _dias_short = ["Lun",   "Mar",    "Mié",       "Jue",    "Vie",     "Sáb",    "Dom"]
    dias_rows: list[dict] = []
    for emp_d, m_d in metricas.items():
        for d_full, d_lbl in zip(_dias_full, _dias_short):
            dias_rows.append({"Empresa": emp_d, "Día": d_lbl, "Posts": (m_d.get("dias") or {}).get(d_full, 0)})

    if dias_rows:
        df_dias = pd.DataFrame(dias_rows)
        if df_dias["Posts"].sum() > 0:
            fig_heat = px.density_heatmap(
                df_dias, x="Día", y="Empresa", z="Posts",
                category_orders={"Día": _dias_short},
                color_continuous_scale="Blues",
                title="¿Qué días publica más cada empresa?",
            )
            fig_heat.update_layout(
                title_font_size=14, font_family="Inter, sans-serif",
                template="simple_white", margin=dict(t=50, b=20, l=0, r=0),
            )
            st.plotly_chart(fig_heat, use_container_width=True)

    if noticias_bm:
        st.markdown("---")
        st.markdown("**📰 Últimas noticias de la competencia**")
        df_news_bm = pd.DataFrame([
            {
                "Empresa": n.get("empresa", ""),
                "Titular": (n.get("titulo") or "")[:80],
                "Fecha":   n.get("fecha_pub", ""),
                "Fuente":  n.get("fuente", ""),
            }
            for n in sorted(noticias_bm, key=lambda x: x.get("fecha_pub", ""), reverse=True)[:15]
        ])
        if not df_news_bm.empty:
            st.dataframe(df_news_bm, use_container_width=True, hide_index=True)


# ── Tab 4: Análisis de Contenido IA ──────────────────────────────────────────
with tab_temas:
    import pandas as pd
    import plotly.express as px

    seccion_titulo("🏷️ Nivel 3 — Análisis de Contenido con IA")
    st.caption(
        "Gemini clasifica cada publicación en temas siderúrgicos para detectar "
        "qué estrategias está comunicando cada competidor."
    )

    _temas_col_btn, _temas_col_frz = st.columns([3, 1])
    with _temas_col_btn:
        run_temas = st.button(
            "▶ Clasificar publicaciones con IA",
            key="comp_temas_run",
            width="stretch",
            disabled=not _GEMINI_KEY,
        )
        if not _GEMINI_KEY:
            st.caption("⚙️ Configura GEMINI_API_KEY en secrets.toml para usar esta función.")
    with _temas_col_frz:
        frz_temas = st.checkbox("Regenerar", key="comp_temas_frz", value=False)

    _TEMAS_KEY = f"comp_temas_{'_'.join(sorted(empresas_sel))}"

    if run_temas and _GEMINI_KEY:
        _emp_key_t  = "|".join(sorted(empresas_sel))
        posts_t     = _feed_apify_cached(_emp_key_t, _APIFY_KEY, "linkedin|instagram|facebook|twitter", n=8)
        if posts_t:
            st.session_state[_TEMAS_KEY] = clasificar_temas_ia(posts_t, _GEMINI_KEY)
        else:
            st.warning("No hay publicaciones cargadas. Ve a 📌 Publicaciones Reales primero.")

    temas_result = st.session_state.get(_TEMAS_KEY)

    if temas_result is None:
        st.html(
            "<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            "padding:16px;color:#0369A1;font-size:13px;'>"
            "ℹ️ Haz clic en <b>▶ Clasificar publicaciones</b> para detectar los temas "
            "estratégicos que comunica cada competidor.</div>"
        )
    elif isinstance(temas_result, dict) and temas_result:
        temas_rows: list[dict] = []
        for emp_tm, temas_dict in temas_result.items():
            for tema, cnt in temas_dict.items():
                if cnt > 0:
                    temas_rows.append({"Empresa": emp_tm, "Tema": tema, "Posts": cnt})

        if temas_rows:
            df_temas = pd.DataFrame(temas_rows)
            fig_temas = px.bar(
                df_temas, x="Empresa", y="Posts", color="Tema",
                barmode="stack",
                title="Distribución de temas por empresa",
                color_discrete_sequence=px.colors.qualitative.Set3,
                category_orders={"Tema": _TEMAS_SIDERURGICOS},
            )
            fig_temas.update_layout(
                title_font_size=14, font_family="Inter, sans-serif",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                template="simple_white", margin=dict(t=70, b=20, l=0, r=0),
                yaxis_title="# Posts clasificados",
            )
            st.plotly_chart(fig_temas, use_container_width=True)

            pivot_temas = df_temas.pivot_table(index="Empresa", columns="Tema", values="Posts", fill_value=0)
            st.markdown("**Detalle por empresa y tema:**")
            st.dataframe(pivot_temas, use_container_width=True)
        else:
            st.info("La clasificación no produjo resultados. Intenta con más publicaciones.")


# ── Tab 4: Síntesis IA ────────────────────────────────────────────────────────
with tab_sintesis:
    seccion_titulo("🤖 Análisis ejecutivo de la competencia con IA")

    col_btn, col_frz = st.columns([3, 1])
    with col_btn:
        run_sint = st.button(
            "▶ Generar síntesis de competencia",
            key="comp_sint_run",
            width="stretch",
            disabled=not _GEMINI_KEY,
        )
        if not _GEMINI_KEY:
            st.caption("⚙️ Configura GEMINI_API_KEY en secrets.toml para usar esta función.")
    with col_frz:
        frz_sint = st.checkbox("Regenerar", key="comp_sint_frz", value=False)

    _SINT_KEY = f"comp_sint_{'_'.join(sorted(empresas_sel))}"

    if run_sint and _GEMINI_KEY:
        noticias_ctx = _get_todas_noticias(empresas_sel, max_r=8)
        _emp_key_s   = "|".join(sorted(empresas_sel))
        posts_ctx    = _feed_apify_cached(_emp_key_s, _APIFY_KEY, "linkedin|instagram|facebook|twitter", n=8)
        st.session_state[_SINT_KEY] = _generar_sintesis(
            noticias_ctx, posts_ctx, empresas_sel, _GEMINI_KEY, force_refresh=frz_sint
        )

    st.html(_render_sintesis(st.session_state.get(_SINT_KEY)))
