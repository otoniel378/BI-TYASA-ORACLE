"""
notify_failure.py — Avisa por correo cuando un workflow de GitHub Actions falla.

Se llama desde los workflows de actualización con `if: failure()`, como último
paso. Reusa el mismo canal de envío que el digest de noticias
(mercado_noticias/analytics/correo_noticias.py) — mismas credenciales de Gmail,
mismo destinatario (DIGEST_EMAIL_TO). Solo depende de la librería estándar,
así que corre incluso si el paso de instalar dependencias del workflow falló.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mercado_noticias.analytics.correo_noticias import enviar_email_noticias


def main() -> None:
    workflow = os.environ.get("GITHUB_WORKFLOW", "Workflow desconocido")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else ""

    subject = f"⚠️ TYASA BI — Falló: {workflow}"
    html = f"""
    <div style="font-family:Arial,sans-serif;padding:20px;color:#1F2937;">
      <h2 style="color:#C62828;margin:0 0 12px;">La actualización automática falló</h2>
      <p><b>Workflow:</b> {workflow}</p>
      <p><b>Repositorio:</b> {repo}</p>
      <p>Revisa el detalle y vuelve a correrlo manualmente (workflow_dispatch) si hace falta:</p>
      <p><a href="{run_url}" style="color:#1B3A5C;">{run_url}</a></p>
      <p style="color:#6B7280;font-size:12px;margin-top:20px;">
        Aviso automático: algún paso de este workflow terminó en error.
        Mientras no se corrija, los datos de este módulo pueden quedar desactualizados.
      </p>
    </div>
    """

    ok, msg = enviar_email_noticias(html, subject)
    print(f"Notificación de falla: {'enviada' if ok else 'NO enviada'} — {msg}")


if __name__ == "__main__":
    main()
