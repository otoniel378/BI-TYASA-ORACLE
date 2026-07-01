"""
market_summary.py — Tabla HTML de indicadores financieros clave para TYASA.
Usada en 01_monitor.py (resumen visual) y 03_industria.py (email digest).
"""
import pandas as pd

# (nombre en DB, etiqueta legible, categoría)
INDICADORES_TABLA = [
    # ── México ────────────────────────────────────────────────────────────────
    ("USD_MXN",          "Tipo de Cambio USD/MXN",   "Mexico"),
    ("EUR_MXN",          "Tipo de Cambio EUR/MXN",   "Mexico"),
    ("USD_CNY",          "USD / Yuan Chino",          "Asia"),
    ("CEMEX",            "CEMEX (construcción MX)",   "Mexico"),
    # ── Energía ───────────────────────────────────────────────────────────────
    ("Brent_USD",        "Petróleo Brent",            "Energia"),
    ("WTI_USD",          "Petróleo WTI",              "Energia"),
    ("Gas_HenryHub_USD", "Gas Natural (Henry Hub)",   "Energia"),
    # ── Insumos acero ─────────────────────────────────────────────────────────
    ("Mineral_Hierro",   "Mineral de Hierro",         "Insumos_Acero"),
    ("Zinc_USD",         "Zinc LME",                  "Insumos_Acero"),
    ("Cobre_USD",        "Cobre LME",                 "Insumos_Acero"),
    ("Aluminio_USD",     "Aluminio LME",              "Insumos_Acero"),
    # ── Sector acero ─────────────────────────────────────────────────────────
    ("ETF_Acero_Global", "ETF Acero Global (SLX)",   "Sector_Acero"),
    ("Ternium_MX",       "Ternium",                   "Sector_Acero"),
    ("ArcelorMittal",    "ArcelorMittal",             "Sector_Acero"),
    ("Nucor_EAF",        "Nucor (EAF)",               "Sector_Acero"),
    # ── Riesgo ───────────────────────────────────────────────────────────────
    ("VIX",              "VIX (Volatilidad)",         "Riesgo_Mercados"),
    ("SP500",            "S&P 500",                   "Riesgo_Mercados"),
    ("Oro_USD",          "Oro",                       "Riesgo_Mercados"),
    # ── Logística ────────────────────────────────────────────────────────────
    ("ETF_Flete_Seco",   "Baltic Dry (BDRY ETF)",    "Logistica"),
]

_CAT_COLOR = {
    "Mexico":          "#1B3A5C",
    "Asia":            "#7C3AED",
    "Energia":         "#D97706",
    "Insumos_Acero":   "#059669",
    "Sector_Acero":    "#2563EB",
    "Riesgo_Mercados": "#DC2626",
    "Logistica":       "#0891B2",
}

_CAT_LABEL = {
    "Mexico":          "México",
    "Asia":            "Asia",
    "Energia":         "Energía",
    "Insumos_Acero":   "Insumos Acero",
    "Sector_Acero":    "Sector Acero",
    "Riesgo_Mercados": "Riesgo",
    "Logistica":       "Logística",
}


def build_indicadores_html(df_vars: pd.DataFrame, titulo: str = "📊 Indicadores Financieros Clave") -> str:
    """
    Genera HTML de tabla de indicadores con valor actual, cambio % diario y fecha.
    Retorna '' si df_vars está vacío.
    """
    if df_vars is None or df_vars.empty:
        return ""

    filas = []
    cat_actual = None

    for nombre, label, cat in INDICADORES_TABLA:
        sub = df_vars[df_vars["nombre"] == nombre].sort_values("fecha")
        if sub.empty:
            continue

        ult   = sub.iloc[-1]
        valor = ult["valor"]
        fecha = str(ult["fecha"])[:10]

        cambio = None
        if len(sub) >= 2:
            prev = sub.iloc[-2]["valor"]
            if prev and prev != 0:
                cambio = (valor - prev) / abs(prev) * 100

        try:
            v_fmt = f"{valor:,.2f}"
        except Exception:
            v_fmt = str(valor)

        if cambio is None:
            c_txt, c_color = "N/A", "#9CA3AF"
        elif cambio >= 0:
            c_txt, c_color = f"+{cambio:.2f}%", "#059669"
        else:
            c_txt, c_color = f"{cambio:.2f}%", "#DC2626"

        dot_color  = _CAT_COLOR.get(cat, "#6B7280")
        cat_label  = _CAT_LABEL.get(cat, cat)

        # Separador de categoría
        if cat != cat_actual:
            cat_actual = cat
            filas.append(
                f"<tr style='background:#F8FAFC;'>"
                f"<td colspan='4' style='padding:5px 14px;font-size:10px;font-weight:700;"
                f"color:{dot_color};text-transform:uppercase;letter-spacing:.06em;'>"
                f"● {cat_label}</td></tr>"
            )

        filas.append(
            f"<tr style='border-bottom:1px solid #F3F4F6;'>"
            f"<td style='padding:7px 14px 7px 22px;font-size:13px;color:#374151;'>{label}</td>"
            f"<td style='padding:7px 14px;font-size:13px;font-weight:600;color:#1B3A5C;"
            f"text-align:right;'>{v_fmt}</td>"
            f"<td style='padding:7px 14px;font-size:13px;font-weight:700;color:{c_color};"
            f"text-align:right;'>{c_txt}</td>"
            f"<td style='padding:7px 14px;font-size:12px;color:#9CA3AF;text-align:right;'>{fecha}</td>"
            f"</tr>"
        )

    if not filas:
        return ""

    return f"""
<div style="margin-bottom:20px;">
  <div style="font-size:11px;font-weight:700;color:#1B3A5C;text-transform:uppercase;
       letter-spacing:.06em;margin-bottom:8px;">{titulo}</div>
  <table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;
         border:1px solid #E5E7EB;">
    <thead>
      <tr style="background:#1B3A5C;">
        <th style="padding:9px 14px;text-align:left;font-size:11px;color:#fff;font-weight:600;">Indicador</th>
        <th style="padding:9px 14px;text-align:right;font-size:11px;color:#fff;font-weight:600;">Valor</th>
        <th style="padding:9px 14px;text-align:right;font-size:11px;color:#fff;font-weight:600;">Cambio diario</th>
        <th style="padding:9px 14px;text-align:right;font-size:11px;color:#fff;font-weight:600;">Actualización</th>
      </tr>
    </thead>
    <tbody>{''.join(filas)}</tbody>
  </table>
</div>"""
