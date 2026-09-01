"""
reportes.py — Generador de reportes descargables (Word + PDF) por indicador
o por grupo de indicadores INEGI. Incluye gráfica, estadísticas, comparación
anual, noticias relacionadas y (opcional) análisis IA ya generado en la página.
"""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors as rl_colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak,
)

from .loaders import INDICADORES_LABEL, GRUPOS_INEGI, load_serie, load_comparacion_anual
from .noticias_inegi import buscar_noticias_indicador
from mercado_noticias.analytics.ai_analysis import analizar_indicador_inegi_reporte

_NAVY  = RGBColor(0x1B, 0x3A, 0x5C)
_GREY  = RGBColor(0x47, 0x55, 0x69)
_NAVY_HEX = "#1B3A5C"
_MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# Traducción de niveles de alerta a lenguaje llano — sin jerga estadística
_ALERTA_DESC = {
    "Critico":  "Movimiento muy atípico — fuera de su comportamiento habitual",
    "Alto":     "Fuera de lo habitual — conviene dar seguimiento",
    "Moderado": "Ligera desviación de lo habitual",
    "Normal":   "Dentro de su comportamiento habitual",
}


def _hex_rgba(hex_color: str, alpha: float = 0.15) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _fmt_num(v) -> str:
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:.2f}M"
        if abs(f) >= 10_000:
            return f"{f:,.0f}"
        return f"{f:,.2f}"
    except Exception:
        return "—"


def _fmt_pct(v) -> str:
    try:
        f = float(v)
        return f"{f:+.1f}%"
    except Exception:
        return "—"


def _grupo_de_clave(clave: str) -> str:
    for gkey, g in GRUPOS_INEGI.items():
        if clave in g["claves"]:
            return gkey
    return ""


def _nivel_alerta(z) -> str:
    try:
        az = abs(float(z))
        if az > 2.5:
            return "Critico"
        if az > 1.5:
            return "Alto"
        if az > 1.0:
            return "Moderado"
    except Exception:
        pass
    return "Normal"


def _serie_to_list(df_serie: pd.DataFrame) -> list:
    if df_serie.empty:
        return []
    df_s = df_serie.sort_values("fecha").tail(12)
    out = []
    for _, r in df_s.iterrows():
        try:
            out.append((str(r["fecha"])[:7], float(r["valor"])))
        except Exception:
            pass
    return out


def _split_secciones(texto: str) -> list[tuple[str, str]]:
    """Parsea el texto de la IA en (título, cuerpo) según encabezados '## '."""
    secciones: list[tuple[str, str]] = []
    titulo = None
    buffer: list[str] = []
    for linea in (texto or "").splitlines():
        if linea.strip().startswith("## "):
            if titulo is not None:
                secciones.append((titulo, " ".join(buffer).strip()))
            titulo = linea.strip()[3:].strip()
            buffer = []
        elif linea.strip():
            buffer.append(linea.strip())
    if titulo is not None:
        secciones.append((titulo, " ".join(buffer).strip()))
    if not secciones and texto and texto.strip():
        secciones = [("Análisis", texto.strip())]
    return secciones


# ── Cálculo de estadísticas propias del reporte (auto-consistentes con periodos) ──
def _stats_from_serie(df_serie: pd.DataFrame) -> dict:
    if df_serie.empty:
        return {}
    df_s = df_serie.sort_values("fecha")
    vals = pd.to_numeric(df_s["valor"], errors="coerce")
    ult = float(vals.iloc[-1])
    prev = float(vals.iloc[-2]) if len(vals) >= 2 else None
    hace_12 = float(vals.iloc[-13]) if len(vals) >= 13 else None
    media = float(vals.mean())
    std = float(vals.std()) if len(vals) > 1 else 0.0
    z = ((ult - media) / std) if std else None
    return {
        "ult_fecha": str(df_s["fecha"].iloc[-1])[:7],
        "ult_valor": ult,
        "var_mom": ((ult - prev) / abs(prev) * 100) if prev else None,
        "var_yoy": ((ult - hace_12) / abs(hace_12) * 100) if hace_12 else None,
        "media": media,
        "std": std,
        "z_score": z,
        "alerta": _nivel_alerta(z),
    }


