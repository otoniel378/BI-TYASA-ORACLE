"""
mercado/snice/vistas_aranceles.py — Pestaña "Aranceles" de Comercio Exterior
(pages/mercado/07_comercio_exterior.py): arancel base por fracción propia de
TYASA (capa 1, SNICE/TIGIE — scripts/cargar_tigie_base_oracle.py) y qué le ha
aplicado el DOF desde entonces (capa 2 — scripts/monitor_dof.py), para que
"qué arancel le toca a cada fracción y qué le cambió" se vea en el dashboard
y no solo en Oracle o en un reporte aparte.
"""

import pandas as pd
import streamlit as st

from config import COLORS
from core.components.kpi_cards import render_kpi_row
from core.components.charts import estructura_100

from mercado.snice.loaders_aranceles import (
    load_tigie_tyasa,
    load_fuente_tigie,
    load_medidas_tyasa,
    load_alertas_dof_relevantes,
)

# Las 3 divisiones oficiales de TYASA (CLAUDE.md) — "Derivados" y
# "Semiterminados" son categorías de respaldo del catálogo (insumos/subproductos,
# no una división en sí) y se agrupan en "Otros / insumos" para no confundirlas
# con una cuarta división que no existe.
_DIVISIONES = ["Aceros Planos", "Aceros Largos", "Aceros SBQ"]
_OTROS_LINEA = "Otros / insumos"

_IMPACTO_COLORES = {
    "alto":  ("#DC2626", "#FEE2E2"),
    "medio": ("#D97706", "#FEF3C7"),
    "bajo":  ("#64748B", "#F1F5F9"),
}


def _linea_dashboard(linea: str) -> str:
    return linea if linea in _DIVISIONES else _OTROS_LINEA


def _igi_bucket(igi: str) -> str:
    igi = (igi or "").strip()
    if not igi or igi.upper().startswith("EX"):
        return "Exento"
    return f"{igi}%"


def _badge(texto: str, color: str, bg: str) -> str:
    return (
        f"<span style='font-size:0.66rem;font-weight:700;color:{color};background:{bg};"
        f"padding:3px 10px;border-radius:20px;white-space:nowrap;'>{texto}</span>"
    )


def _card_wrap(filas_html: str, vacio_texto: str) -> str:
    return filas_html or f"<p style='color:{COLORS['text_light']};font-size:0.85rem;padding:4px 0;'>{vacio_texto}</p>"


def _fila_medida(r) -> str:
    pais_html = f" · {r.pais_origen}" if r.pais_origen else ""
    vigencia_html = (
        f"<span style='color:{COLORS['text_light']};'> ({r.vigencia_desde or '—'} a {r.vigencia_hasta or '—'})</span>"
        if r.vigencia_desde or r.vigencia_hasta else ""
    )
    return f"""
    <div style="border-bottom:1px solid #F1F5F9;padding:11px 0;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <span style="font-size:0.82rem;font-weight:700;color:{COLORS['primary']};">{r.fraccion}</span>
        <span style="font-size:0.72rem;color:{COLORS['text_light']};white-space:nowrap;">{r.fecha_dof}</span>
      </div>
      <div style="margin-top:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        {_badge(r.tipo_medida, COLORS['secondary'], '#E8EFF5')}
        <span style="font-size:0.8rem;color:{COLORS['text']};font-weight:600;">{r.valor}{pais_html}</span>
        {vigencia_html}
      </div>
      <a href="{r.url}" target="_blank" style="font-size:0.72rem;color:{COLORS['secondary']};text-decoration:none;">Ver publicación en el DOF →</a>
    </div>"""


