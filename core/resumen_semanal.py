"""
resumen_semanal.py — Correo semanal de TYASA BI (lunes 8:00, scripts/enviar_resumen_semanal.py).

Tres bloques: ventas de Aceros Planos Negros con las definiciones del catálogo
(core/metricas.py), mercado de la última semana (GOLD_VARIABLES_MERCADO) y las
alertas vigentes de la bandeja (core/alertas.py). Hoy hay una sola versión
(dirección); <rol> queda para separar versiones por rol más adelante.
"""

from datetime import date
from html import escape

import pandas as pd

from core import alertas, metricas
from core.db_connector import run_query_params, table_ref

VARIABLES_MERCADO = [("HRC_CME_USD", "Bobina caliente (HRC) EE. UU.", "USD/t"),
                     ("USD_MXN", "Tipo de cambio", "MXN"),
                     ("Mineral_Hierro", "Mineral de hierro", "USD/t")]
_AZUL, _GRIS, _TEXTO = "#1B3A5C", "#64748B", "#1F2937"
_COLOR_PRIORIDAD = {"alta": "#C62828", "media": "#D97706", "info": "#4A7BA7"}
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def _mes(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{_MESES[ts.month - 1]} {ts.year}"


def _pct(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    color = "#2E7D32" if v >= 0 else "#C62828"
    return f"<span style='color:{color};font-weight:700;'>{v:+.1f} %</span>"


def datos_ventas() -> dict:
    corte = metricas.fecha_corte()
    var_m = metricas.variacion("toneladas", "mes_anterior")
    var_a = metricas.variacion("toneladas", "anio_anterior")
    return {
        "corte": corte, "mes": var_m["mes"], "toneladas_mes": var_m["actual"],
        "vs_mes_anterior": var_m["pct"], "vs_anio_anterior": var_a["pct"],
        "toneladas_anio": metricas.valor("toneladas", corte.replace(month=1, day=1), corte),
        "clientes_activos": metricas.clientes_activos(),
    }


def datos_mercado(hoy: date) -> pd.DataFrame:
    """Último valor de cada variable y cambio contra el último dato de hace 7+ días."""
    nombres = [n for n, _, _ in VARIABLES_MERCADO]
    binds = {f"n{i}": n for i, n in enumerate(nombres)}
    df = run_query_params(f"""
        SELECT NOMBRE, FECHA, VALOR FROM {table_ref('GOLD_VARIABLES_MERCADO')}
        WHERE NOMBRE IN ({", ".join(":" + k for k in binds)}) AND FECHA >= :desde
    """, {**binds, "desde": (pd.Timestamp(hoy) - pd.Timedelta(days=40)).to_pydatetime()})
    df.columns = [c.upper() for c in df.columns]
    filas = []
    for nombre, etiqueta, unidad in VARIABLES_MERCADO:
        s = df[df["NOMBRE"] == nombre].sort_values("FECHA")
        if s.empty:
            continue
        ult = s.iloc[-1]
        previos = s[s["FECHA"] <= ult["FECHA"] - pd.Timedelta(days=7)]
        cambio = ((float(ult["VALOR"]) / float(previos.iloc[-1]["VALOR"]) - 1) * 100) if not previos.empty else None
        filas.append({"etiqueta": etiqueta, "unidad": unidad, "valor": float(ult["VALOR"]),
                      "fecha": ult["FECHA"], "cambio_7d": cambio})
    return pd.DataFrame(filas)


def _bloque(titulo: str, cuerpo: str) -> str:
    return f"""
    <tr><td style="padding:18px 24px 6px;font-size:13px;font-weight:700;color:{_AZUL};
                   text-transform:uppercase;letter-spacing:.05em;">{titulo}</td></tr>
    <tr><td style="padding:0 24px 8px;">{cuerpo}</td></tr>"""


def _fila_dato(etiqueta: str, valor: str, nota: str = "") -> str:
    return f"""<tr>
      <td style="padding:6px 0;font-size:13px;color:{_GRIS};">{etiqueta}</td>
      <td style="padding:6px 0;font-size:14px;font-weight:700;color:{_TEXTO};text-align:right;">{valor}</td>
      <td style="padding:6px 0 6px 10px;font-size:12px;color:{_GRIS};text-align:right;">{nota}</td></tr>"""


def _tarjeta_alerta(a: alertas.Alerta) -> str:
    color = _COLOR_PRIORIDAD[a.prioridad]
    return f"""<div style="border-left:4px solid {color};background:#F8FAFC;padding:8px 12px;margin:6px 0;border-radius:4px;">
      <div style="font-size:11px;font-weight:700;color:{color};text-transform:uppercase;">
        {a.prioridad} · {escape(a.area)} · {escape(a.fuente)}</div>
      <div style="font-size:14px;font-weight:700;color:{_TEXTO};">{escape(a.titulo)}</div>
      <div style="font-size:12.5px;color:{_GRIS};">{escape(a.detalle or "")}</div></div>"""


def construir(hoy: date | None = None, rol: str = "director", url_app: str = "") -> tuple[str, str]:
    """(asunto, html) del resumen semanal."""
    hoy = hoy or date.today()
    lista = alertas.recolectar(hoy)
    altas = [a for a in lista if a.prioridad == "alta"]
    medias = [a for a in lista if a.prioridad == "media"]
    n_info = sum(a.prioridad == "info" for a in lista)

    v = datos_ventas()
    ventas = "<table width='100%' cellpadding='0' cellspacing='0'>" + "".join([
        _fila_dato(f"Toneladas de {_mes(v['mes'])}", f"{v['toneladas_mes']:,.0f} t",
                   f"{_pct(v['vs_mes_anterior'])} vs mes anterior · {_pct(v['vs_anio_anterior'])} vs año anterior"),
        _fila_dato(f"Toneladas en {v['corte'].year} (al corte)", f"{v['toneladas_anio']:,.0f} t"),
        _fila_dato(f"Clientes activos ({metricas.DIAS_CLIENTE_ACTIVO} días)", f"{v['clientes_activos']}"),
    ]) + "</table>"
    ventas += (f"<div style='font-size:11.5px;color:{_GRIS};margin-top:4px;'>Aceros Planos Negros · "
               f"datos al {v['corte']:%d/%m/%Y} · último mes completo: {_mes(v['mes'])}.</div>")

    mk = datos_mercado(hoy)
    mercado = ("<table width='100%' cellpadding='0' cellspacing='0'>" + "".join(
        _fila_dato(r["etiqueta"], f"{r['valor']:,.2f} {r['unidad']}", f"{_pct(r['cambio_7d'])} en 7 días")
        for _, r in mk.iterrows()) + "</table>") if not mk.empty else \
        f"<div style='font-size:13px;color:{_GRIS};'>Sin datos de mercado recientes.</div>"

    cuerpo_alertas = "".join(_tarjeta_alerta(a) for a in altas + medias) or \
        f"<div style='font-size:13px;color:#2E7D32;'>Sin alertas de prioridad alta o media.</div>"
    if n_info:
        cuerpo_alertas += (f"<div style='font-size:12px;color:{_GRIS};margin-top:6px;'>Además, {n_info} "
                           f"{'alerta informativa' if n_info == 1 else 'alertas informativas'} en la bandeja.</div>")

    liga = (f"<a href='{escape(url_app)}' style='color:{_AZUL};font-weight:700;'>Abrir la bandeja en TYASA BI</a>"
            if url_app else "Más detalle en TYASA BI → Inicio → Bandeja de alertas.")
    inicio_semana = pd.Timestamp(hoy) - pd.Timedelta(days=7)
    html = f"""<!doctype html><html><body style="margin:0;background:#EEF2F6;font-family:Segoe UI,Arial,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F6;padding:20px 0;"><tr><td align="center">
    <table width="640" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:10px;overflow:hidden;">
      <tr><td style="background:{_AZUL};padding:16px 24px;">
        <div style="color:#FFFFFF;font-size:18px;font-weight:700;">TYASA BI · Resumen semanal</div>
        <div style="color:rgba(255,255,255,.7);font-size:12px;">Semana del {inicio_semana:%d/%m} al {pd.Timestamp(hoy):%d/%m/%Y}
          · {len(altas)} alertas altas · {len(medias)} medias</div></td></tr>
      {_bloque("Alertas que requieren atención", cuerpo_alertas)}
      {_bloque("Ventas", ventas)}
      {_bloque("Mercado esta semana", mercado)}
      <tr><td style="padding:16px 24px 22px;font-size:12.5px;color:{_GRIS};border-top:1px solid #E5E7EB;">{liga}</td></tr>
    </table></td></tr></table></body></html>"""
    asunto = f"TYASA BI · Resumen semanal {pd.Timestamp(hoy):%d/%m}: {len(altas)} alertas altas"
    return asunto, html
