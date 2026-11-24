"""
03_industria.py — Monitor de la Industria Siderúrgica — TYASA BI
Mañanera presidencial · Noticias Nacionales e Internacionales · Síntesis IA

DOM-STABLE: cero componentes condicionales.
  - st.spinner eliminado, se usa st.empty() con HTML de estado
  - Todas las secciones de resultado usan 1 st.empty() fijo
  - st.chat_message loop eliminado, se usa _render_chat_html() con burbujas HTML
"""
import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import json
import datetime

import streamlit as st
from config import COLORS
from mercado_noticias.analytics.noticias import (
    buscar_query_libre,
    GRUPOS_NACIONAL,
    GRUPOS_INTERNACIONAL,
    GRUPO_STYLE_NACIONAL,
    GRUPO_STYLE_INTERNACIONAL,
    _resolve_gnews_batch,
)
from mercado_noticias.analytics.ai_analysis import _call_gemini_text, sintesis_global, cargar_cache_hoy
from mercado_noticias.analytics.mananera import analizar_mananera, MANANERA_CACHE_DIR, MANANERA_CACHE_DAYS
from mercado_noticias.analytics.detector import detectar_quiebres_automatico
from core.components.filters import sidebar_header
from core.components.kpi_cards import seccion_titulo
from mercado_noticias.loaders import load_variables_mercado

# ── API key ───────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    _GEMINI_KEY = ""

from mercado_noticias.vistas_industria import (
    _noticias_grupo,
    _noticias_alerta_cached,
    _filtrar_por_fecha,
    _render_busqueda_libre,
    _render_noticias_grid,
    _render_sintesis_global,
    _render_alertas_mercado,
    _build_email_html,
    _enviar_email_digest,
    _render_mananera_full,
    _render_chat_html,
)



# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
sidebar_header("Industria Siderúrgica")

# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════
st.html(
    f"<h2 style='color:{COLORS['primary']};margin-bottom:0;'>Monitor de la Industria Siderúrgica</h2>"
)
st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN 0 — ANALISTA DE LA MAÑANERA PRESIDENCIAL
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo("Analista de la Mañanera Presidencial")

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
        run_man = st.form_submit_button("▶ Analizar", width="stretch")
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

# ── Noticias de inversión del día (complemento a la mañanera) ─────────────────
_nots_nearsh = _noticias_grupo("Nearshoring", 8)
_hoy_man_str = str(fecha_man)
_nots_inv_hoy = [
    n for n in _nots_nearsh
    if (n.get("fecha_pub") or "")[:10] >= _hoy_man_str
][:4]
if _nots_inv_hoy:
    _inv_cards = ""
    for _n in _nots_inv_hoy:
        _t  = (_n.get("titulo") or "")[:90]
        _u  = _n.get("url") or "#"
        _f  = (_n.get("fuente") or "").upper()
        _fd = (_n.get("fecha_pub") or "")[:10]
        _inv_cards += (
            f"<a href='{_u}' target='_blank' style='text-decoration:none;'>"
            f"<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;"
            f"padding:10px 14px;margin-bottom:8px;'>"
            f"<span style='font-size:11px;color:#0284C7;font-weight:700;'>{_f}</span>"
            f"<span style='font-size:10px;color:#9CA3AF;margin-left:8px;'>{_fd}</span>"
            f"<div style='font-size:13px;color:#1B3A5C;font-weight:600;margin-top:4px;line-height:1.4;'>{_t}</div>"
            f"</div></a>"
        )
    st.html(
        "<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;"
        "padding:14px 16px;margin-top:12px;'>"
        "<div style='font-size:13px;font-weight:800;color:#1D4ED8;margin-bottom:10px;'>"
        "Noticias de inversión y nearshoring del día</div>"
        + _inv_cards + "</div>"
    )

st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN A — SÍNTESIS EJECUTIVA GLOBAL (10 categorías + URLs + correo)
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo("Síntesis Ejecutiva Global")

_ALERTAS_CAT_KEY = "Alertas de Mercado"

