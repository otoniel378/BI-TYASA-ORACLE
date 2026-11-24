"""
frescura.py — Indicador de "datos al día" en la barra lateral (app.py).

Muestra, para la sección abierta, la fecha del último dato de cada fuente que
usa (core/calidad_datos.FUENTES[*].secciones) con un punto verde / ámbar / rojo.
Solo consulta fechas máximas (rápido) y se cachea 10 minutos.
"""

from datetime import date

import pandas as pd
import streamlit as st

from core import calidad_datos

COLOR_ESTADO = {"ok": "#2E7D32", "aviso": "#D97706", "falla": "#C62828"}
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_MENSUALES = {f.nombre for f in calidad_datos.FUENTES if f.formato == "periodo"}


@st.cache_data(ttl=600, show_spinner=False)
def frescura_fuentes() -> pd.DataFrame:
    return calidad_datos.a_dataframe(calidad_datos.revisar_frescura(date.today()))


def _fila(r) -> str:
    color = COLOR_ESTADO.get(r["estado"], "#64748B")
    if pd.notna(r["fecha"]) and r["fuente"] in _MENSUALES:   # fecha = fin del mes: se muestra el mes
        m = pd.Timestamp(r["fecha"]) - pd.Timedelta(days=1)
        cuando = f"{_MESES[m.month - 1]} {m.year}"
    elif pd.notna(r["fecha"]):
        dias = (pd.Timestamp(date.today()) - pd.Timestamp(r["fecha"])).days
        cuando = f"{pd.Timestamp(r['fecha']):%d/%m/%Y}" if dias > 1 else ("hoy" if dias <= 0 else "ayer")
    else:
        cuando = "sin datos"
    return (f"<div style='display:flex;align-items:center;gap:7px;font-size:11.5px;color:#475569;margin:3px 0;'>"
            f"<span style='width:8px;height:8px;border-radius:50%;background:{color};flex-shrink:0;'></span>"
            f"<span style='flex:1;'>{r['fuente']}</span><span style='color:#64748B;'>{cuando}</span></div>")


def indicador_sidebar(seccion: str) -> None:
    """Llamar dentro de `with st.sidebar:`."""
    nombres = [f.nombre for f in calidad_datos.FUENTES if seccion in f.secciones]
    try:
        df = frescura_fuentes()
    except Exception:
        return
    if seccion == "inicio":   # resumen de todo el sistema
        n_falla, n_aviso = int((df["estado"] == "falla").sum()), int((df["estado"] == "aviso").sum())
        if n_falla + n_aviso == 0:
            txt, color = "Todas las fuentes al día", COLOR_ESTADO["ok"]
        else:
            partes = [f"{n_falla} sin actualizar" if n_falla else "", f"{n_aviso} atrasada{'s' if n_aviso > 1 else ''}" if n_aviso else ""]
            txt, color = " · ".join(p for p in partes if p), COLOR_ESTADO["falla" if n_falla else "aviso"]
        cuerpo = (f"<div style='display:flex;align-items:center;gap:7px;font-size:11.5px;color:#475569;'>"
                  f"<span style='width:8px;height:8px;border-radius:50%;background:{color};'></span>{txt}</div>")
    else:
        sub = df[df["fuente"].isin(nombres)]
        if sub.empty:
            return
        cuerpo = "".join(_fila(r) for _, r in sub.set_index("fuente").loc[[n for n in nombres if n in set(sub["fuente"])]]
                         .reset_index().iterrows())
    st.html(f"<div style='margin-top:6px;'><div style='font-size:10.5px;font-weight:700;color:#94A3B8;"
            f"letter-spacing:.06em;margin-bottom:4px;'>DATOS AL DÍA</div>{cuerpo}</div>")
