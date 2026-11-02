"""
scripts/monitor_dof.py — Revisa el sumario diario del DOF, analiza con Gemini
los decretos/acuerdos que puedan afectar a TYASA y, si encuentra algo con
impacto real, manda un correo "ALERTA DOF" inmediato (aparte del periódico
virtual de noticias). Registra en Oracle (ADMIN.GOLD_ALERTAS_DOF) todo lo que
ya analizó para no repetir el trabajo ni la alerta en una corrida futura.

Uso:
  python scripts/monitor_dof.py

Corre como paso extra dentro del mismo workflow de GitHub Actions que
update_sentimiento_noticias.py (9am y 3pm, L-V) — reusa las mismas variables
de entorno (ORACLE_*, GEMINI_API_KEY, GMAIL_*).
"""

import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import oracledb
from datetime import date
from dotenv import load_dotenv

load_dotenv()


def _get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        import tomllib
        cfg = tomllib.loads((_root / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
        return cfg.get("GEMINI_API_KEY", "")
    except Exception:
        return ""


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


def _codigos_ya_analizados(conn: oracledb.Connection, codigos: list[str]) -> set[str]:
    if not codigos:
        return set()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join(f"'{c}'" for c in codigos)  # codigos son numéricos, sin riesgo de inyección
        cursor.execute(f"SELECT CODIGO FROM ADMIN.GOLD_ALERTAS_DOF WHERE CODIGO IN ({placeholders})")
        return {row[0] for row in cursor.fetchall()}
    finally:
        cursor.close()


def _guardar_resultado(conn: oracledb.Connection, analisis: dict, correo_enviado: bool):
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
        cursor.execute(
            """
            MERGE INTO ADMIN.GOLD_ALERTAS_DOF T
            USING (SELECT :codigo AS CODIGO FROM dual) S
            ON (T.CODIGO = S.CODIGO)
            WHEN NOT MATCHED THEN INSERT
                (CODIGO, FECHA_DOF, DEPENDENCIA, DESCRIPCION, URL, RELEVANTE,
                 IMPACTO, DIRECCION, RESUMEN, FRACCIONES_TYASA, CORREO_ENVIADO)
            VALUES
                (:codigo, :fecha_dof, :dependencia, :descripcion, :url, :relevante,
                 :impacto, :direccion, :resumen, :fracciones, :correo_enviado)
            """,
            {
                "codigo": analisis["codigo"],
                "fecha_dof": analisis.get("fecha_dof", "")[:10],
                "dependencia": (analisis.get("titulo_dependencia", "") or "")[:300],
                "descripcion": (analisis.get("descripcion", "") or "")[:1000],
                "url": (analisis.get("url", "") or "")[:500],
                "relevante": 1 if analisis.get("tiene_contenido_relevante") else 0,
                "impacto": (analisis.get("impacto", "") or "")[:10],
                "direccion": (analisis.get("direccion", "") or "")[:15],
                "resumen": (analisis.get("resumen", "") or "")[:1000],
                "fracciones": ", ".join(analisis.get("fracciones_tyasa") or [])[:500],
                "correo_enviado": 1 if correo_enviado else 0,
            },
        )
        conn.commit()
    finally:
        cursor.close()


def run():
    print("=" * 60)
    print(f"TYASA BI — Monitor DOF — {date.today()}")
    print("=" * 60)

    gemini_key = _get_gemini_key()
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY no encontrada.")
        sys.exit(1)

    from mercado_noticias.analytics.dof_monitor import (
        fetch_sumario_dof, filtrar_candidatos, analizar_decreto,
        construir_email_alerta_dof,
    )
    from mercado_noticias.analytics.correo_noticias import enviar_email_noticias

    items = fetch_sumario_dof()
    print(f"\n  Publicaciones en el sumario de hoy: {len(items)}")
    if not items:
        print("  Nada que revisar.")
        return

    candidatos = filtrar_candidatos(items)
    print(f"  Candidatos (dependencia/palabra clave relevante): {len(candidatos)}")
    if not candidatos:
        print("\n  LISTO — sin candidatos hoy.")
        return

    conn = get_conn()
    try:
        ya_vistos = _codigos_ya_analizados(conn, [c["codigo"] for c in candidatos])
        pendientes = [c for c in candidatos if c["codigo"] not in ya_vistos]
        print(f"  Ya analizados en una corrida anterior: {len(ya_vistos)} | Pendientes: {len(pendientes)}")

        alertas_enviadas = 0
        for item in pendientes:
            print(f"\n  Analizando [{item['codigo']}] {item['titulo']} — {item['descripcion'][:80]}")
            analisis = analizar_decreto(item, gemini_key)
            if analisis is None:
                print("    [WARN] No se pudo bajar/analizar la nota, se reintentará en la próxima corrida.")
                continue

            relevante = analisis.get("tiene_contenido_relevante")
            impacto = (analisis.get("impacto") or "").lower()
            correo_enviado = False

            if relevante and impacto in ("alto", "medio"):
                html, subject = construir_email_alerta_dof(analisis)
                ok, msg = enviar_email_noticias(html, subject)
                correo_enviado = ok
                print(f"    Impacto {impacto.upper()} — Correo ALERTA DOF: {'OK' if ok else 'FALLÓ'} — {msg}")
            elif relevante:
                print(f"    Impacto {impacto.upper()} — relevante pero bajo, no se manda alerta aparte.")
            else:
                print("    Sin impacto real para TYASA.")

            _guardar_resultado(conn, analisis, correo_enviado)
            if correo_enviado:
                alertas_enviadas += 1

        print(f"\n  Alertas DOF enviadas hoy: {alertas_enviadas}")
    finally:
        conn.close()

    print("\n  LISTO")


if __name__ == "__main__":
    run()
