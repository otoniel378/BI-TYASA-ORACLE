"""
chat_widget.py — Panel de chat compacto para el drawer lateral de TYASA BI.
Características:
  - Contexto acumulativo de todo el sistema (todas las páginas aportan datos)
  - Auto-guardado de insights después de respuestas con análisis real
  - Ejecución de análisis del sistema desde el chat
"""

from __future__ import annotations
import streamlit as st

_HIST_KEY  = "chat_historial_gemini"
_MSGS_KEY  = "chat_mensajes_display"
_MEM_KEY   = "chat_memorias_previas"
_CTX_KEY   = "chat_contexto_previo"
_SYS_KEY   = "_tyasa_ctx"           # contexto acumulativo del sistema
_INP_KEY   = "chat_widget_input"
_AUTOSAVE_THRESHOLD = 6             # mensajes antes de intentar auto-guardar


def _asegurar_init():
    for key, default in [
        (_HIST_KEY, []),
        (_MSGS_KEY, []),
        (_MEM_KEY,  []),
        (_CTX_KEY,  ""),
        (_SYS_KEY,  {}),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def _cargar_memorias_lazy(gemini_key: str):
    if st.session_state[_MEM_KEY] or not gemini_key:
        return
    try:
        from core.memoria_ia import cargar_memorias_contexto, construir_contexto_previo
        mems = cargar_memorias_contexto()
        st.session_state[_MEM_KEY] = mems
        st.session_state[_CTX_KEY] = construir_contexto_previo(mems)
    except Exception:
        pass


# ── API pública para que las páginas actualicen el contexto del sistema ────────
def actualizar_contexto_sistema(clave: str, datos: dict):
    """
    Llamada por las páginas para exportar sus datos al contexto del chat.
    Ejemplo: actualizar_contexto_sistema("negros_kpis", {"toneladas": 1234, ...})
    """
    if _SYS_KEY not in st.session_state:
        st.session_state[_SYS_KEY] = {}
    st.session_state[_SYS_KEY][clave] = datos


def _construir_contexto(seccion_label: str, subseccion: str) -> str:
    """Construye el prompt de contexto completo: memoria + sistema + página actual."""
    ctx_mem = st.session_state.get(_CTX_KEY, "")
    partes: list[str] = []

    if seccion_label:
        partes.append(f"PÁGINA ACTIVA: {seccion_label} → {subseccion}")

    # ── Contexto acumulativo del sistema ──────────────────────────────────────
    sys_ctx: dict = st.session_state.get(_SYS_KEY, {})
    if sys_ctx:
        partes.append("\nDATA DEL SISTEMA TYASA BI (cargada mientras el usuario navega):")

    # KPIs de ventas
    kpis = sys_ctx.get("negros_kpis") or sys_ctx.get("page_context", {})
    if kpis and kpis.get("toneladas_totales"):
        partes.append(
            f"  Aceros Negros — KPIs: {kpis['toneladas_totales']:,.1f} ton | "
            f"{kpis.get('clientes_activos','?')} clientes | "
            f"Top cliente: {kpis.get('top_cliente','?')} | "
            f"Top producto: {kpis.get('top_producto','?')} | "
            f"MoM: {kpis.get('variacion_mom_pct', 0):+.1f}%"
        )

    # Mañanera
    man = sys_ctx.get("mananera") or {}
    if man.get("mananera_fecha"):
        partes.append(f"  Mañanera analizada: {man['mananera_fecha']}")
        for p in (man.get("mananera_resumen") or [])[:3]:
            partes.append(f"    • {str(p)[:130]}")
        if man.get("mananera_insight"):
            partes.append(f"  Insight IA mañanera: {man['mananera_insight'][:150]}")
        if man.get("mananera_recomendacion"):
            partes.append(f"  Recomendación IA: {man['mananera_recomendacion'][:150]}")

    # Síntesis industrial
    sint = sys_ctx.get("sintesis_industria") or {}
    if sint.get("sintesis_nivel_alerta"):
        partes.append(f"  Síntesis industria — Alerta: {sint['sintesis_nivel_alerta']}")
        if sint.get("sintesis_recomendacion"):
            partes.append(f"  Recom. industria: {sint['sintesis_recomendacion'][:120]}")

    # Quiebres mercado
    qb = sys_ctx.get("quiebres") or {}
    if qb.get("n_quiebres"):
        partes.append(f"  Quiebres activos: {qb['n_quiebres']} variables con cambio estructural")

    # Sentimiento
    sent = sys_ctx.get("sentimiento") or {}
    if sent.get("nivel"):
        partes.append(
            f"  Sentimiento noticias: {sent['nivel']} "
            f"(score {sent.get('score_promedio', 0):+.2f}, "
            f"{sent.get('total_noticias', 0)} noticias)"
        )

    # page_context legacy (páginas que aún no migraron)
    pc = st.session_state.get("page_context") or {}
    if pc and not kpis:
        if pc.get("toneladas_totales"):
            partes.append(
                f"  Datos página activa — Toneladas: {pc['toneladas_totales']:,.1f} | "
                f"Clientes: {pc.get('clientes_activos','?')}"
            )
        if pc.get("mananera_fecha"):
            partes.append(f"  Mañanera activa: {pc['mananera_fecha']}")
            for p in (pc.get("mananera_resumen") or [])[:2]:
                partes.append(f"    • {str(p)[:120]}")

    ctx_page = "\n".join(partes) if partes else ""
    combined = (ctx_mem + "\n\n" + ctx_page).strip() if ctx_page else ctx_mem.strip()
    return combined


def _auto_guardar_insights(msgs: list[dict], gemini_key: str):
    """Auto-guarda insights después de respuestas con análisis real (silencioso)."""
    if not gemini_key or len(msgs) < _AUTOSAVE_THRESHOLD:
        return
    last_assistant = next(
        (m for m in reversed(msgs) if m["role"] == "assistant" and len(m.get("content", "")) > 150),
        None
    )
    if not last_assistant:
        return
    had_tools = bool(last_assistant.get("herramientas"))
    if not had_tools:
        return
    # Solo auto-guardar si no lo hemos hecho en esta sesión recientemente
    ya_guardado_en = st.session_state.get("_autosave_last_n", 0)
    if len(msgs) - ya_guardado_en < _AUTOSAVE_THRESHOLD:
        return
    try:
        from core.memoria_ia import (
            crear_tabla_si_no_existe,
            extraer_memorias_de_conversacion,
            guardar_memorias,
            cargar_memorias_contexto,
            construir_contexto_previo,
        )
        crear_tabla_si_no_existe()
        nuevas = extraer_memorias_de_conversacion(msgs[-10:], gemini_key)
        if nuevas:
            guardar_memorias(nuevas)
            mems = cargar_memorias_contexto()
            st.session_state[_MEM_KEY] = mems
            st.session_state[_CTX_KEY] = construir_contexto_previo(mems)
            st.session_state["_autosave_last_n"] = len(msgs)
    except Exception:
        pass


def _procesar_mensaje(prompt: str, gemini_key: str, contexto: str):
    from core.chat_ia import chat_turno

    st.session_state[_HIST_KEY].append({"role": "user", "parts": [prompt]})
    st.session_state[_MSGS_KEY].append({"role": "user", "content": prompt})

    resultado    = chat_turno(
        historial=st.session_state[_HIST_KEY],
        gemini_key=gemini_key,
        contexto_previo=contexto,
    )
    respuesta    = resultado.get("respuesta", "")
    herramientas = resultado.get("herramientas", [])
    error        = resultado.get("error")

    msg_entry = {
        "role":                "assistant",
        "content":             respuesta,
        "herramientas":        [{k: v for k, v in t.items() if k != "_df"} for t in herramientas],
        "_herramientas_df":    herramientas,
        "error":               error,
    }
    st.session_state[_MSGS_KEY].append(msg_entry)

    if respuesta:
        st.session_state[_HIST_KEY].append({"role": "model", "parts": [respuesta]})

    # Actualizar contexto del sistema con resultados de ejecutar_analisis
    for tool in herramientas:
        nombre   = tool.get("herramienta", "")
        result   = tool.get("_resultado_completo", {})
        analisis = result.get("analisis", "")

        if nombre == "ejecutar_analisis" and not result.get("error"):
            sys_ctx = st.session_state.get(_SYS_KEY, {})
            if analisis == "mananera":
                sys_ctx["mananera"] = {
                    "mananera_fecha":        result.get("fecha", ""),
                    "mananera_resumen":      result.get("resumen_ejecutivo", []),
                    "mananera_insight":      result.get("insight_estrategico", ""),
                    "mananera_recomendacion":result.get("recomendacion", ""),
                }
            elif analisis == "quiebres_mercado":
                sys_ctx["quiebres"] = {
                    "n_quiebres": result.get("total", 0),
                    "detalle":    result.get("quiebres", [])[:5],
                }
            elif analisis == "kpis_ventas":
                sys_ctx["negros_kpis"] = result
            elif analisis == "sentimiento_noticias":
                sys_ctx["sentimiento"] = {
                    "nivel":          result.get("nivel", ""),
                    "score_promedio": result.get("score_promedio", 0),
                    "total_noticias": result.get("total_noticias", 0),
                }
            st.session_state[_SYS_KEY] = sys_ctx

    # Auto-guardar insights (silencioso, en segundo plano)
    _auto_guardar_insights(st.session_state[_MSGS_KEY], gemini_key)


def render_drawer(gemini_key: str = "", seccion_label: str = "", subseccion: str = ""):
    """Renderiza el panel de chat compacto dentro de la columna derecha del drawer."""
    _asegurar_init()
    _cargar_memorias_lazy(gemini_key)

    # ── Header ────────────────────────────────────────────────────────────────
    st.html("""
    <div style="
        background:linear-gradient(135deg,#1B3A5C 0%,#2A5080 100%);
        border-radius:10px; padding:10px 14px; margin-bottom:8px;
        display:flex; align-items:center; justify-content:space-between;
    ">
        <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3rem;">🤖</span>
            <div>
                <div style="color:#fff;font-size:0.85rem;font-weight:700;line-height:1.2;">
                    Asistente TYASA BI
                </div>
                <div style="color:rgba(255,255,255,0.6);font-size:0.65rem;">
                    SQL · Noticias · Análisis en tiempo real
                </div>
            </div>
        </div>
    </div>
    """)

    # ── Badges de estado del sistema ──────────────────────────────────────────
    sys_ctx = st.session_state.get(_SYS_KEY, {})
    badges  = []
    if sys_ctx.get("negros_kpis") or sys_ctx.get("page_context", {}).get("toneladas_totales"):
        badges.append("📊 KPIs")
    if sys_ctx.get("mananera"):
        badges.append("🎙️ Mañanera")
    if sys_ctx.get("quiebres"):
        badges.append(f"⚡ {sys_ctx['quiebres'].get('n_quiebres',0)} quiebres")
    if sys_ctx.get("sentimiento"):
        nivel = sys_ctx["sentimiento"].get("nivel", "")
        badges.append(f"📰 {nivel}")
    mems = st.session_state.get(_MEM_KEY, [])
    if mems:
        badges.append(f"🧠 {len(mems)} memorias")

    if badges:
        badge_html = " &nbsp;".join(
            f"<span style='background:#EFF6FF;color:#1E40AF;border:1px solid #BFDBFE;"
            f"border-radius:10px;padding:2px 8px;font-size:0.65rem;font-weight:600;'>{b}</span>"
            for b in badges
        )
        st.html(f"<div style='margin-bottom:6px;line-height:2;'>{badge_html}</div>")

    # ── Historial de mensajes ──────────────────────────────────────────────────
    msgs    = st.session_state[_MSGS_KEY]
    recents = msgs[-12:] if len(msgs) > 12 else msgs

    dfs_por_idx: dict[int, list] = {}
    offset = max(0, len(msgs) - 12)
    for i, msg in enumerate(msgs):
        if "_herramientas_df" in msg:
            rel = i - offset
            if 0 <= rel < len(recents):
                dfs_por_idx[rel] = msg["_herramientas_df"]

    try:
        msgs_box = st.container(height=430, border=True)
    except TypeError:
        msgs_box = st.container()

    with msgs_box:
        if not recents:
            st.html("""
            <div style="color:#6B7280;font-size:0.78rem;padding:10px;line-height:1.8;">
                👋 <b>Hola!</b> Puedo ayudarte a:<br>
                • Analizar la mañanera de hoy con IA<br>
                • Revisar quiebres del mercado<br>
                • Consultar KPIs de ventas<br>
                • Buscar noticias del sector<br>
                • Hacer cualquier pregunta sobre los datos
            </div>
            """)
        else:
            for rel_i, msg in enumerate(recents):
                role = msg["role"]
                with st.chat_message("user" if role == "user" else "assistant"):
                    if role == "user":
                        st.markdown(msg["content"])
                    else:
                        tools_df     = dfs_por_idx.get(rel_i, [])
                        tools_show   = tools_df if tools_df else msg.get("herramientas", [])

                        for tool in tools_show:
                            nombre = tool.get("herramienta", "")
                            err    = tool.get("error")

                            if err:
                                st.caption(f"⚠️ {err}")

                            elif nombre == "ejecutar_sql" and tool.get("sql"):
                                with st.expander(
                                    f"🔍 {tool.get('titulo','SQL')} · {tool.get('filas',0)} filas",
                                    expanded=False
                                ):
                                    st.code(tool["sql"], language="sql")
                                    _df = tool.get("_df")
                                    if _df is not None and not _df.empty:
                                        st.dataframe(_df, use_container_width=True,
                                                     height=min(200, 35 + 35 * len(_df)))

                            elif nombre == "buscar_noticias" and tool.get("noticias"):
                                nots = tool["noticias"]
                                with st.expander(
                                    f"📰 Noticias · {len(nots)} resultados",
                                    expanded=False
                                ):
                                    for n in nots:
                                        if n.get("titulo"):
                                            st.caption(f"**{n['titulo']}** — {n.get('fuente','')} {n.get('fecha','')[:10]}")

                            elif nombre == "obtener_precios_mercado":
                                _df = tool.get("_df")
                                if _df is not None and not _df.empty:
                                    with st.expander(
                                        f"📊 Precios mercado · {tool.get('filas',0)} registros",
                                        expanded=False
                                    ):
                                        st.dataframe(_df, use_container_width=True,
                                                     height=min(200, 35 + 35 * len(_df)))

                            elif nombre == "ejecutar_analisis":
                                analisis = tool.get("analisis", "")
                                icons    = {"mananera": "🎙️", "quiebres_mercado": "⚡",
                                            "kpis_ventas": "📊", "sentimiento_noticias": "📰"}
                                icon     = icons.get(analisis, "🔧")
                                res      = tool.get("_resultado_completo", {})
                                n_items  = (
                                    len(res.get("resumen_ejecutivo", res.get("quiebres", [])))
                                    if res else 0
                                )
                                label = f"{icon} Análisis: {analisis} · {n_items} resultados"
                                with st.expander(label, expanded=False):
                                    if res.get("error"):
                                        st.error(res["error"])
                                    else:
                                        for k, v in res.items():
                                            if k in ("analisis", "ejecutado"):
                                                continue
                                            if isinstance(v, list) and v:
                                                st.markdown(f"**{k}:**")
                                                for item in v[:5]:
                                                    st.caption(f"• {str(item)[:120]}")
                                            elif isinstance(v, (str, int, float)) and v:
                                                st.caption(f"**{k}:** {v}")

                        content = msg.get("content", "")
                        if len(content) > 500:
                            st.markdown(content[:500] + "…")
                            with st.expander("Ver respuesta completa"):
                                st.markdown(content)
                        else:
                            st.markdown(content)

                        if msg.get("error") and msg["error"] not in ("max_iter",):
                            st.caption(f"⚠️ {msg['error']}")

    # ── Auto-save indicator ────────────────────────────────────────────────────
    last_autosave = st.session_state.get("_autosave_last_n", 0)
    if last_autosave > 0 and last_autosave == len(msgs):
        st.html(
            "<div style='font-size:0.65rem;color:#059669;text-align:right;margin-top:2px;'>"
            "🧠 Insights guardados automáticamente</div>"
        )

    # ── Input ──────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    inp = st.text_area(
        "msg",
        placeholder=(
            "Ejemplos:\n"
            "• Corre el análisis de la mañanera de hoy\n"
            "• Analiza los quiebres del mercado\n"
            "• ¿Cuál es mi cliente más grande este año?"
        ),
        height=90,
        key=_INP_KEY,
        label_visibility="collapsed",
    )

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        enviar = st.button("▶ Enviar", use_container_width=True,
                           type="primary", key="cw_send")
    with c2:
        if st.button("🗑️", key="cw_clear", help="Limpiar conversación",
                     use_container_width=True):
            st.session_state[_HIST_KEY] = []
            st.session_state[_MSGS_KEY] = []
            st.rerun()
    with c3:
        if st.button("↗️", key="cw_full", help="Abrir chat completo",
                     use_container_width=True):
            st.session_state.nav_seccion    = "chat_ia"
            st.session_state.nav_subseccion = "chat"
            st.session_state.chat_drawer_abierto = False
            st.rerun()

    if enviar and inp and inp.strip():
        if not gemini_key:
            st.error("Configura GEMINI_API_KEY en secrets.toml")
        else:
            contexto = _construir_contexto(seccion_label, subseccion)
            with st.spinner("Analizando…"):
                _procesar_mensaje(inp.strip(), gemini_key, contexto)
            if _INP_KEY in st.session_state:
                del st.session_state[_INP_KEY]
            st.rerun()