# Auto-cargar desde caché si la sesión acaba de iniciar (botón correo siempre habilitado)
if "sint_result" not in st.session_state:
    _all_cat_keys = list(GRUPOS_NACIONAL.keys()) + list(GRUPOS_INTERNACIONAL.keys()) + [_ALERTAS_CAT_KEY]
    _base_cat_keys = list(GRUPOS_NACIONAL.keys()) + list(GRUPOS_INTERNACIONAL.keys())
    # Intentar con clave nueva (incluye "Alertas de Mercado"); fallback a clave legada
    _cached_hoy = (
        cargar_cache_hoy("sintesis_global", cat_keys=_all_cat_keys)
        or cargar_cache_hoy("sintesis_global", cat_keys=_base_cat_keys)
    )
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
                         width="stretch")
with col_frz_s:
    frz_sint = st.checkbox("Regenerar", key="sint_frz", value=False)
with col_email_b:
    enviar_email_clicked = st.button(
        "Enviar por correo", key="sint_email",
        width="stretch",
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

    # Resolver URLs de Google News (redirect -> URL real) solo para artículos de la síntesis
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
    _email_html = (
        f"<div style='background:{_em_color};border:1px solid {_em_border};"
        f"border-radius:8px;padding:10px 14px;font-size:13px;color:{_em_text};margin-top:6px;'>"
        f"{_email_st['msg']}</div>"
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
seccion_titulo("Noticias de la Industria")

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
    hoy_clicked = st.button("Hoy", key="ind_hoy", width="stretch",
                            help="Ver solo noticias de hoy")
with col_act:
    st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
    if st.button("Actualizar", key="ind_refresh", width="stretch"):
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
    + (" · *Solo hoy*" if hoy_clicked else "")
)

# ── Fila 2: buscador libre ────────────────────────────────────────────────────
col_busq, col_busq_btn = st.columns([4, 1])
with col_busq:
    query_libre = st.text_input(
        "busqueda",
        placeholder="Buscar noticias por tema, empresa o fuente…  ej: HRC México, T-MEC acero, Fastmarkets",
        key="ind_query_libre",
        label_visibility="collapsed",
    )
with col_busq_btn:
    buscar_clicked = st.button("Buscar", key="ind_buscar_btn", width="stretch")

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
        "Limpiar búsqueda",
        key="ind_busq_clear",
        width="stretch",
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
    "<span style='font-size:18px;font-weight:900;color:#1B3A5C;letter-spacing:-0.02em;'>Nacionales</span>"
    "<span style='margin-left:auto;font-size:10px;color:#9CA3AF;font-style:italic;'>"
    "Reforma · El Financiero · El Universal · Milenio · El Economista · ReporteAcero · +</span>"
    "</div>"
)

nac_grupos = list(GRUPOS_NACIONAL.keys())
tabs_nac = st.tabs(nac_grupos)

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
    "<span style='font-size:18px;font-weight:900;color:#1B3A5C;letter-spacing:-0.02em;'>Internacionales</span>"
    "<span style='margin-left:auto;font-size:10px;color:#9CA3AF;font-style:italic;'>"
    "Fastmarkets · Reuters · Bloomberg · WorldSteel · S&amp;P Global · CRU · +</span>"
    "</div>"
)

int_grupos = list(GRUPOS_INTERNACIONAL.keys())
tabs_int = st.tabs(int_grupos)

for tab, grupo in zip(tabs_int, int_grupos):
    with tab:
        noticias_raw = _noticias_grupo(grupo, 15)
        noticias_g   = _filtrar_por_fecha(noticias_raw, fecha_desde, fecha_hasta)
        st.html(_render_noticias_grid(noticias_g, grupo, GRUPO_STYLE_INTERNACIONAL))

st.divider()

# ════════════════════════════════════════════════════════════════════════════
# SECCIÓN C — CHAT SOBRE LA INDUSTRIA
# ════════════════════════════════════════════════════════════════════════════
seccion_titulo("Chat con el Analista Siderúrgico")

CHAT_KEY_IND = "chat_industria_msgs"
if CHAT_KEY_IND not in st.session_state:
    st.session_state[CHAT_KEY_IND] = []

# Reserve visual slot above the input controls — filled after processing
chat_placeholder = st.container()

prompt_ind = st.chat_input(
    "Pregunta sobre la industria siderúrgica...",
    key="chat_input_industria",
)

if st.button("Limpiar conversación", key="chat_ind_clear"):
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
