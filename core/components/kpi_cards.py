"""
kpi_cards.py — Tarjetas KPI ejecutivas reutilizables.
Renderiza metricas con formato corporativo TYASA.
Compartido entre todas las areas.
"""

import streamlit as st
from typing import Union, Optional
from config import COLORS


def kpi_card(
    label: str,
    value: Union[str, float, int],
    delta: Optional[Union[str, float]] = None,
    delta_label: str = "",
    icon: str = "",
    suffix: str = "",
    prefix: str = "",
    help_text: Optional[str] = None,
) -> None:
    if isinstance(value, float):
        value_str = f"{prefix}{value:,.1f}{suffix}"
    elif isinstance(value, int):
        value_str = f"{prefix}{value:,}{suffix}"
    else:
        value_str = f"{prefix}{value}{suffix}"

    delta_html = ""
    if delta is not None:
        try:
            delta_num = float(delta)
            color = COLORS["success"] if delta_num >= 0 else COLORS["danger"]
            arrow = "▲" if delta_num >= 0 else "▼"
            delta_html = (
                f"<span style='color:{color};font-size:0.82rem;font-weight:600;'>"
                f"{arrow} {abs(delta_num):.1f}%"
                f"</span>"
                f"<span style='color:{COLORS['text_light']};font-size:0.78rem;'> {delta_label}</span>"
            )
        except (TypeError, ValueError):
            delta_html = f"<span style='color:{COLORS['neutral']};font-size:0.82rem;'>{delta}</span>"

    help_attr = f'title="{help_text}"' if help_text else ""

    st.markdown(
        f"""
        <div {help_attr} style='
            background:{COLORS["surface"]};
            border:1px solid #E5E7EB;
            border-left:4px solid {COLORS["primary"]};
            border-radius:8px;
            padding:16px 20px;
            margin-bottom:8px;
        '>
            <div style='
                color:{COLORS["text_light"]};
                font-size:0.78rem;
                font-weight:600;
                text-transform:uppercase;
                letter-spacing:0.05em;
                margin-bottom:4px;
            '>{icon} {label}</div>
            <div style='
                color:{COLORS["primary"]};
                font-size:1.8rem;
                font-weight:700;
                line-height:1.2;
                margin-bottom:4px;
            '>{value_str}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_row(kpis: list) -> None:
    cols = st.columns(len(kpis))
    for col, kpi in zip(cols, kpis):
        with col:
            kpi_card(
                label=kpi.get("label", ""),
                value=kpi.get("value", 0),
                delta=kpi.get("delta"),
                delta_label=kpi.get("delta_label", "vs mes anterior"),
                icon=kpi.get("icon", ""),
                suffix=kpi.get("suffix", ""),
                prefix=kpi.get("prefix", ""),
                help_text=kpi.get("help_text"),
            )


def seccion_titulo(titulo: str, subtitulo: str = "") -> None:
    sub_html = (
        f"<p style='color:{COLORS['text_light']};font-size:0.85rem;margin:2px 0 0 0;'>{subtitulo}</p>"
        if subtitulo else ""
    )
    st.html(
        f"<div style='margin:24px 0 12px 0;'>"
        f"<h3 style='color:{COLORS['primary']};margin:0;font-size:1.15rem;'>{titulo}</h3>"
        f"{sub_html}"
        f"</div>"
    )
