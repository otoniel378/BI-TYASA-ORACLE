"""
login.py — Pantalla de inicio de sesión TYASA BI.
Split-card: panel izquierdo (form) | panel derecho (brand).
"""
import os
import base64
import streamlit as st
from core.auth import autenticar, iniciar_sesion

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Buscar el logo en assets/img (cualquier formato soportado)
def _find_logo() -> tuple[str | None, str]:
    for fname, mime in [
        ("tyasa_logo.webp", "image/webp"),
        ("tyasa_logo.png",  "image/png"),
        ("tyasa_logo.jpg",  "image/jpeg"),
        ("tyasa_logo.svg",  "image/svg+xml"),
    ]:
        path = os.path.join(_ROOT, "assets", "img", fname)
        if os.path.exists(path):
            return path, mime
    return None, ""


def _logo_tag(style: str = "height:48px;width:auto;display:block;") -> str:
    """Devuelve un <img> con el logo TYASA usando el style CSS indicado."""
    path, mime = _find_logo()
    if path:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return (
            f'<img src="data:{mime};base64,{b64}" '
            f'style="{style}object-fit:contain;">'
        )
    return (
        '<div style="font-size:1.9rem;font-weight:900;letter-spacing:.04em;'
        'color:#1B3A5C;font-family:\'Segoe UI\',sans-serif;">TYASA BI</div>'
    )


# Solo puestos, sin nombres
_ROLES = {
    "director":   "Director General",
    "gerente":    "Gerente Comercial",
    "esp.negros": "Especialista — Aceros Planos Negros",
    "esp.largos": "Especialista — Aceros Largos",
    "esp.sbq":    "Especialista — Aceros SBQ",
}


