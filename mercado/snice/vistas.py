"""
vistas.py — Piezas HTML de la página de Comercio Exterior Siderúrgico
(pages/mercado/07_comercio_exterior.py): rankings, tarjetas, flechas de variación
y nombres cortos de países y empresas.
"""

import os
import sys

import pandas as pd

from config import COLORS

# Los catálogos de fracciones viven en scripts/ (los comparten las cargas y la página).
_scripts = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from fracciones_tyasa import RAZON_SOCIAL_TYASA_SNICE
from fracciones_tyasa_ligie import FRACCIONES_TYASA_DESCRIPCION
from tigie_partidas import categoria_de


def _rank_bar_row(nombre: str, valor_ton: float, avisos: int, pct_ancho: float, tag: str = "") -> str:
    tag_html = (
        f"<span style='font-size:0.68rem;font-weight:600;color:{COLORS['secondary']};"
        f"background:#E8EFF5;padding:2px 8px;border-radius:20px;margin-left:8px;white-space:nowrap;'>{tag}</span>"
        if tag else ""
    )
    return f"""
    <div style="display:grid;grid-template-columns:1fr 108px;align-items:center;gap:10px;padding:8px 0;">
      <div>
        <div style="font-size:0.85rem;font-weight:600;color:{COLORS['text']};">{nombre}{tag_html}</div>
        <div style="height:7px;background:{COLORS['background']};border-radius:4px;margin-top:5px;overflow:hidden;">
          <div style="height:100%;width:{max(pct_ancho, 2):.0f}%;background:{COLORS['primary']};border-radius:4px;"></div>
        </div>
      </div>
      <div style="text-align:right;font-size:0.82rem;font-weight:700;color:{COLORS['text']};">
        {valor_ton:,.0f} t
        <div style="font-size:0.68rem;font-weight:500;color:{COLORS['text_light']};">{avisos:,} avisos</div>
      </div>
    </div>
    """


def _card_open(titulo: str, subtitulo: str = "") -> str:
    sub = f"<p style='margin:0 0 14px;font-size:0.8rem;color:{COLORS['text_light']};'>{subtitulo}</p>" if subtitulo else "<div style='height:8px'></div>"
    return (
        f"<div style='background:{COLORS['surface']};border:1px solid #E5E7EB;border-radius:14px;"
        f"padding:20px 22px;'>"
        f"<p style='margin:0 0 3px;font-size:1rem;font-weight:700;color:{COLORS['primary']};'>{titulo}</p>"
        f"{sub}"
    )


_CARD_CLOSE = "</div>"


def _rank_list_html(df: pd.DataFrame, col_nombre: str, tag_col: str | None, max_filas: int = 999) -> str:
    if df.empty:
        return f"<p style='color:{COLORS['text_light']};font-size:0.85rem;'>Sin datos para este filtro.</p>"
    df2 = df.head(max_filas)
    max_vol = df2["volumen_total"].max() or 1
    filas = []
    for _, r in df2.iterrows():
        pct = (r["volumen_total"] or 0) / max_vol * 100
        tag = str(r[tag_col]) if tag_col and pd.notna(r.get(tag_col)) else ""
        filas.append(_rank_bar_row(
            str(r[col_nombre]), (r["volumen_total"] or 0) / 1000, int(r["avisos"] or 0), pct, tag,
        ))
    return "".join(filas)


def _agrupar_por_partida(fracciones_df: pd.DataFrame) -> pd.DataFrame:
    """Convierte un detalle por fracción (fraccion_arancelaria/volumen_total/avisos)
    en un ranking por partida (categoría TIGIE), usando el catálogo oficial LIGIE."""
    columnas = ["partida", "categoria_producto", "subcategoria", "volumen_total", "avisos"]
    if fracciones_df.empty:
        return pd.DataFrame(columns=columnas)
    df = fracciones_df.copy()
    df["partida"] = df["fraccion_arancelaria"].str[:4]
    info = df["partida"].apply(categoria_de)
    df["categoria_producto"] = info.apply(lambda t: t[0])
    df["subcategoria"] = info.apply(lambda t: t[1])
    agg = (
        df.groupby(["partida", "categoria_producto", "subcategoria"], as_index=False)[["volumen_total", "avisos"]]
        .sum()
        .sort_values("volumen_total", ascending=False)
    )
    return agg


# Tonos de texto para "subió / bajó" — mismo par divergente que las gráficas
# (core/components/charts.py), un paso más oscuro para que se lea como texto.
_TXT_SUBE, _TXT_BAJA = "#1F5FAE", "#C2410C"