def _fila_alerta(r) -> str:
    color, bg = _IMPACTO_COLORES.get((r.impacto or "").lower(), _IMPACTO_COLORES["bajo"])
    frac_html = (
        f"<div style='margin-top:5px;font-size:0.72rem;color:{COLORS['text_light']};'>Fracciones TYASA citadas: <b>{r.fracciones_tyasa}</b></div>"
        if r.fracciones_tyasa else ""
    )
    return f"""
    <div style="border-bottom:1px solid #F1F5F9;padding:11px 0;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <div style="min-width:0;">
          {_badge(f"Impacto {r.impacto}", color, bg)}
          <span style="font-size:0.74rem;color:{COLORS['text_light']};margin-left:8px;">{(r.dependencia or '').title()}</span>
        </div>
        <span style="font-size:0.72rem;color:{COLORS['text_light']};white-space:nowrap;">{r.fecha_dof}</span>
      </div>
      <div style="margin-top:6px;font-size:0.82rem;color:{COLORS['text']};">{r.resumen}</div>
      {frac_html}
      <a href="{r.url}" target="_blank" style="font-size:0.72rem;color:{COLORS['secondary']};text-decoration:none;">Ver publicación en el DOF →</a>
    </div>"""


def _card_open(titulo: str, subtitulo: str = "") -> str:
    sub = f"<p style='margin:0 0 10px;font-size:0.8rem;color:{COLORS['text_light']};'>{subtitulo}</p>" if subtitulo else "<div style='height:6px'></div>"
    return (
        f"<div style='background:{COLORS['surface']};border:1px solid #E5E7EB;border-radius:14px;"
        f"padding:18px 20px;height:100%;'>"
        f"<p style='margin:0 0 3px;font-size:0.96rem;font-weight:700;color:{COLORS['primary']};'>{titulo}</p>"
        f"{sub}"
    )


_CARD_CLOSE = "</div>"