# ── Gráfica como PNG (vía Plotly + kaleido, tema claro para documentos) ─────────
def _chart_png(df_serie: pd.DataFrame, label: str, color: str, width=900, height=380) -> bytes:
    df_s = df_serie.sort_values("fecha")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_s["fecha"], y=df_s["valor"], mode="lines+markers", name=label,
        line=dict(color=color, width=2.5),
        marker=dict(size=4, color=color),
        fill="tozeroy", fillcolor=_hex_rgba(color, 0.15),
    ))
    fig.update_layout(
        template="plotly_white", width=width, height=height,
        margin=dict(l=55, r=25, t=20, b=45),
        showlegend=False, font=dict(size=13, color="#1B2A3A"),
        xaxis=dict(gridcolor="#E5E9F0", tickformat="%b %Y"),
        yaxis=dict(gridcolor="#E5E9F0"),
    )
    return fig.to_image(format="png", scale=2)


def _yoy_chart_png(comp: dict, label: str, color: str, width=900, height=380) -> bytes | None:
    if not comp or len(comp.get("anios", [])) < 2:
        return None
    anio_actual, anio_anterior = comp["anio_actual"], comp["anio_anterior"]
    series = comp["series"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_MESES, y=[series[anio_anterior].get(m) for m in range(1, 13)],
        mode="lines+markers", name=str(anio_anterior),
        line=dict(color="#94A3B8", width=2, dash="dot"), marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=_MESES, y=[series[anio_actual].get(m) for m in range(1, 13)],
        mode="lines+markers", name=str(anio_actual),
        line=dict(color=color, width=3), marker=dict(size=6),
    ))
    fig.update_layout(
        template="plotly_white", width=width, height=height,
        margin=dict(l=55, r=25, t=30, b=45),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        font=dict(size=13, color="#1B2A3A"),
        xaxis=dict(gridcolor="#E5E9F0"),
        yaxis=dict(gridcolor="#E5E9F0"),
    )
    return fig.to_image(format="png", scale=2)


