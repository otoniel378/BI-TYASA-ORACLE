"""
estado_datos.py — Estado de los datos (INICIO → Estado de los datos).
Cuándo se actualizó cada fuente y qué reglas de calidad se cumplen (core/calidad_datos.py).
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
from core.calidad_datos import FUENTES, estado_datos
from core.components.kpi_cards import render_kpi_row, seccion_titulo

ESTILO = {
    "falla": ("Requiere acción", COLORS["danger"], "#FEF2F2"),
    "aviso": ("Revisar", "#D97706", "#FFFBEB"),
    "ok":    ("Correcto", COLORS["success"], "#F0FDF4"),
}

df = estado_datos()
seccion_titulo("Estado de los datos", "Qué tan recientes y confiables son los datos de cada fuente")

fres = df[df["tipo"] == "frescura"]
reglas = df[df["tipo"] == "contenido"]
render_kpi_row([
    {"label": "Fuentes al día", "value": f"{int((fres['estado'] == 'ok').sum())} de {len(fres)}"},
    {"label": "Fuentes atrasadas", "value": int((fres["estado"] != "ok").sum())},
    {"label": "Reglas que se cumplen", "value": f"{int((reglas['estado'] == 'ok').sum())} de {len(reglas)}"},
])

st.markdown("#### Última actualización por fuente")
orden = {f.nombre: i for i, f in enumerate(FUENTES)}
tabla = fres.assign(_o=fres["fuente"].map(orden)).sort_values("_o")
filas = []
for _, r in tabla.iterrows():
    nombre, color, fondo = ESTILO[r["estado"]]
    filas.append(f"""<tr>
      <td style="padding:7px 10px;font-weight:600;color:{COLORS['text']};">{html.escape(r['fuente'])}</td>
      <td style="padding:7px 10px;color:{COLORS['text_light']};">{html.escape(r['detalle'])}</td>
      <td style="padding:7px 10px;"><span style="background:{fondo};color:{color};font-weight:700;font-size:11.5px;
          padding:2px 9px;border-radius:10px;white-space:nowrap;">{nombre}</span></td></tr>""")
st.html(f"""<table style="width:100%;border-collapse:collapse;font-size:13px;background:{COLORS['surface']};
           border:1px solid #E5E7EB;border-radius:8px;">{''.join(filas)}</table>""")

st.markdown("#### Reglas de calidad")
for grupo, sub in reglas.groupby("grupo", sort=False):
    st.markdown(f"**{grupo}**")
    for _, r in sub.iterrows():
        nombre, color, fondo = ESTILO[r["estado"]]
        st.html(f"""
        <div style="background:{fondo};border-left:4px solid {color};border-radius:8px;padding:8px 14px;margin:4px 0;">
          <div style="font-size:13.5px;font-weight:700;color:{COLORS['text']};">{html.escape(r['regla'])}
            <span style="font-size:11px;color:{color};margin-left:6px;">{nombre}</span></div>
          <div style="font-size:12.5px;color:{COLORS['text_light']};">{html.escape(r['fuente'])} · {html.escape(r['detalle'])}</div>
        </div>""")

st.caption("Se revisa cada 10 minutos. Lo que no está correcto también aparece en la Bandeja de alertas.")