def render_aranceles_tab():
    tigie_df = load_tigie_tyasa()

    if tigie_df.empty:
        st.info(
            "Todavía no hay arancel base cargado. Corre "
            "`python scripts/cargar_tigie_base_oracle.py` para la primera carga "
            "(ver scripts/setup_tigie_base_oracle.py)."
        )
        return

    fuente = load_fuente_tigie()
    medidas_df = load_medidas_tyasa()
    alertas_df = load_alertas_dof_relevantes()

    tigie_df["linea_dashboard"] = tigie_df["linea_tyasa"].apply(_linea_dashboard)
    n_con_medida = medidas_df["fraccion"].nunique() if not medidas_df.empty else 0

    st.caption(
        "Arancel general (TIGIE) por fracción propia de TYASA + lo que el DOF le ha "
        "aplicado desde entonces (cuotas compensatorias, Regla 8a, TLC) — fracción y "
        "arancel, los dos monitoreados juntos."
    )

    render_kpi_row([
        {"label": "Fracciones con arancel base", "value": len(tigie_df)},
        {"label": "Con medida DOF registrada", "value": n_con_medida},
        {"label": "Alertas DOF relevantes (histórico)", "value": len(alertas_df)},
        {"label": "Arancel base vigente desde", "value": fuente or "N/D"},
    ])

    st.divider()

    col_a, col_b = st.columns([1.5, 1])

    with col_a:
        df_graf = tigie_df[tigie_df["linea_dashboard"].isin(_DIVISIONES)].copy()
        df_graf["igi_bucket"] = df_graf["igi"].apply(_igi_bucket)
        df_graf["conteo"] = 1
        fig = estructura_100(
            df_graf, fila="linea_dashboard", categoria="igi_bucket", valor="conteo",
            titulo="Composición del arancel base (IGI) por línea TYASA",
            orden_filas=_DIVISIONES, height=230,
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption(
            "% de fracciones de cada línea en cada tasa de importación (IGI) — "
            "exportación (IGE) está exenta en el 100% del catálogo de TYASA."
        )

    with col_b:
        html = _card_open("Alertas DOF recientes", "Relevantes para TYASA, cualquier fracción del acero")
        if alertas_df.empty:
            html += _card_wrap("", "Sin alertas relevantes registradas todavía.")
        else:
            html += "".join(_fila_alerta(r) for r in alertas_df.head(4).itertuples())
        html += _CARD_CLOSE
        st.html(html)

    st.divider()

    # ── Filtro por línea + detalle por fracción ─────────────────────────────
    linea_sel = st.selectbox(
        "Ver fracciones de:",
        ["Todas las líneas"] + _DIVISIONES + ([_OTROS_LINEA] if (tigie_df["linea_dashboard"] == _OTROS_LINEA).any() else []),
        key="aranceles_linea_sel",
    )
    tigie_filtrado = tigie_df if linea_sel == "Todas las líneas" else tigie_df[tigie_df["linea_dashboard"] == linea_sel]

    ultima_medida = (
        medidas_df.sort_values("fecha_dof", ascending=False).drop_duplicates("fraccion")
        if not medidas_df.empty else pd.DataFrame(columns=["fraccion", "tipo_medida", "valor", "fecha_dof"])
    )
    conteo_medidas = medidas_df.groupby("fraccion").size() if not medidas_df.empty else pd.Series(dtype=int)

    tabla = tigie_filtrado.copy()
    tabla["medidas_dof"] = tabla["fraccion"].map(conteo_medidas).fillna(0).astype(int)
    tabla = tabla.merge(
        ultima_medida[["fraccion", "tipo_medida", "valor", "fecha_dof"]].rename(columns={
            "tipo_medida": "ultima_medida_tipo", "valor": "ultima_medida_valor", "fecha_dof": "ultima_medida_fecha",
        }),
        on="fraccion", how="left",
    )
    tabla[["ultima_medida_tipo", "ultima_medida_valor", "ultima_medida_fecha"]] = (
        tabla[["ultima_medida_tipo", "ultima_medida_valor", "ultima_medida_fecha"]].fillna("—")
    )
    tabla["igi"] = tabla["igi"].apply(_igi_bucket)
    tabla["ige"] = tabla["ige"].apply(_igi_bucket)
    tabla = tabla.rename(columns={
        "fraccion": "Fracción", "descripcion": "Descripción", "igi": "IGI (import.)", "ige": "IGE (export.)",
        "linea_tyasa": "Línea", "medidas_dof": "Medidas DOF", "ultima_medida_tipo": "Última medida",
        "ultima_medida_valor": "Valor", "ultima_medida_fecha": "Fecha",
    })
    st.dataframe(
        tabla[["Fracción", "Descripción", "Línea", "IGI (import.)", "IGE (export.)", "Medidas DOF", "Última medida", "Valor", "Fecha"]],
        hide_index=True, width="stretch", height=360,
    )

    st.divider()

    # ── Historial de medidas arancelarias (DOF), cronológico ────────────────
    fracciones_filtro = set(tigie_filtrado["fraccion"]) if linea_sel != "Todas las líneas" else None
    medidas_mostrar = (
        medidas_df[medidas_df["fraccion"].isin(fracciones_filtro)] if fracciones_filtro is not None else medidas_df
    )
    subtitulo_medidas = (
        "Cuotas compensatorias, Regla 8a, TLC o cambios de arancel general detectados por el monitor del DOF"
        + (f" — línea {linea_sel}" if linea_sel != "Todas las líneas" else "")
    )
    html = _card_open(f"Historial de medidas arancelarias ({len(medidas_mostrar)})", subtitulo_medidas)
    if medidas_mostrar.empty:
        html += _card_wrap(
            "", "Sin medidas registradas todavía para este filtro — es normal, estos cambios son poco "
            "frecuentes. El monitor del DOF (scripts/monitor_dof.py) las va acumulando aquí automáticamente "
            "conforme ocurren."
        )
    else:
        html += "".join(_fila_medida(r) for r in medidas_mostrar.itertuples())
    html += _CARD_CLOSE
    st.html(html)
