"""
coming_soon.py — Aceros Planos Galvanizados — EN DESARROLLO
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
        <h2 style='color:{COLORS["primary"]};'>Aceros Planos Galvanizados</h2>
        <p style='color:{COLORS["neutral"]};font-size:1.1rem;max-width:500px;margin:0 auto 24px;'>
            Este modulo esta actualmente en desarrollo.
            Se integra al area de <b>Aceros Planos</b> y seguira la misma estructura
            que Aceros Negros.
        </p>
        <div style='
            background:#FFF3E0;
            border:1px solid #F57C00;
            border-radius:8px;
            padding:16px 24px;
            display:inline-block;
            color:#F57C00;
            font-weight:600;
        '>En Desarrollo</div>
    </div>
    """,
    unsafe_allow_html=True,
)