# ── Recopilación de datos de un indicador ───────────────────────────────────────
def generar_datos_reporte(
    clave: str,
    periodos: int = 24,
    incluir_noticias: bool = True,
    max_noticias: int = 8,
    api_key: str | None = None,
    force_refresh_ia: bool = False,
) -> dict:
    gkey = _grupo_de_clave(clave)
    g = GRUPOS_INEGI.get(gkey, {})
    label = INDICADORES_LABEL.get(clave, clave)
    df_serie = load_serie(clave, periodos=periodos)
    stats = _stats_from_serie(df_serie)
    comp = load_comparacion_anual(clave) if g.get("freq") == "mensual" else {}
    noticias = buscar_noticias_indicador(clave, gkey, max_resultados=max_noticias) if incluir_noticias else []

    analisis_ia, analisis_error = None, None
    if api_key:
        try:
            r = analizar_indicador_inegi_reporte(
                clave=clave, label=label,
                group_label=g.get("label", gkey), group_desc=g.get("desc", ""),
                freq=g.get("freq", "mensual"),
                alerta=stats.get("alerta", "Normal"),
                ult_fecha=stats.get("ult_fecha", ""),
                ult_valor=stats.get("ult_valor"),
                var_mom=stats.get("var_mom"),
                var_yoy=stats.get("var_yoy"),
                media=stats.get("media"),
                comp=comp,
                valores_recientes=_serie_to_list(df_serie),
                noticias=noticias,
                api_key=api_key,
                force_refresh=force_refresh_ia,
            )
            analisis_ia = r.get("analisis") or None
            analisis_error = r.get("_error")
        except Exception as exc:
            analisis_error = str(exc)

    return {
        "clave": clave,
        "label": label,
        "grupo_key": gkey,
        "grupo_label": g.get("label", gkey),
        "grupo_desc": g.get("desc", ""),
        "color": g.get("color", _NAVY_HEX),
        "freq": g.get("freq", "mensual"),
        "df_serie": df_serie,
        "stats": stats,
        "comparacion": comp,
        "noticias": noticias,
        "analisis_ia": analisis_ia,
        "analisis_error": analisis_error,
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# WORD (.docx)
# ═══════════════════════════════════════════════════════════════════════════

def _docx_seccion_indicador(doc: Document, datos: dict):
    label, color = datos["label"], datos["color"]
    stats = datos["stats"]

    h = doc.add_heading(f"{label}", level=2)
    for run in h.runs:
        run.font.color.rgb = _NAVY

    p = doc.add_paragraph(
        f"Clave INEGI: {datos['clave']}  ·  Grupo: {datos['grupo_label']}  ·  "
        f"Frecuencia: {'mensual' if datos['freq'] == 'mensual' else 'anual'}"
    )
    p.runs[0].font.size = Pt(9)
    p.runs[0].font.color.rgb = _GREY

    if datos["grupo_desc"]:
        pd_ = doc.add_paragraph(datos["grupo_desc"])
        pd_.runs[0].font.size = Pt(9.5)
        pd_.runs[0].font.color.rgb = _GREY
        pd_.runs[0].italic = True

    if not datos["df_serie"].empty:
        png = _chart_png(datos["df_serie"], label, color)
        doc.add_picture(io.BytesIO(png), width=Inches(6.3))

    if stats:
        doc.add_paragraph().add_run("En resumen").bold = True
        table = doc.add_table(rows=1, cols=2)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text = "Métrica", "Valor"
        filas = [
            ("Dato más reciente", stats.get("ult_fecha", "—")),
            ("Valor actual", _fmt_num(stats.get("ult_valor"))),
            ("Vs. mes anterior", _fmt_pct(stats.get("var_mom"))),
            ("Vs. mismo mes del año anterior", _fmt_pct(stats.get("var_yoy"))),
            ("Promedio últimos 24 meses", _fmt_num(stats.get("media"))),
            ("Comportamiento", _ALERTA_DESC.get(stats.get("alerta"), _ALERTA_DESC["Normal"])),
        ]
        for k, v in filas:
            row = table.add_row().cells
            row[0].text, row[1].text = k, str(v)

    comp = datos.get("comparacion") or {}
    if comp and comp.get("yoy_ytd") is not None:
        png_yoy = _yoy_chart_png(comp, label, color)
        if png_yoy:
            doc.add_paragraph()
            doc.add_paragraph().add_run(
                f"Comparación {comp['anio_actual']} vs {comp['anio_anterior']} "
                f"(YTD {comp['meses_ytd']} meses: {_fmt_pct(comp['yoy_ytd'])})"
            ).bold = True
            doc.add_picture(io.BytesIO(png_yoy), width=Inches(6.3))

    if datos.get("analisis_ia"):
        doc.add_paragraph()
        h_an = doc.add_heading("Análisis y proyección — contexto TYASA", level=3)
        for run in h_an.runs:
            run.font.color.rgb = _NAVY
        for titulo_sec, cuerpo_sec in _split_secciones(datos["analisis_ia"]):
            p_tit = doc.add_paragraph()
            r_tit = p_tit.add_run(titulo_sec)
            r_tit.bold = True
            r_tit.font.color.rgb = _NAVY
            if cuerpo_sec:
                doc.add_paragraph(cuerpo_sec)
    elif datos.get("analisis_error"):
        doc.add_paragraph()
        nota = doc.add_paragraph(
            "Análisis y proyección no disponibles — configura GEMINI_API_KEY en el sistema para incluir esta sección."
        )
        nota.runs[0].italic = True
        nota.runs[0].font.color.rgb = _GREY

    noticias = datos.get("noticias") or []
    if noticias:
        doc.add_paragraph()
        doc.add_paragraph().add_run("Noticias relacionadas").bold = True
        for n in noticias[:8]:
            para = doc.add_paragraph(style="List Bullet")
            run = para.add_run(n.get("titulo", ""))
            run.bold = True
            fecha = n.get("fecha_pub", "")
            fuente = n.get("fuente", "")
            meta = "  ·  ".join(x for x in [fuente, fecha] if x)
            if meta:
                para.add_run(f"  ({meta})").italic = True


def generar_word_indicador(clave: str, periodos: int = 24, incluir_noticias: bool = True,
                            api_key: str | None = None) -> bytes:
    datos = generar_datos_reporte(clave, periodos, incluir_noticias, api_key=api_key)
    doc = Document()
    title = doc.add_heading("TYASA BI · Reporte de Indicador INEGI", level=1)
    for run in title.runs:
        run.font.color.rgb = _NAVY
    sub = doc.add_paragraph(f"Generado el {datos['generado']}")
    sub.runs[0].font.size = Pt(9)
    sub.runs[0].font.color.rgb = _GREY
    doc.add_paragraph()

    _docx_seccion_indicador(doc, datos)

    doc.add_paragraph()
    foot = doc.add_paragraph("Fuente: INEGI · Banco de Indicadores Económicos (BIE) · Sistema TYASA BI")
    foot.runs[0].font.size = Pt(8)
    foot.runs[0].font.color.rgb = _GREY

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def generar_word_grupo(grupo: str, periodos: int = 24, incluir_noticias: bool = True,
                        api_key: str | None = None) -> bytes:
    g = GRUPOS_INEGI.get(grupo, {})
    doc = Document()
    title = doc.add_heading("TYASA BI · Reporte de Grupo INEGI", level=1)
    for run in title.runs:
        run.font.color.rgb = _NAVY
    sub = doc.add_paragraph(f"{g.get('icon', '')} {g.get('label', grupo)}  ·  Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    sub.runs[0].font.size = Pt(10)
    sub.runs[0].font.color.rgb = _GREY
    if g.get("desc"):
        d = doc.add_paragraph(g["desc"])
        d.runs[0].italic = True
        d.runs[0].font.color.rgb = _GREY
    doc.add_paragraph()

    for i, clave in enumerate(g.get("claves", [])):
        datos = generar_datos_reporte(clave, periodos, incluir_noticias, api_key=api_key)
        _docx_seccion_indicador(doc, datos)
        if i < len(g["claves"]) - 1:
            doc.add_page_break()

    doc.add_paragraph()
    foot = doc.add_paragraph("Fuente: INEGI · Banco de Indicadores Económicos (BIE) · Sistema TYASA BI")
    foot.runs[0].font.size = Pt(8)
    foot.runs[0].font.color.rgb = _GREY

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# PDF (reportlab)
# ═══════════════════════════════════════════════════════════════════════════

_styles = getSampleStyleSheet()
_STYLE_TITLE = ParagraphStyle("TyasaTitle", parent=_styles["Heading1"], textColor=rl_colors.HexColor(_NAVY_HEX), fontSize=18)
_STYLE_H2 = ParagraphStyle("TyasaH2", parent=_styles["Heading2"], textColor=rl_colors.HexColor(_NAVY_HEX), fontSize=13, spaceBefore=14)
_STYLE_META = ParagraphStyle("TyasaMeta", parent=_styles["Normal"], textColor=rl_colors.HexColor("#475569"), fontSize=8.5)
_STYLE_BODY = ParagraphStyle("TyasaBody", parent=_styles["Normal"], fontSize=9.5, leading=14)
_STYLE_BULLET = ParagraphStyle("TyasaBullet", parent=_styles["Normal"], fontSize=9, leading=13, leftIndent=12)


def _pdf_flowables_indicador(datos: dict) -> list:
    flow = []
    flow.append(Paragraph(datos["label"], _STYLE_H2))
    flow.append(Paragraph(
        f"Clave INEGI: {datos['clave']} &nbsp;·&nbsp; Grupo: {datos['grupo_label']} &nbsp;·&nbsp; "
        f"Frecuencia: {'mensual' if datos['freq'] == 'mensual' else 'anual'}",
        _STYLE_META,
    ))
    if datos["grupo_desc"]:
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(datos["grupo_desc"], _STYLE_META))
    flow.append(Spacer(1, 8))

    if not datos["df_serie"].empty:
        png = _chart_png(datos["df_serie"], datos["label"], datos["color"], width=760, height=320)
        flow.append(RLImage(io.BytesIO(png), width=6.3 * inch, height=6.3 * inch * 320 / 760))
        flow.append(Spacer(1, 8))

    stats = datos["stats"]
    if stats:
        rows = [["Métrica", "Valor"], [
            "Dato más reciente", stats.get("ult_fecha", "—")], [
            "Valor actual", _fmt_num(stats.get("ult_valor"))], [
            "Vs. mes anterior", _fmt_pct(stats.get("var_mom"))], [
            "Vs. mismo mes del año anterior", _fmt_pct(stats.get("var_yoy"))], [
            "Promedio últimos 24 meses", _fmt_num(stats.get("media"))], [
            "Comportamiento", _ALERTA_DESC.get(stats.get("alerta"), _ALERTA_DESC["Normal"])],
        ]
        tbl = Table(rows, colWidths=[2.8 * inch, 3.5 * inch])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(_NAVY_HEX)),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#D0D5DD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F4F6F9")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        flow.append(tbl)
        flow.append(Spacer(1, 8))

    comp = datos.get("comparacion") or {}
    if comp and comp.get("yoy_ytd") is not None:
        png_yoy = _yoy_chart_png(comp, datos["label"], datos["color"], width=760, height=320)
        if png_yoy:
            flow.append(Paragraph(
                f"Comparación {comp['anio_actual']} vs {comp['anio_anterior']} "
                f"(YTD {comp['meses_ytd']} meses: {_fmt_pct(comp['yoy_ytd'])})",
                ParagraphStyle("TyasaBoldSmall", parent=_STYLE_BODY, fontSize=9.5, spaceBefore=4, spaceAfter=4),
            ))
            flow.append(RLImage(io.BytesIO(png_yoy), width=6.3 * inch, height=6.3 * inch * 320 / 760))
            flow.append(Spacer(1, 8))

    if datos.get("analisis_ia"):
        flow.append(Paragraph("Análisis y proyección — contexto TYASA", ParagraphStyle(
            "TyasaAnalisisH", parent=_STYLE_H2, fontSize=12, spaceBefore=6, spaceAfter=6,
        )))
        style_sec_titulo = ParagraphStyle(
            "TyasaSecTitulo", parent=_STYLE_BODY, fontSize=9.5, spaceBefore=6, spaceAfter=2,
            textColor=rl_colors.HexColor(_NAVY_HEX),
        )
        for titulo_sec, cuerpo_sec in _split_secciones(datos["analisis_ia"]):
            flow.append(Paragraph(f"<b>{titulo_sec}</b>", style_sec_titulo))
            if cuerpo_sec:
                flow.append(Paragraph(cuerpo_sec, _STYLE_BODY))
                flow.append(Spacer(1, 2))
    elif datos.get("analisis_error"):
        flow.append(Paragraph(
            "Análisis y proyección no disponibles — configura GEMINI_API_KEY en el sistema para "
            "incluir esta sección.",
            ParagraphStyle("TyasaNota", parent=_STYLE_META, fontSize=8.5, spaceBefore=6),
        ))

    noticias = datos.get("noticias") or []
    if noticias:
        flow.append(Paragraph("Noticias relacionadas", ParagraphStyle(
            "TyasaBoldSmall3", parent=_STYLE_BODY, fontSize=10, spaceBefore=6, spaceAfter=4,
        )))
        for n in noticias[:8]:
            meta = "  ·  ".join(x for x in [n.get("fuente", ""), n.get("fecha_pub", "")] if x)
            texto = f"<b>{n.get('titulo', '')}</b>"
            if meta:
                texto += f" <i>({meta})</i>"
            flow.append(Paragraph(f"• {texto}", _STYLE_BULLET))
    return flow


