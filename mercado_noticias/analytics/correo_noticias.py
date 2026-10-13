"""
correo_noticias.py — Alerta de noticias nuevas estilo "periódico virtual":
una nota destacada arriba (la de mayor impacto para TYASA) + el resto de
noticias nuevas + indicadores de mercado.

A propósito NO importa streamlit — este módulo lo usa scripts/update_sentimiento_noticias.py,
que corre como script plano tanto localmente como en GitHub Actions (sin
servidor de Streamlit, sin .streamlit/secrets.toml en CI). Los secretos se
leen de variables de entorno primero, con fallback a secrets.toml solo para
desarrollo local — mismo patrón que mercado_noticias/analytics/sentimiento.py.
"""

from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

_SENT_COLORS = {
    "positivo": ("#16A34A", "#DCFCE7"),
    "negativo": ("#DC2626", "#FEE2E2"),
    "neutro":   ("#64748B", "#F1F5F9"),
}


def _get_secret(name: str, default: str = "") -> str:
    """os.environ primero (GitHub Actions) -> .streamlit/secrets.toml (local)."""
    val = os.environ.get(name, "")
    if val:
        return val
    try:
        import tomllib
        cfg = tomllib.loads((_ROOT / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
        val = cfg.get(name, default)
        if isinstance(val, list):
            return val  # DIGEST_EMAIL_TO puede ser lista
        return str(val)
    except Exception:
        return default


def seleccionar_noticia_destacada(nuevas: list[dict]) -> dict | None:
    """
    Elige la noticia de mayor impacto para TYASA: prioriza confianza "Alta"
    y, dentro de esas, la de |score| más extremo (positiva o negativa).
    Si ninguna tiene confianza Alta, elige por |score| entre todas.
    """
    if not nuevas:
        return None
    alta = [n for n in nuevas if (n.get("confianza") or "").lower() == "alta"]
    candidatas = alta if alta else nuevas
    return max(candidatas, key=lambda n: abs(float(n.get("score", 0.0) or 0.0)))


def _hero_html(destacada: dict) -> str:
    sent = destacada.get("sentimiento", "neutro")
    color, bg = _SENT_COLORS.get(sent, _SENT_COLORS["neutro"])
    titulo = (destacada.get("titulo") or "").strip()
    razon  = (destacada.get("razon") or "").strip()
    fuente = (destacada.get("fuente") or "").strip()
    url    = (destacada.get("url") or "#").strip()
    var    = (destacada.get("variable_principal") or "").replace("_", " ")
    categoria = destacada.get("categoria") or ""

    return f"""
    <div style="padding:22px 28px;background:{bg};border-bottom:3px solid {color};">
      <div style="font-size:10.5px;font-weight:800;color:{color};text-transform:uppercase;
           letter-spacing:.08em;margin-bottom:8px;">
        Noticia destacada · {sent}{" · " + categoria if categoria else ""}
      </div>
      <a href="{url}" style="text-decoration:none;">
        <h2 style="margin:0 0 8px;font-size:22px;line-height:1.3;color:#0F172A;font-weight:800;">
          {titulo}
        </h2>
      </a>
      <p style="margin:0 0 6px;font-size:13.5px;color:#334155;line-height:1.6;">{razon}</p>
      <div style="font-size:11px;color:#64748B;">
        {fuente}{" · " + var if var else ""}
      </div>
    </div>"""


def _fila_noticia_html(n: dict, color: str) -> str:
    titulo = (n.get("titulo") or "")[:110]
    fuente = (n.get("fuente") or "")
    url    = (n.get("url") or "#")
    categoria = n.get("categoria") or ""
    return f"""
    <tr>
      <td style="padding:8px 10px;border-left:3px solid {color};background:#FAFAFA;">
        <a href="{url}" style="color:#1B3A5C;font-size:13px;font-weight:600;text-decoration:none;">{titulo}</a>
        <div style="font-size:10.5px;color:#94A3B8;margin-top:2px;">
          {fuente}{" · " + categoria if categoria else ""}
        </div>
      </td>
    </tr>"""


def _grupo_html(titulo: str, color: str, items: list[dict]) -> str:
    if not items:
        return ""
    filas = "".join(_fila_noticia_html(n, color) for n in items[:12])
    return f"""
    <div style="margin-bottom:14px;">
      <div style="font-size:11px;font-weight:700;color:{color};text-transform:uppercase;
           letter-spacing:.06em;margin-bottom:6px;">{titulo}</div>
      <table style="width:100%;border-collapse:separate;border-spacing:0 4px;">
        {filas}
      </table>
    </div>"""


def _lista_noticias_html(resto: list[dict]) -> str:
    """Agrupa el resto de noticias nuevas por sentimiento: positivas (verde),
    negativas (rojo) y neutras (gris) — en vez de una sola lista mezclada."""
    if not resto:
        return ""
    positivas = [n for n in resto if n.get("sentimiento") == "positivo"]
    negativas = [n for n in resto if n.get("sentimiento") == "negativo"]
    neutras   = [n for n in resto if n.get("sentimiento") not in ("positivo", "negativo")]

    bloques = (
        _grupo_html("Positivas para TYASA", _SENT_COLORS["positivo"][0], positivas)
        + _grupo_html("Negativas para TYASA", _SENT_COLORS["negativo"][0], negativas)
        + _grupo_html("Neutras / informativas", _SENT_COLORS["neutro"][0], neutras)
    )
    if not bloques:
        return ""
    return f'<div style="padding:16px 28px 4px;">{bloques}</div>'


def _find_logo_path() -> tuple[str | None, str, str]:
    for fname, mime, subtype in [
        ("tyasa_logo.webp", "image/webp", "webp"),
        ("tyasa_logo.png",  "image/png",  "png"),
        ("tyasa_logo.jpg",  "image/jpeg", "jpeg"),
    ]:
        path = _ROOT / "assets" / "img" / fname
        if path.exists():
            return str(path), mime, subtype
    return None, "", ""


def construir_email_noticias_html(
    nuevas: list[dict],
    destacada: dict,
    indicadores_html: str = "",
    hora_corrida: str = "",
) -> str:
    """Arma el HTML completo del correo estilo 'periódico virtual'."""
    resto = [n for n in nuevas if n.get("url") != destacada.get("url")]
    fecha_str = datetime.now().strftime("%d de %B, %Y")

    ind_block = (
        f'<div style="padding:16px 28px;">{indicadores_html}</div>' if indicadores_html else ""
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Segoe UI,Arial,sans-serif;background:#F3F4F6;margin:0;padding:20px;">
<div style="max-width:680px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;
     box-shadow:0 2px 8px rgba(0,0,0,.08);">
  <div style="background:#1B3A5C;padding:20px 28px;">
    <table role="presentation" style="border-collapse:collapse;">
      <tr>
        <td style="padding-right:14px;vertical-align:middle;">
          <img src="cid:tyasa_logo" alt="TYASA" style="height:36px;width:auto;display:block;object-fit:contain;">
        </td>
        <td style="vertical-align:middle;">
          <h1 style="color:#fff;margin:0;font-size:22px;font-weight:800;letter-spacing:.02em;">TYASA BI — Noticias</h1>
          <div style="font-size:10.5px;color:rgba(255,255,255,.55);text-transform:uppercase;
               letter-spacing:.08em;margin-top:2px;">{fecha_str}{" · " + hora_corrida if hora_corrida else ""} · {len(nuevas)} noticia(s) nueva(s)</div>
        </td>
      </tr>
    </table>
  </div>
  {_hero_html(destacada)}
  {_lista_noticias_html(resto)}
  {ind_block}
  <div style="background:#F9FAFB;padding:14px 28px;border-top:1px solid #E5E7EB;">
    <div style="font-size:11px;color:#9CA3AF;">Generado automáticamente por TYASA BI · No responder este mensaje</div>
  </div>
</div>
</body></html>"""


def enviar_email_noticias(
    html_body: str, subject: str, destinatarios_override: list[str] | None = None
) -> tuple[bool, str]:
    """
    Envía el correo por Gmail SMTP (SSL, puerto 465). Requiere, en variables
    de entorno (GitHub Actions) o .streamlit/secrets.toml (local):
      GMAIL_USER, GMAIL_APP_PASSWORD, DIGEST_EMAIL_TO (lista o string)

    destinatarios_override: para pruebas — ignora DIGEST_EMAIL_TO y manda
    solo a esta lista (ej. solo al propio usuario mientras se ajusta el diseño).
    """
    gmail_user = _get_secret("GMAIL_USER")
    gmail_pass = _get_secret("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pass:
        return False, "Faltan GMAIL_USER / GMAIL_APP_PASSWORD."

    if destinatarios_override:
        to_list = [e.strip() for e in destinatarios_override if e.strip()]
    else:
        to_raw = _get_secret("DIGEST_EMAIL_TO", gmail_user)
        if isinstance(to_raw, list):
            to_list = [e.strip() for e in to_raw if e.strip()]
        elif isinstance(to_raw, str) and "," in to_raw:
            to_list = [e.strip() for e in to_raw.split(",") if e.strip()]
        else:
            to_list = [str(to_raw).strip() or gmail_user]

    try:
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"]    = gmail_user
        msg["To"]      = ", ".join(to_list)

        msg_alt = MIMEMultipart("alternative")
        msg_alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(msg_alt)

        logo_path, _mime, subtype = _find_logo_path()
        if logo_path:
            with open(logo_path, "rb") as f:
                logo_img = MIMEImage(f.read(), _subtype=subtype)
            logo_img.add_header("Content-ID", "<tyasa_logo>")
            logo_img.add_header("Content-Disposition", "inline", filename=os.path.basename(logo_path))
            msg.attach(logo_img)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as srv:
            srv.login(gmail_user, gmail_pass)
            srv.sendmail(gmail_user, to_list, msg.as_string())
        return True, f"Enviado a {', '.join(to_list)}"
    except Exception as e:
        return False, f"Error enviando correo: {e}"
