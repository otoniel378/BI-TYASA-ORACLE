"""
dashboard.py — Dashboard placeholder para especialistas de área.
Se muestra mientras su módulo específico está en desarrollo.
"""
import streamlit as st
from core.auth import cerrar_sesion, Usuario


_AREA_CONFIG = {
    "aceros_planos": {
        "nombre": "Aceros Planos",
        "icono": "🔩",
        "color": "#1D4ED8",
        "color_light": "#DBEAFE",
        "modulos": [
            ("📊", "Resumen Ejecutivo", "Ventas, clientes activos y variación MoM"),
            ("👥", "Segmentación ABC", "Clasificación y análisis de clientes por volumen"),
            ("📈", "Series de Tiempo", "Evolución histórica y estacionalidad"),
            ("🔮", "Pronóstico de Demanda", "Modelos ETS, SARIMA y XGBoost"),
            ("🎯", "Mix de Productos", "Co-ocurrencia y oportunidades cross-sell"),
        ],
        "disponible": ["negros"],
        "desc_disponible": "Aceros Planos Negros — en desarrollo activo",
    },
    "aceros_largos": {
        "nombre": "Aceros Largos",
        "icono": "📏",
        "color": "#D97706",
        "color_light": "#FEF3C7",
        "modulos": [
            ("📊", "Dashboard Ejecutivo", "KPIs, tendencias y alertas del área"),
            ("🏦", "Macroeconomía", "Indicadores INEGI y variables de mercado"),
            ("🏭", "Sectores Productivos", "Análisis por sector: construcción, manufactura"),
            ("🌍", "Comercio Exterior", "Importaciones y exportaciones de aceros largos"),
        ],
        "disponible": [],
        "desc_disponible": "Módulo en preparación — próximamente disponible",
    },
    "aceros_sbq": {
        "nombre": "Aceros SBQ",
        "icono": "🔑",
        "color": "#DC2626",
        "color_light": "#FEE2E2",
        "modulos": [
            ("📊", "Dashboard Ejecutivo", "KPIs y métricas del área SBQ"),
            ("🎯", "Clientes Especiales", "Análisis de clientes de acero de calidad especial"),
            ("📈", "Series de Tiempo", "Evolución histórica de volúmenes SBQ"),
        ],
        "disponible": [],
        "desc_disponible": "Módulo en preparación — próximamente disponible",
    },
}