def generar_pdf_indicador(clave: str, periodos: int = 24, incluir_noticias: bool = True,
                           api_key: str | None = None) -> bytes:
    datos = generar_datos_reporte(clave, periodos, incluir_noticias, api_key=api_key)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    flow = [
        Paragraph("TYASA BI · Reporte de Indicador INEGI", _STYLE_TITLE),
        Paragraph(f"Generado el {datos['generado']}", _STYLE_META),
        Spacer(1, 12),
    ]
    flow += _pdf_flowables_indicador(datos)
    flow.append(Spacer(1, 14))
    flow.append(Paragraph("Fuente: INEGI · Banco de Indicadores Económicos (BIE) · Sistema TYASA BI", _STYLE_META))
    doc.build(flow)
    return buf.getvalue()


def generar_pdf_grupo(grupo: str, periodos: int = 24, incluir_noticias: bool = True,
                       api_key: str | None = None) -> bytes:
    g = GRUPOS_INEGI.get(grupo, {})
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    flow = [
        Paragraph("TYASA BI · Reporte de Grupo INEGI", _STYLE_TITLE),
        Paragraph(
            f"{g.get('icon', '')} {g.get('label', grupo)}  ·  Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            _STYLE_META,
        ),
    ]
    if g.get("desc"):
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(g["desc"], _STYLE_META))
    flow.append(Spacer(1, 12))

    claves = g.get("claves", [])
    for i, clave in enumerate(claves):
        datos = generar_datos_reporte(clave, periodos, incluir_noticias, api_key=api_key)
        flow += _pdf_flowables_indicador(datos)
        if i < len(claves) - 1:
            flow.append(PageBreak())

    flow.append(Spacer(1, 14))
    flow.append(Paragraph("Fuente: INEGI · Banco de Indicadores Económicos (BIE) · Sistema TYASA BI", _STYLE_META))
    doc.build(flow)
    return buf.getvalue()
