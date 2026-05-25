"""
chat.py — Chat conversacional con los datos de TYASA BI.
Powered by Gemini function calling + BigQuery + Memoria persistente entre sesiones.
"""

import streamlit as st

# ── Config ─────────────────────────────────────────────────────────────────────
try:
    _GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
except Exception:
    _GEMINI_KEY = ""

_HIST_KEY     = "chat_historial_gemini"
_MSGS_KEY     = "chat_mensajes_display"
_MEM_KEY      = "chat_memorias_previas"
_CTX_KEY      = "chat_contexto_previo"
_MAX_TURNS    = 20

# ── Inicializar session_state ──────────────────────────────────────────────────
if _HIST_KEY not in st.session_state:
    st.session_state[_HIST_KEY] = []
if _MSGS_KEY not in st.session_state:
    st.session_state[_MSGS_KEY] = []
if _MEM_KEY not in st.session_state:
    st.session_state[_MEM_KEY] = []
if _CTX_KEY not in st.session_state:
    st.session_state[_CTX_KEY] = ""

# ── Cargar memorias al inicio de sesión (una sola vez) ────────────────────────
from core.chat_ia    import PREGUNTAS_SUGERIDAS, chat_turno
from core.memoria_ia import (
    cargar_memorias_contexto,
    construir_contexto_previo,
    extraer_memorias_de_conversacion,
    guardar_memorias,
    crear_tabla_si_no_existe,
)

if not st.session_state[_MEM_KEY] and _GEMINI_KEY:
    try:
        mems = cargar_memorias_contexto()
        st.session_state[_MEM_KEY] = mems
        st.session_state[_CTX_KEY] = construir_contexto_previo(mems)
    except Exception:
        pass

# ── Header ─────────────────────────────────────────────────────────────────────
st.html("""
<div style="
    background:linear-gradient(135deg,#1B3A5C 0%,#2E5080 100%);
    border-radius:12px; padding:18px 24px; margin-bottom:16px;
    display:flex; align-items:center; gap:14px;
">
    <span style="font-size:2rem;">🤖</span>
    <div>
        <div style="color:#fff;font-size:1.2rem;font-weight:700;font-family:'Segoe UI',sans-serif;">
            Chat Analítico TYASA BI
        </div>
        <div style="color:rgba(255,255,255,0.65);font-size:0.8rem;margin-top:2px;">
            Pregunta sobre ventas, clientes, productos y mercado siderúrgico · Con memoria entre sesiones
        </div>
    </div>
</div>
""")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🤖 Chat IA")
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    n_msgs = len(st.session_state[_MSGS_KEY])
    st.caption(f"Mensajes esta sesión: {n_msgs}")

    if not _GEMINI_KEY:
        st.error("GEMINI_API_KEY no configurada")

    st.markdown("---")

    # Guardar insights de la sesión actual
    if st.button("💾 Guardar insights de esta sesión", use_container_width=True,
                 disabled=n_msgs < 4):
        with st.spinner("Extrayendo insights..."):
            try:
                crear_tabla_si_no_existe()
                nuevas = extraer_memorias_de_conversacion(
                    st.session_state[_MSGS_KEY], _GEMINI_KEY
                )
                if nuevas:
                    guardar_memorias(nuevas)
                    st.success(f"✅ {len(nuevas)} insights guardados")
                    # Refrescar memorias en contexto
                    mems = cargar_memorias_contexto()
                    st.session_state[_MEM_KEY] = mems
                    st.session_state[_CTX_KEY] = construir_contexto_previo(mems)
                else:
                    st.info("No se encontraron insights nuevos.")
            except Exception as e:
                st.warning(f"No se pudo guardar: {e}")

    if st.button("🗑️ Nueva conversación", use_container_width=True):
        st.session_state[_HIST_KEY] = []
        st.session_state[_MSGS_KEY] = []
        st.rerun()

    # Mostrar memorias activas
    mems = st.session_state.get(_MEM_KEY, [])
    if mems:
        st.markdown("---")
        st.markdown(f"**🧠 Memoria activa** ({len(mems)} insights)")
        for m in mems[:5]:
            rel = m.get("relevancia", "")
            dot = "🔴" if rel == "Alta" else "🟡" if rel == "Media" else "⚪"
            st.caption(f"{dot} **{m.get('tema','')}**: {m.get('contenido','')[:60]}...")

    st.markdown("---")
    st.markdown("**Modelo:** Gemini 2.5 Flash")
    st.markdown("**Datos:** BigQuery · tyasa_bi")

