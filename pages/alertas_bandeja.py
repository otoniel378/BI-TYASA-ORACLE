"""
alertas_bandeja.py — Bandeja única de alertas de todo el sistema (core/alertas.py).
Prioridad alta / media / informativa, filtros por prioridad y área, y botón para
ir a la página donde se revisa cada alerta.
"""

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import html

import pandas as pd
import streamlit as st

from config import COLORS
from core.alertas import PRIORIDADES, alertas_vigentes
from core.auth import get_usuario
from core.components.kpi_cards import render_kpi_row, seccion_titulo

ESTILO = {
    "alta":  ("Alta", COLORS["danger"], "#FEF2F2"),
    "media": ("Media", "#D97706", "#FFFBEB"),
    "info":  ("Informativa", COLORS["secondary"], "#F1F5F9"),
}

_u = get_usuario()
_areas = tuple(_u.areas_permitidas) if _u and _u.areas_permitidas else ()
df = alertas_vigentes(_areas)

seccion_titulo("Bandeja de alertas", "Lo que requiere atención, de todo el sistema")

conteo = df["prioridad"].value_counts()
render_kpi_row([{"label": f"Prioridad {ESTILO[p][0].lower()}", "value": int(conteo.get(p, 0))} for p in PRIORIDADES])

c1, c2 = st.columns(2)
with c1:
    prioridades = st.multiselect("Prioridad", list(PRIORIDADES), default=["alta", "media"],
                                 format_func=lambda p: ESTILO[p][0], key="bandeja_prioridad")
with c2:
    areas = sorted(df["area"].unique()) if not df.empty else []
    areas_sel = st.multiselect("Área", areas, default=areas, key="bandeja_area")

vista = df[df["prioridad"].isin(prioridades) & df["area"].isin(areas_sel)] if not df.empty else df
if vista.empty:
    st.success("Sin alertas con estos filtros.")

for i, a in vista.reset_index(drop=True).iterrows():
    nombre, color, fondo = ESTILO[a["prioridad"]]
    fecha = f" · {pd.Timestamp(a['fecha']):%d/%m/%Y}" if pd.notna(a["fecha"]) else ""
    col_txt, col_btn = st.columns([6, 1])
    with col_txt:
        st.html(f"""
        <div style="background:{fondo};border-left:4px solid {color};border-radius:8px;padding:10px 14px;">
          <div style="font-size:11px;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:.04em;">
            {nombre} · {html.escape(a['area'])} · {html.escape(a['fuente'])}{fecha}</div>
          <div style="font-size:14px;font-weight:700;color:{COLORS['text']};margin-top:2px;">{html.escape(a['titulo'])}</div>
          <div style="font-size:12.5px;color:{COLORS['text_light']};margin-top:2px;">{html.escape(a['detalle'] or '')}</div>
        </div>""")
    with col_btn:
        destino = a["destino"]
        if isinstance(destino, tuple) and st.button("Ver", key=f"bandeja_ir_{i}_{a['clave']}", width="stretch"):
            seccion, subseccion, modulo = destino
            st.session_state.nav_seccion = seccion
            st.session_state.nav_subseccion = subseccion
            if modulo:
                st.session_state.nav_modulo_planos = modulo
            st.rerun()

st.caption("Se actualiza cada 10 minutos con lo vigente en Oracle; una alerta desaparece cuando deja de cumplirse.")
