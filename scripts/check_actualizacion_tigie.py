"""
scripts/check_actualizacion_tigie.py — Aviso mensual: ¿ya hay una edición más
nueva de la TIGIE completa en SNICE que la que tiene cargada el sistema
(ADMIN.GOLD_TIGIE_BASE)? Solo revisa y avisa por correo — NO descarga ni
carga nada solo (ver scripts/cargar_tigie_base_oracle.py, que sigue siendo
manual a propósito).

SNICE republica la TIGIE completa 1-2 veces al año, así que no vale la pena
automatizar la carga; pero tampoco hay que acordarse de revisar a mano — este
script lo hace una vez al mes (GitHub Actions) y solo manda correo si
encuentra algo más reciente que lo ya cargado.

Fuente: listado público de archivos de SNICE (snice.gob.mx/~oracle/SNICE_DOCS/).
Las ediciones "completas" siguen el patrón de nombre
"TIGIE-<MES><AA>-TIGIE_<AAAAMMDD>-<AAAAMMDD>.XLSX" (confirmado 2026-11-25: hoy
solo existe "TIGIE-MAYO24-TIGIE_20240529-20240529.XLSX" con ese patrón exacto
— por eso el regex es estricto, para no disparar avisos falsos con los miles
de otros archivos de ese directorio que también traen "TIGIE" en el nombre).

Uso:
  python scripts/check_actualizacion_tigie.py
"""

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import oracledb
import requests
from dotenv import load_dotenv

load_dotenv()

LISTADO_URL = "https://www.snice.gob.mx/~oracle/SNICE_DOCS/"
_EDICION_RE = re.compile(
    r'<a href="(TIGIE-[A-Za-z]+\d{2}-TIGIE_(\d{8})-\d{8}\.[Xx][Ll][Ss][Xx])">'
)


def get_conn() -> oracledb.Connection:
    wallet_dir = os.environ.get("ORACLE_WALLET_DIR", "")
    params = {
        "user":     os.environ.get("ORACLE_USER", "ADMIN"),
        "password": os.environ.get("ORACLE_PASSWORD", ""),
        "dsn":      os.environ.get("ORACLE_DSN", ""),
    }
    if wallet_dir:
        params["config_dir"]      = wallet_dir
        params["wallet_location"] = wallet_dir
        wallet_pw = os.environ.get("ORACLE_WALLET_PASSWORD", "")
        if wallet_pw:
            params["wallet_password"] = wallet_pw
    return oracledb.connect(**params)


def _fecha_cargada(conn: oracledb.Connection) -> date | None:
    """FUENTE_FECHA (DD/MM/YYYY) más reciente ya cargada en GOLD_TIGIE_BASE."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(FUENTE_FECHA) FROM ADMIN.GOLD_TIGIE_BASE")
        row = cursor.fetchone()
    finally:
        cursor.close()
    if not row or not row[0]:
        return None
    return datetime.strptime(row[0], "%d/%m/%Y").date()


def _ediciones_disponibles_snice() -> list[tuple[str, date]]:
    """[(nombre_archivo, fecha), ...] de las ediciones "TIGIE completa"
    publicadas en el directorio de SNICE, según el patrón de nombre oficial."""
    resp = requests.get(LISTADO_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; TyasaBI/1.0)"}, timeout=30)
    resp.raise_for_status()
    ediciones = []
    for nombre, fecha_str in _EDICION_RE.findall(resp.text):
        try:
            ediciones.append((nombre, datetime.strptime(fecha_str, "%Y%m%d").date()))
        except ValueError:
            continue
    return ediciones


def run():
    print("=" * 60)
    print(f"TYASA BI — Chequeo de edición TIGIE (SNICE) — {date.today()}")
    print("=" * 60)

    conn = get_conn()
    try:
        fecha_cargada = _fecha_cargada(conn)
    finally:
        conn.close()
    print(f"  Edición cargada hoy en GOLD_TIGIE_BASE: {fecha_cargada or 'ninguna'}")

    ediciones = _ediciones_disponibles_snice()
    if not ediciones:
        print("  No se encontró ninguna edición 'TIGIE completa' en el listado de SNICE (¿cambió el formato del sitio?).")
        return

    nombre_mas_reciente, fecha_mas_reciente = max(ediciones, key=lambda t: t[1])
    print(f"  Edición más reciente en SNICE: {nombre_mas_reciente} ({fecha_mas_reciente})")

    if fecha_cargada and fecha_mas_reciente <= fecha_cargada:
        print("\n  LISTO — no hay edición más nueva, no se manda aviso.")
        return

    from mercado_noticias.analytics.correo_noticias import enviar_email_noticias

    url_archivo = LISTADO_URL + nombre_mas_reciente
    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"></head>
<body style="font-family:Segoe UI,Arial,sans-serif;background:#F3F4F6;margin:0;padding:20px;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
  <div style="background:#1B3A5C;padding:18px 26px;">
    <h1 style="color:#fff;margin:0;font-size:17px;font-weight:800;">TYASA BI &middot; Nueva edición de la TIGIE disponible</h1>
  </div>
  <div style="padding:22px 26px;">
    <p style="margin:0 0 12px;font-size:13.5px;color:#334155;line-height:1.6;">
      SNICE publicó una edición de la TIGIE completa más reciente que la que tiene cargado el
      sistema en <b>GOLD_TIGIE_BASE</b> (arancel base IGI/IGE por fracción de los capítulos 72/73).
    </p>
    <table style="width:100%;font-size:13px;color:#334155;margin:14px 0;border-collapse:collapse;">
      <tr><td style="padding:4px 0;color:#64748B;">Cargada actualmente:</td><td style="font-weight:700;">{fecha_cargada.strftime('%d/%m/%Y') if fecha_cargada else 'ninguna'}</td></tr>
      <tr><td style="padding:4px 0;color:#64748B;">Disponible en SNICE:</td><td style="font-weight:700;color:#1B3A5C;">{fecha_mas_reciente.strftime('%d/%m/%Y')}</td></tr>
    </table>
    <p style="margin:0 0 14px;font-size:13px;color:#334155;line-height:1.6;">
      Para actualizarla: en <code>scripts/cargar_tigie_base_oracle.py</code>, cambiar <code>TIGIE_URL</code>
      y <code>FUENTE_FECHA</code> por esta edición y correr el script (hace MERGE, no duplica filas).
    </p>
    <a href="{url_archivo}" style="display:inline-block;font-size:12.5px;color:#1B3A5C;font-weight:600;">Ver archivo en SNICE &rarr;</a>
  </div>
  <div style="background:#F9FAFB;padding:12px 26px;border-top:1px solid #E5E7EB;">
    <div style="font-size:11px;color:#9CA3AF;">Chequeo automático mensual &middot; No vuelve a avisar hasta que se actualice GOLD_TIGIE_BASE</div>
  </div>
</div>
</body></html>"""
    subject = f"TYASA BI · Nueva edición TIGIE disponible en SNICE ({fecha_mas_reciente.strftime('%d/%m/%Y')})"
    ok, msg = enviar_email_noticias(html, subject)
    print(f"\n  Correo de aviso: {'OK' if ok else 'FALLÓ'} — {msg}")


if __name__ == "__main__":
    run()
