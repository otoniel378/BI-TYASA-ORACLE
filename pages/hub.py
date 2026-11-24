"""
hub.py — Pagina de bienvenida y vision general del proyecto TYASA BI.
Muestra el estado de cada area y sus modulos.
"""

import os
import sys
import streamlit as st

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from config import COLORS, APP_NAME, APP_SUBTITLE, AREAS

def main():
    """Funcion principal para compatibilidad con app.py"""
    render()

def _contador_alertas():
    """Resumen de la bandeja de alertas (core/alertas.py) con liga a ella."""
    try:
        from core.alertas import alertas_vigentes
        df = alertas_vigentes()
    except Exception:
        return
    altas, medias = int((df["prioridad"] == "alta").sum()), int((df["prioridad"] == "media").sum())
    color = "#C62828" if altas else ("#D97706" if medias else "#2E7D32")
    texto = (f"<b>{altas}</b> alertas de prioridad alta · <b>{medias}</b> de prioridad media"
             if altas or medias else "Sin alertas que requieran atención")
    col_t, col_b = st.columns([5, 1])
    with col_t:
        st.html(f"""<div style="border-left:4px solid {color};background:#F8FAFC;border-radius:8px;
                    padding:10px 14px;font-size:14px;color:#1F2937;">{texto}</div>""")
    with col_b:
        if st.button("Ver alertas", key="hub_ver_alertas", width="stretch"):
            st.session_state.nav_seccion = "inicio"
            st.session_state.nav_subseccion = "alertas"
            st.rerun()


def render():
    """Render del contenido del hub"""
    col1, col2 = st.columns([5, 1])
    with col1:
        st.markdown(
            f"<h2 style='color:{COLORS['primary']};margin-bottom:4px;'>Bienvenido a {APP_NAME}</h2>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='color:#6B7280;'>Selecciona un modulo en el menu lateral para comenzar el analisis.</p>",
            unsafe_allow_html=True,
        )

    _contador_alertas()

    st.divider()

    st.markdown(
        f"<h3 style='color:{COLORS['primary']};'>Estado del Proyecto</h3>",
        unsafe_allow_html=True,
    )

    STATUS_BADGE = {
        "activo": ("<span style='background:#E8F5E9;color:#2E7D32;padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;'>Activo</span>", "#2E7D32"),
        "en_desarrollo": ("<span style='background:#FFF3E0;color:#F57C00;padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;'>En Desarrollo</span>", "#F57C00"),
        "proximo": ("<span style='background:#F3F4F6;color:#6B7280;padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;'>Proximo</span>", "#6B7280"),
    }

    st.markdown(f"<h4 style='color:{COLORS['primary']};margin-top:24px;'>Aceros Planos</h4>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    subsecciones_ap = [
        ("negros", "Aceros Negros", "activo", ["Resumen Ejecutivo", "Segmentacion Clientes", "Series de Tiempo", "Forecasting", "Mix de Productos"]),
        ("galvanizados", "Aceros Galvanizados", "en_desarrollo", []),
        ("formados", "Aceros Formados", "en_desarrollo", []),
    ]

    for col, (key, nombre, status, modulos) in zip([col1, col2, col3], subsecciones_ap):
        badge, border_color = STATUS_BADGE[status]
        modulos_html = "".join(
            f"<li style='font-size:0.82rem;color:{COLORS['text_light']};margin:2px 0;'>{m}</li>"
            for m in modulos
        ) if modulos else f"<li style='font-size:0.82rem;color:{COLORS['text_light']};font-style:italic;'>En construccion...</li>"

        with col:
            st.markdown(
                f"""
                <div style='background:{COLORS["surface"]};border:1px solid #E5E7EB;border-top:4px solid {border_color};border-radius:8px;padding:18px 16px;min-height:200px;'>
                    <div style='font-size:1.1rem;font-weight:700;color:{COLORS["primary"]};margin-bottom:6px;'>{nombre}</div>
                    {badge}
                    <ul style='margin-top:12px;padding-left:18px;'>{modulos_html}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(f"<h4 style='color:{COLORS['primary']};margin-top:28px;'>Otras Areas</h4>", unsafe_allow_html=True)
    col4, col5, _ = st.columns(3)

    otras = [
        (col4, "Aceros Largos", "Proximo - Pendiente de desarrollo por el equipo."),
        (col5, "Aceros SBQ", "Proximo - Pendiente de desarrollo por el equipo."),
    ]

    for col, titulo, desc in otras:
        with col:
            st.markdown(
                f"""
                <div style='background:{COLORS["background"]};border:1px dashed #D1D5DB;border-radius:8px;padding:18px 16px;min-height:120px;'>
                    <div style='font-size:1.1rem;font-weight:700;color:{COLORS["neutral"]};margin-bottom:8px;'>{titulo}</div>
                    <p style='font-size:0.83rem;color:{COLORS["text_light"]};'>{desc}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()
    st.markdown(
        f"<div style='text-align:center;color:{COLORS['text_light']};font-size:0.78rem;padding:16px 0;'>{APP_NAME} - {APP_SUBTITLE}</div>",
        unsafe_allow_html=True,
    )

if __name__ == "__main__":
    main()