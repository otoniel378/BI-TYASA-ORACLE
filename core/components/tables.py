"""
tables.py — Tablas colapsables y exportables a Excel.
Las tablas aparecen dentro de un expander (colapsado por defecto)
para mantener el dashboard compacto sin perder la funcionalidad.
"""

import io
import streamlit as st
import pandas as pd
from config import COLORS


def tabla_ejecutiva(
    df: pd.DataFrame,
    titulo: str = "",
    height: int = 320,
    col_formatos: dict | None = None,
    key: str = "tabla",
) -> None:
    if df is None or df.empty:
        st.info("Sin datos para mostrar.")
        return

    df_display = df.copy()
    if col_formatos:
        for col, fmt in col_formatos.items():
            if col in df_display.columns:
                try:
                    df_display[col] = df_display[col].apply(
                        lambda v: fmt.format(v) if pd.notna(v) else ""
                    )
                except Exception:
                    pass

    label = titulo if titulo else "Ver tabla de datos"
    with st.expander(label, expanded=False):
        st.dataframe(df_display, height=height, width="stretch", hide_index=True)
        _boton_descarga(df, key=key)


def _boton_descarga(df: pd.DataFrame, key: str = "export", label: str = "Exportar Excel") -> None:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Datos")
    buffer.seek(0)

    st.download_button(
        label=label,
        data=buffer,
        file_name=f"{key}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"dl_{key}",
    )


def tabla_clasificacion_abc(df_abc: pd.DataFrame, key: str = "abc") -> None:
    if df_abc.empty:
        st.info("Sin datos para clasificación ABC.")
        return

    col_formatos = {
        "PESO_TON": "{:,.1f}",
        "PCT": "{:.2f}%",
        "PCT_ACUM": "{:.2f}%",
    }

    df_display = df_abc.copy()
    for col, fmt in col_formatos.items():
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda v: fmt.format(v) if pd.notna(v) else ""
            )

    with st.expander("Clasificación ABC — detalle", expanded=False):
        st.dataframe(df_display, height=320, width="stretch", hide_index=True)
        _boton_descarga(df_abc, key=key, label="Exportar ABC")


def tabla_metricas(metricas: dict, titulo: str = "Métricas del modelo") -> None:
    if not metricas:
        return

    cols = st.columns(len(metricas))
    for col, (nombre, valor) in zip(cols, metricas.items()):
        with col:
            st.markdown(
                f"""
                <div style="
                    background:#FFFFFF;border:1px solid #DDE3EC;
                    border-top:3px solid #2563EB;border-radius:4px;
                    padding:9px 12px;text-align:center;
                ">
                    <div style="color:#64748B;font-size:0.62rem;font-weight:700;
                                text-transform:uppercase;letter-spacing:0.07em;">{nombre}</div>
                    <div style="color:#0F172A;font-size:1.2rem;font-weight:700;
                                line-height:1.2;margin-top:3px;">{valor}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