def render_dashboard(usuario: Usuario):
    area = usuario.areas_permitidas[0] if usuario.areas_permitidas else "aceros_planos"
    cfg = _AREA_CONFIG.get(area, _AREA_CONFIG["aceros_planos"])

    color     = cfg["color"]
    color_lt  = cfg["color_light"]
    icono     = cfg["icono"]
    nombre_area = cfg["nombre"]

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        # Avatar del usuario
        st.html(f"""
        <div style="text-align:center;padding:16px 0 12px;">
          <div style="
            width:64px;height:64px;border-radius:50%;
            background:{usuario.color};
            display:flex;align-items:center;justify-content:center;
            font-size:1.5rem;font-weight:800;color:#fff;
            margin:0 auto 10px;
            box-shadow:0 4px 14px {usuario.color}55;
            border:3px solid rgba(255,255,255,0.25);
          ">{usuario.iniciales}</div>
          <div style="font-weight:700;font-size:.90rem;color:#1B3A5C;">{usuario.cargo}</div>
        </div>
        """)

        st.markdown("---")
        st.markdown("### Área asignada")

        st.html(f"""
        <div style="
          background:{color_lt};border:2px solid {color}33;
          border-radius:12px;padding:12px 14px;margin-bottom:12px;
        ">
          <div style="font-size:1.4rem;">{icono}</div>
          <div style="font-weight:700;color:{color};font-size:.88rem;margin-top:4px;">
            {nombre_area}
          </div>
          <div style="font-size:.72rem;color:#6B7280;margin-top:2px;">
            {cfg['desc_disponible']}
          </div>
        </div>
        """)

        st.markdown("---")
        if st.button("🚪 Cerrar sesión", use_container_width=True, type="secondary"):
            cerrar_sesion()
            st.rerun()

    # ── Header principal ──────────────────────────────────────────────────────
    st.html(f"""
    <div style="
      background:linear-gradient(135deg,{color},#3B82F6);
      padding:20px 28px;
      border-radius:20px;
      margin-bottom:24px;
      display:flex;align-items:center;justify-content:space-between;
      box-shadow:0 8px 28px {color}40;
    ">
      <div style="display:flex;align-items:center;gap:16px;">
        <div style="
          width:56px;height:56px;border-radius:16px;
          background:rgba(255,255,255,.2);
          display:flex;align-items:center;justify-content:center;
          font-size:1.8rem;
          border:2px solid rgba(255,255,255,.25);
        ">{icono}</div>
        <div>
          <div style="color:#fff;font-size:1.4rem;font-weight:800;
                      font-family:'Segoe UI',sans-serif;letter-spacing:-.01em;">
            Bienvenido
          </div>
          <div style="color:rgba(255,255,255,.70);font-size:.80rem;margin-top:2px;">
            {usuario.cargo} · {nombre_area}
          </div>
        </div>
      </div>
      <div style="
        background:rgba(255,255,255,.15);border-radius:12px;
        padding:10px 18px;text-align:center;
        border:1px solid rgba(255,255,255,.20);
      ">
        <div style="color:rgba(255,255,255,.65);font-size:.65rem;
                    letter-spacing:.10em;text-transform:uppercase;font-weight:600;">
          Plataforma
        </div>
        <div style="color:#fff;font-size:.88rem;font-weight:700;margin-top:2px;">
          TYASA BI
        </div>
      </div>
    </div>
    """)

    # ── Estado del módulo ─────────────────────────────────────────────────────
    st.html(f"""
    <div style="
      background:linear-gradient(135deg,#F0F9FF,#E0F2FE);
      border:2px solid #BAE6FD;border-radius:16px;
      padding:20px 24px;margin-bottom:24px;
      display:flex;align-items:center;gap:16px;
    ">
      <div style="font-size:2.2rem;">🚧</div>
      <div>
        <div style="font-weight:700;color:#0C4A6E;font-size:1rem;">
          Módulo en desarrollo activo
        </div>
        <div style="color:#0369A1;font-size:.82rem;margin-top:4px;line-height:1.5;">
          Tu plataforma de análisis está siendo construida. Pronto tendrás acceso a
          dashboards completos con datos en tiempo real de tu área.
        </div>
      </div>
    </div>
    """)

    # ── Módulos próximos (cards) ──────────────────────────────────────────────
    st.markdown(f"#### {icono} Módulos de {nombre_area}")
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    cols = st.columns(min(len(cfg["modulos"]), 3))
    for i, (mod_icon, mod_nombre, mod_desc) in enumerate(cfg["modulos"]):
        disponible = i == 0 and len(cfg["disponible"]) > 0
        with cols[i % len(cols)]:
            estado_badge = (
                f'<span style="background:#DCFCE7;color:#166534;font-size:.62rem;'
                f'font-weight:700;padding:2px 8px;border-radius:20px;'
                f'letter-spacing:.05em;">EN DESARROLLO</span>'
                if disponible else
                f'<span style="background:#F1F5F9;color:#64748B;font-size:.62rem;'
                f'font-weight:700;padding:2px 8px;border-radius:20px;'
                f'letter-spacing:.05em;">PRÓXIMAMENTE</span>'
            )
            borde = f"border:2px solid {color}33;" if disponible else "border:2px solid #E2E8F0;"
            bg    = f"background:{color_lt};" if disponible else "background:#F8FAFC;"

            st.html(f"""
            <div style="
              {bg}{borde}border-radius:16px;padding:18px;margin-bottom:12px;
              transition:all .2s ease;
            ">
              <div style="font-size:1.8rem;margin-bottom:8px;">{mod_icon}</div>
              <div style="font-weight:700;color:#1B3A5C;font-size:.88rem;
                          margin-bottom:4px;">{mod_nombre}</div>
              <div style="color:#6B7280;font-size:.75rem;line-height:1.45;
                          margin-bottom:10px;">{mod_desc}</div>
              {estado_badge}
            </div>
            """)

    # ── Sección de acceso a Mercado Global (todos pueden verla) ──────────────
    st.markdown("---")
    st.markdown("#### 🌐 Mercado Global")
    st.markdown(
        "<p style='color:#6B7280;font-size:.82rem;'>"
        "Tienes acceso al monitor de mercado siderúrgico global."
        "</p>",
        unsafe_allow_html=True,
    )

    col_a, col_b, col_c = st.columns(3)
    _mkt_items = [
        ("📡", "Monitor de Quiebres", "Alertas de quiebres estructurales en mercados clave"),
        ("🏭", "Monitor Siderúrgico", "Análisis de noticias + mañanera presidencial"),
        ("🌡️", "Sentimiento de Mercado", "Score IA del sentimiento en prensa especializada"),
    ]
    for col, (ic, tit, desc) in zip([col_a, col_b, col_c], _mkt_items):
        with col:
            st.html(f"""
            <div style="background:#F8FAFC;border:2px solid #E2E8F0;
                        border-radius:14px;padding:16px;text-align:center;">
              <div style="font-size:1.6rem;margin-bottom:6px;">{ic}</div>
              <div style="font-weight:700;color:#1B3A5C;font-size:.82rem;
                          margin-bottom:4px;">{tit}</div>
              <div style="color:#6B7280;font-size:.72rem;line-height:1.4;">{desc}</div>
            </div>
            """)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    if st.button("🌐 Ir al Monitor de Mercado Global", type="primary"):
        # Navegar al mercado (solo info, no tienen acceso completo aún)
        st.info("El acceso completo al mercado global estará disponible con tu módulo.")