def render_login():
    # Logo panel izquierdo: tamaño moderado
    logo_form  = _logo_tag("height:46px;width:auto;display:block;")
    # Logo panel derecho: ocupa casi todo el ancho, centrado
    logo_brand = _logo_tag(
        "width:88%;max-width:340px;height:auto;display:block;margin:0 auto;"
    )

    # ── CSS ────────────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    /* ── Animaciones ── */
    @keyframes driftA {
        0%,100% { transform:translateY(0) scale(1);    opacity:.50; }
        50%      { transform:translateY(-30px) scale(1.04); opacity:.75; }
    }
    @keyframes driftB {
        0%,100% { transform:translateY(0) scale(1);  opacity:.35; }
        50%      { transform:translateY(26px) scale(.96); opacity:.58; }
    }
    @keyframes driftC {
        0%,100% { transform:translateX(0);  opacity:.30; }
        50%      { transform:translateX(18px); opacity:.48; }
    }
    @keyframes fadeUp {
        from { opacity:0; transform:translateY(22px); }
        to   { opacity:1; transform:translateY(0);    }
    }
    @keyframes shimmer {
        0%   { background-position:-200% center; }
        100% { background-position: 200% center; }
    }
    @keyframes rotateSlow {
        from { transform:rotate(0deg);   }
        to   { transform:rotate(360deg); }
    }

    /* ── Chrome de Streamlit oculto ── */
    [data-testid="stSidebar"],
    header[data-testid="stHeader"],
    #MainMenu, footer { display:none !important; }

    /* ── Fondo: azul muy oscuro → gris carbón → toque rojo profundo ── */
    .stApp {
        background:
            radial-gradient(ellipse 80% 60% at 10% 90%, rgba(220,38,38,.18) 0%, transparent 55%),
            radial-gradient(ellipse 70% 50% at 90% 10%, rgba(29,78,216,.22) 0%, transparent 55%),
            linear-gradient(155deg, #060D1A 0%, #0F1C2E 35%, #131B2B 65%, #0A0F1A 100%);
        min-height:100vh;
    }

    /* ── Contenedor principal ── */
    [data-testid="stMainBlockContainer"] {
        max-width: 900px !important;
        margin: 5.5vh auto 0 auto !important;
        padding: 0 !important;
        background: transparent !important;
        animation: fadeUp .55s ease both;
    }

    /* ── Columnas → forman el card ── */
    [data-testid="stMainBlockContainer"] [data-testid="stHorizontalBlock"] {
        gap: 0 !important;
        align-items: stretch !important;
        border-radius: 24px;
        overflow: hidden;
        box-shadow:
            0 40px 90px rgba(0,0,0,.70),
            0 0 0 1px rgba(255,255,255,.07),
            inset 0 1px 0 rgba(255,255,255,.08);
    }

    /* ── Panel izquierdo — blanco puro ── */
    [data-testid="stMainBlockContainer"]
      [data-testid="stHorizontalBlock"]
      > [data-testid="stColumn"]:nth-child(1) {
        background: #FFFFFF !important;
        padding: 54px 52px 46px !important;
        border-radius: 24px 0 0 24px !important;
    }
    [data-testid="stMainBlockContainer"]
      [data-testid="stHorizontalBlock"]
      > [data-testid="stColumn"]:nth-child(1) > div { width:100% !important; }

    /* ── Panel derecho — sin padding extra (lo controla el st.html) ── */
    [data-testid="stMainBlockContainer"]
      [data-testid="stHorizontalBlock"]
      > [data-testid="stColumn"]:nth-child(2) {
        padding: 0 !important;
        border-radius: 0 24px 24px 0 !important;
        overflow: hidden !important;
    }

    /* ── Labels ── */
    [data-testid="stMainBlockContainer"] label p {
        color: #4B5563 !important;
        font-size: .73rem !important;
        font-weight: 700 !important;
        letter-spacing: .08em !important;
        text-transform: uppercase !important;
    }

    /* ── Inputs ── */
    [data-testid="stMainBlockContainer"] .stSelectbox > div > div,
    [data-testid="stMainBlockContainer"] .stTextInput  > div > div > input {
        background: #F9FAFB !important;
        border: 1.5px solid #D1D5DB !important;
        color: #111827 !important;
        border-radius: 10px !important;
        font-size: .88rem !important;
    }
    [data-testid="stMainBlockContainer"] .stSelectbox > div > div:focus-within,
    [data-testid="stMainBlockContainer"] .stTextInput  > div > div > input:focus {
        border-color: #1D4ED8 !important;
        box-shadow: 0 0 0 3px rgba(29,78,216,.14) !important;
        background: #fff !important;
    }

    /* ── Botón ingresar ── */
    [data-testid="stMainBlockContainer"] .stForm .stButton > button {
        width: 100% !important;
        background: linear-gradient(135deg, #1B3A5C 0%, #1D4ED8 100%) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 11px !important;
        height: 50px !important;
        font-size: .93rem !important;
        font-weight: 700 !important;
        letter-spacing: .05em !important;
        box-shadow: 0 6px 22px rgba(29,78,216,.42) !important;
        transition: all .18s ease !important;
        margin-top: 6px !important;
    }
    [data-testid="stMainBlockContainer"] .stForm .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 12px 32px rgba(29,78,216,.58) !important;
    }

    /* ── Alert ── */
    [data-testid="stMainBlockContainer"] .stAlert { border-radius:10px !important; }
    </style>
    """, unsafe_allow_html=True)

    # ── Orbs fijos en el fondo ─────────────────────────────────────────────────
    st.html("""
    <div style="position:fixed;top:0;left:0;width:100vw;height:100vh;
                pointer-events:none;overflow:hidden;z-index:0;">
      <!-- Orb azul rey top-right -->
      <div style="position:absolute;top:-18%;right:-10%;width:600px;height:600px;
           border-radius:50%;
           background:radial-gradient(circle,rgba(29,78,216,.30) 0%,transparent 62%);
           animation:driftA 11s ease-in-out infinite;"></div>
      <!-- Orb rojo bottom-left -->
      <div style="position:absolute;bottom:-20%;left:-8%;width:580px;height:580px;
           border-radius:50%;
           background:radial-gradient(circle,rgba(220,38,38,.22) 0%,transparent 60%);
           animation:driftB 14s ease-in-out infinite;"></div>
      <!-- Orb navy center -->
      <div style="position:absolute;top:30%;left:38%;width:300px;height:300px;
           border-radius:50%;
           background:radial-gradient(circle,rgba(27,58,92,.28) 0%,transparent 65%);
           animation:driftC 9s ease-in-out infinite;"></div>
      <!-- Partículas -->
      <div style="position:absolute;top:18%;left:12%;width:5px;height:5px;
           border-radius:50%;background:rgba(96,165,250,.55);
           animation:driftA 7s ease-in-out infinite;"></div>
      <div style="position:absolute;top:72%;right:14%;width:4px;height:4px;
           border-radius:50%;background:rgba(248,113,113,.50);
           animation:driftB 8s ease-in-out infinite 1.5s;"></div>
      <div style="position:absolute;top:45%;left:22%;width:3px;height:3px;
           border-radius:50%;background:rgba(147,197,253,.45);
           animation:driftC 10s ease-in-out infinite 2s;"></div>
    </div>
    """)

    # ── Layout split ───────────────────────────────────────────────────────────
    col_form, col_brand = st.columns([1, 1])

    # ──────────────────────────────────────────────────────────────────────────
    # PANEL IZQUIERDO — formulario
    # ──────────────────────────────────────────────────────────────────────────
    with col_form:
        st.html(f"""
        <div style="margin-bottom:30px;">
          {logo_form}
          <div style="margin-top:24px;font-size:1.5rem;font-weight:800;
                      color:#111827;font-family:'Segoe UI',sans-serif;
                      letter-spacing:-.01em;margin-bottom:4px;">
            Iniciar sesión
          </div>
          <div style="color:#9CA3AF;font-size:.79rem;">
            Accede con tus credenciales corporativas
          </div>
        </div>
        """)

        _uid_from_role = {v: k for k, v in _ROLES.items()}

        with st.form("login_form", border=False):
            puesto = st.selectbox("Puesto", options=list(_ROLES.values()), index=0)
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Ingresar al sistema", type="primary")

        if submitted:
            uid = _uid_from_role.get(puesto, "")
            usuario = autenticar(uid, password)
            if usuario:
                iniciar_sesion(usuario)
                st.rerun()
            else:
                st.error("Contraseña incorrecta. Verifica tus credenciales.")

        st.html("""
        <div style="margin-top:32px;padding-top:18px;border-top:1px solid #F3F4F6;
                    display:flex;align-items:center;justify-content:space-between;">
          <span style="color:#D1D5DB;font-size:.67rem;letter-spacing:.04em;">
            © 2026 TYASA · Uso interno exclusivo
          </span>
          <span style="background:#EFF6FF;color:#1D4ED8;font-size:.65rem;
                       font-weight:700;padding:2px 9px;border-radius:20px;
                       letter-spacing:.04em;border:1px solid #BFDBFE;">v2.1</span>
        </div>
        """)

    # ──────────────────────────────────────────────────────────────────────────
    # PANEL DERECHO — brand con logo animado
    # ──────────────────────────────────────────────────────────────────────────
    with col_brand:
        st.html(f"""
        <div style="
          height:100%; min-height:520px;
          background: linear-gradient(150deg,#0D1F3C 0%,#1B3A5C 45%,#1a2a4a 100%);
          padding: 40px 40px 44px;
          display: flex; flex-direction:column;
          justify-content:center; align-items:center;
          position: relative; overflow: hidden;
          border-left: 3px solid rgba(220,38,38,.60);
          text-align: center;
        ">
          <!-- Anillo decorativo top-right -->
          <div style="
            position:absolute; top:-90px; right:-90px;
            width:320px; height:320px; border-radius:50%;
            border: 2px solid rgba(29,78,216,.25);
            animation: rotateSlow 30s linear infinite;
          "></div>
          <div style="
            position:absolute; top:-60px; right:-60px;
            width:220px; height:220px; border-radius:50%;
            border: 1.5px solid rgba(220,38,38,.20);
            animation: rotateSlow 20s linear infinite reverse;
          "></div>

          <!-- Blob difuso bottom-left -->
          <div style="
            position:absolute; bottom:-100px; left:-80px;
            width:380px; height:380px; border-radius:50%;
            background: radial-gradient(circle, rgba(220,38,38,.18) 0%, transparent 65%);
            animation: driftB 12s ease-in-out infinite;
          "></div>

          <!-- Línea acento roja vertical izquierda -->
          <div style="
            position:absolute; left:0; top:15%; bottom:15%;
            width:3px;
            background:linear-gradient(180deg,transparent,#DC2626,transparent);
            border-radius:2px;
          "></div>

          <!-- CONTENIDO centrado -->
          <div style="position:relative; z-index:1; width:100%;">

            <!-- Logo grande centrado, ocupa casi todo el ancho -->
            <div style="
              width:100%; display:flex;
              justify-content:center; align-items:center;
              margin-bottom:36px;
              padding: 0 16px;
            ">
              {logo_brand}
            </div>

            <!-- Separador -->
            <div style="
              width:60px; height:2px; margin:0 auto 24px;
              background:linear-gradient(90deg,transparent,#DC2626,transparent);
              border-radius:2px;
            "></div>

            <!-- Texto -->
            <div style="
              color:#fff; font-size:1.55rem; font-weight:800;
              font-family:'Segoe UI',sans-serif;
              line-height:1.3; letter-spacing:-.01em;
              margin-bottom:12px;
            ">Bienvenido a TYASA BI</div>

            <div style="
              color:rgba(255,255,255,.55);
              font-size:.82rem; line-height:1.65;
              max-width:280px; margin:0 auto 32px;
            ">
              Plataforma de Inteligencia Comercial para el análisis y toma
              de decisiones del negocio siderúrgico.
            </div>

            <!-- Badge -->
            <div style="
              display:inline-flex; align-items:center; gap:10px;
              background:rgba(255,255,255,.07);
              border:1px solid rgba(255,255,255,.12);
              border-radius:10px; padding:10px 18px;
            ">
              <div style="
                width:8px; height:8px; border-radius:50%;
                background:#DC2626;
                box-shadow:0 0 8px rgba(220,38,38,.70);
              "></div>
              <span style="color:rgba(255,255,255,.65);font-size:.75rem;
                           letter-spacing:.06em;font-weight:600;">
                SISTEMA ACTIVO
              </span>
            </div>
          </div>
        </div>
        """)
