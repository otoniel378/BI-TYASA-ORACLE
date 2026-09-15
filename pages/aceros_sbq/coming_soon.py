"""
coming_soon.py — Aceros SBQ — PROXIMO
"""

import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
from config import COLORS

st.markdown(
    f"""
    <div style='text-align:center;padding:60px 20px;'>

        <h2 style='color:{COLORS["primary"]};'>Aceros SBQ</h2>
        <p style='color:{COLORS["neutral"]};font-size:1.1rem;max-width:500px;margin:0 auto 24px;'>
            Esta area sera desarrollada por el equipo de <b>Aceros SBQ</b>.
            La plataforma esta lista para recibir los modulos de analisis
            cuando el equipo comience su desarrollo.
        </p>
        <div style='
            background:#F3F4F6;
            border:1px solid #D1D5DB;
            border-radius:8px;
            padding:16px 24px;
            display:inline-block;
            color:{COLORS["neutral"]};
            font-weight:600;
        '>Proximo</div>
    </div>
    """,
    unsafe_allow_html=True,
)