def _color_signo(v) -> str:
    """Estilo de celda para variaciones: azul si sube, naranja si baja."""
    if pd.isna(v) or v == 0:
        return ""
    return f"color:{_TXT_SUBE if v > 0 else _TXT_BAJA};font-weight:600"


def _flecha_pct(actual: float, anterior: float | None) -> str:
    if anterior is None:
        return ""
    if not anterior:
        return f"<span style='color:{_TXT_SUBE};font-weight:600;'>nueva</span>" if actual else ""
    var = (actual - anterior) / anterior * 100
    color, flecha = (_TXT_SUBE, "▲") if var >= 0 else (_TXT_BAJA, "▼")
    return f"<span style='color:{color};font-weight:600;'>{flecha} {abs(var):.1f}%</span>"


def _flecha_pp(actual: float, anterior: float | None) -> str:
    if anterior is None:
        return ""
    dif = actual - anterior
    color, flecha = (_TXT_SUBE, "▲") if dif >= 0 else (_TXT_BAJA, "▼")
    return f"<span style='color:{color};font-weight:600;'>{flecha} {abs(dif):.1f} pp</span>"


def _top_fracciones_html(
    actual: pd.DataFrame, anterior: pd.DataFrame | None, n: int = 5, total: float | None = None,
) -> str:
    """Ranking tipo "Power Rank" de fracciones: barra, toneladas, % del mes y
    variación contra el mes anterior. <actual>/<anterior>: columnas fraccion
    (8 dígitos) y volumen_ton. <total>: base del "% del mes" si <actual> ya viene
    recortado (si no, la suma de <actual>)."""
    if actual.empty:
        return f"<p style='color:{COLORS['text_light']};font-size:0.85rem;'>Sin datos para este periodo.</p>"
    total = total or actual["volumen_ton"].sum() or 1
    top = actual.nlargest(n, "volumen_ton")
    max_vol = top["volumen_ton"].max() or 1
    previo = anterior.set_index("fraccion")["volumen_ton"] if anterior is not None and not anterior.empty else None
    filas = []
    for i, r in enumerate(top.itertuples(), start=1):
        desc = FRACCIONES_TYASA_DESCRIPCION.get(r.fraccion, "sin descripción")
        ant = float(previo.get(r.fraccion, 0)) if previo is not None else None
        filas.append(f"""
        <div style="display:grid;grid-template-columns:22px 1fr 150px;align-items:center;gap:10px;padding:7px 0;
                    border-bottom:1px solid #F1F5F9;">
          <div style="font-size:0.8rem;font-weight:700;color:{COLORS['text_light']};text-align:center;">{i}</div>
          <div style="min-width:0;">
            <div title="{desc}" style="font-size:0.82rem;color:{COLORS['text']};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
              <b>{r.fraccion}</b> <span style="color:{COLORS['text_light']};">{desc}</span>
            </div>
            <div style="height:6px;background:{COLORS['background']};border-radius:4px;margin-top:5px;overflow:hidden;">
              <div style="height:100%;width:{max(r.volumen_ton / max_vol * 100, 2):.0f}%;background:{COLORS['primary']};border-radius:4px;"></div>
            </div>
          </div>
          <div style="text-align:right;font-size:0.82rem;font-weight:700;color:{COLORS['text']};">
            {r.volumen_ton:,.0f} t
            <div style="font-size:0.7rem;font-weight:500;color:{COLORS['text_light']};">
              {r.volumen_ton / total * 100:.1f}% del mes {_flecha_pct(r.volumen_ton, ant)}
            </div>
          </div>
        </div>""")
    return "".join(filas)


_PAIS_CORTO = {
    "CHINA (REPUBLICA POPULAR)": "China",
    "COREA (REPUBLICA DE) (COREA DEL SUR)": "Corea del Sur",
    "ESTADOS UNIDOS DE AMERICA": "Estados Unidos",
    "TAIWAN (REPUBLICA DE CHINA)": "Taiwán",
    "PAISES BAJOS (REINO DE LOS) (HOLANDA)": "Países Bajos",
    "JAPON": "Japón",
}


def _pais_corto(pais: str) -> str:
    return _PAIS_CORTO.get(pais) or pais.split(" (")[0].strip().title()


def _empresa_corta(razon_social: str) -> str:
    nombre = razon_social.strip()
    for sufijo in (" SA DE CV", " S DE RL DE CV", " SAPI DE CV", " SAB DE CV", " SA"):
        if nombre.upper().endswith(sufijo):
            nombre = nombre[: -len(sufijo)]
            break
    if razon_social.upper() == RAZON_SOCIAL_TYASA_SNICE.upper():
        return "TYASA (T A 2000)"
    return nombre if len(nombre) <= 34 else nombre[:33] + "…"
