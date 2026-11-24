"""
scripts/enviar_resumen_semanal.py — Manda el resumen semanal de TYASA BI por
correo (core/resumen_semanal.py): alertas vigentes, ventas del último mes
completo y mercado de la semana. Corre los lunes 8:00 en
.github/workflows/resumen_semanal.yml; destinatarios = DIGEST_EMAIL_TO.

Uso:
    python scripts/enviar_resumen_semanal.py                  # envía
    python scripts/enviar_resumen_semanal.py --vista-previa   # solo guarda el HTML en logs/
"""

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

from dotenv import load_dotenv

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)
load_dotenv()

from core.resumen_semanal import construir
from mercado_noticias.analytics.correo_noticias import _get_secret, enviar_email_noticias


def main(vista_previa: bool):
    asunto, html = construir(url_app=_get_secret("APP_URL", ""))
    if vista_previa:
        destino = _root / "logs" / "resumen_semanal_vista_previa.html"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(html, encoding="utf-8")
        print(f"{asunto}\nVista previa: {destino}")
        return
    ok, msg = enviar_email_noticias(html, asunto)
    print(msg)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--vista-previa", action="store_true", help="No envía: guarda el HTML en logs/")
    main(parser.parse_args().vista_previa)