# ── Contexto previo (badge) ────────────────────────────────────────────────────
if st.session_state[_MEM_KEY]:
    n_m = len(st.session_state[_MEM_KEY])
    st.html(f"""
    <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;
                padding:8px 14px;margin-bottom:12px;font-size:0.78rem;color:#1E40AF;">
        🧠 <strong>Memoria activa:</strong> {n_m} insights de sesiones anteriores
        inyectados como contexto.
    </div>
    """)

# ── Preguntas sugeridas (solo si conversación vacía) ──────────────────────────
if not st.session_state[_MSGS_KEY]:
    st.markdown("#### Preguntas frecuentes")
    cols = st.columns(2)
    for i, pregunta in enumerate(PREGUNTAS_SUGERIDAS):
        with cols[i % 2]:
            if st.button(pregunta, key=f"sug_{i}", use_container_width=True):
                st.session_state["_chat_sug"] = pregunta
                st.rerun()
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Renderizar historial ───────────────────────────────────────────────────────
for msg in st.session_state[_MSGS_KEY]:
    role = msg["role"]
    with st.chat_message("user" if role == "user" else "assistant"):
        if role == "user":
            st.markdown(msg["content"])
        else:
            for tool in msg.get("herramientas", []):
                _titulo = tool.get("titulo", "Consulta SQL")
                _sql    = tool.get("sql", "")
                _filas  = tool.get("filas", 0)
                _err    = tool.get("error")
                if _err:
                    st.error(f"Error: {_err}")
                elif _sql:
                    with st.expander(f"🔍 {_titulo} — {_filas} filas", expanded=False):
                        st.code(_sql, language="sql")

            st.markdown(msg["content"])
            if msg.get("error"):
                st.warning(f"⚠️ {msg['error']}")

# ── Procesar sugerida pendiente ────────────────────────────────────────────────
_sug_pendiente = st.session_state.pop("_chat_sug", None)

# ── Input ──────────────────────────────────────────────────────────────────────
prompt_input = st.chat_input("Escribe tu pregunta sobre los datos de TYASA...")
prompt = _sug_pendiente or prompt_input

if prompt:
    if not _GEMINI_KEY:
        st.error("Configura GEMINI_API_KEY en .streamlit/secrets.toml para usar el chat.")
        st.stop()

    # Registrar mensaje del usuario
    st.session_state[_MSGS_KEY].append({"role": "user", "content": prompt})
    st.session_state[_HIST_KEY].append({"role": "user", "parts": [prompt]})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analizando datos..."):
            resultado = chat_turno(
                historial=st.session_state[_HIST_KEY],
                gemini_key=_GEMINI_KEY,
                contexto_previo=st.session_state.get(_CTX_KEY, ""),
            )

        respuesta    = resultado.get("respuesta", "")
        herramientas = resultado.get("herramientas", [])
        error        = resultado.get("error")

        # Mostrar queries ejecutadas
        for tool in herramientas:
            _titulo = tool.get("titulo", "Consulta SQL")
            _sql    = tool.get("sql", "")
            _filas  = tool.get("filas", 0)
            _df     = tool.get("_df")
            _err    = tool.get("error")
            if _err:
                st.error(f"Error: {_err}")
            elif _sql:
                with st.expander(f"🔍 {_titulo} — {_filas} filas", expanded=True):
                    st.code(_sql, language="sql")
                    if _df is not None and not _df.empty:
                        st.dataframe(_df, use_container_width=True,
                                     height=min(320, 35 + 35 * len(_df)))

        if respuesta:
            st.markdown(respuesta)
        elif error:
            st.error(f"Error: {error}")

    # Guardar en historial de display (sin DataFrame para evitar re-render pesado)
    st.session_state[_MSGS_KEY].append({
        "role":        "assistant",
        "content":     respuesta,
        "herramientas": [
            {k: v for k, v in t.items() if k != "_df"}
            for t in herramientas
        ],
        "error":       error,
    })

    if respuesta:
        st.session_state[_HIST_KEY].append({"role": "model", "parts": [respuesta]})

    if len(st.session_state[_MSGS_KEY]) >= _MAX_TURNS * 2:
        st.info(
            "💡 Conversación larga. Para mejor rendimiento usa "
            "'🗑️ Nueva conversación' y guarda los insights primero."
        )
