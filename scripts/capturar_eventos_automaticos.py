"""
scripts/capturar_eventos_automaticos.py — Captura automáticamente en
GOLD_EVENTOS_HISTORICOS los quiebres de mercado severos del día, con
contexto de noticias ya clasificadas y una síntesis corta de Gemini.

Objetivo: memoria institucional que se va construyendo sola — si en el
futuro hay un shock fuerte (aranceles nuevos, otra pandemia, lo que sea),
queda registrado desde el día en que pasa, sin depender de reconstruirlo
después (no existe un archivo confiable de noticias históricas viejas).

Corre DESPUÉS de (mismo job, mismo orden que ya usa update_sentimiento.yml):
  1. scripts/update_market_data.py       (quiebres frescos del día)
  2. scripts/update_sentimiento_noticias.py (noticias clasificadas del día)
  3. scripts/link_noticias_quiebres.py   (opcional, no es dependencia dura)

Solo captura severidad Alto/Crítico — con Moderado la tabla se llenaría de
ruido (se vio en pruebas: ~2 quiebres/mes por variable con umbral bajo).
Reutiliza MAPEO_VARIABLE_A_CATEGORIA de link_noticias_quiebres.py: si la
variable no tiene categoría de noticias mapeada, igual se captura el evento
con una descripción basada solo en la estadística (mejor guardar algo que
perder el registro por un diccionario incompleto).

Uso:
    python scripts/capturar_eventos_automaticos.py
    python scripts/capturar_eventos_automaticos.py --fecha 2026-08-05   # prueba con una fecha ya existente
"""

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))
sys.path.insert(0, os.path.dirname(__file__))

import oracledb
from dotenv import load_dotenv

from link_noticias_quiebres import MAPEO_VARIABLE_A_CATEGORIA
from mercado_noticias.analytics.ai_analysis import _call_gemini_text

load_dotenv()

SEVERIDADES_CAPTURA = ("Crítico", "Alto")
VENTANA_NOTICIAS_DIAS = 3


def _get_gemini_key() -> str:
    """Env var primero (así corre en GitHub Actions); si no, cae a
    secrets.toml (para pruebas locales) — mismo patrón que
    scripts/update_sentimiento_noticias.py."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        import tomllib
        cfg = tomllib.loads((_root / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
        return cfg.get("GEMINI_API_KEY", "")
    except Exception:
        try:
            import tomli
            cfg = tomli.loads((_root / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
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


def _quiebres_severos(cursor, fecha_detect: date) -> list[tuple]:
    cursor.execute(f"""
        SELECT VARIABLE, FECHA_CORTE, SIGMA, CAMBIO_PCT, SEVERIDAD
        FROM ADMIN.GOLD_QUIEBRES_DETECTADOS
        WHERE ACTIVO = 1 AND FECHA_DETECT = :fecha
          AND SEVERIDAD IN ({",".join(f"'{s}'" for s in SEVERIDADES_CAPTURA)})
    """, {"fecha": fecha_detect})
    return cursor.fetchall()


def _noticias_relacionadas(cursor, variable: str, fecha_corte) -> list[tuple]:
    categorias = MAPEO_VARIABLE_A_CATEGORIA.get(variable)
    if not categorias:
        return []
    desde = fecha_corte - timedelta(days=VENTANA_NOTICIAS_DIAS)
    hasta = fecha_corte + timedelta(days=VENTANA_NOTICIAS_DIAS)
    placeholders = ", ".join(f":cat{i}" for i in range(len(categorias)))
    params = {f"cat{i}": c for i, c in enumerate(categorias)}
    params.update({"desde": desde, "hasta": hasta})
    cursor.execute(f"""
        SELECT TITULO, RAZON, URL
        FROM ADMIN.GOLD_SENTIMIENTO_NOTICIAS
        WHERE VARIABLE_PRINCIPAL IN ({placeholders}) AND FECHA_PUB BETWEEN :desde AND :hasta
        ORDER BY FECHA_PUB DESC
        FETCH FIRST 6 ROWS ONLY
    """, params)
    return cursor.fetchall()


def _sintetizar(variable: str, sigma: float, cambio_pct: float, severidad: str,
                 noticias: list[tuple], api_key: str) -> tuple[str, str]:
    """Devuelve (nombre_evento, descripcion). Si Gemini no está disponible o
    no responde en el formato esperado, arma un fallback simple con la
    estadística — nunca se cae sin guardar nada."""
    fallback_nombre = f"Ruptura {severidad.lower()} en {variable.replace('_', ' ')}"
    fallback_desc = (
        f"Ruptura estadística {severidad.lower()} detectada en {variable.replace('_', ' ')}: "
        f"sigma={sigma}, cambio de {cambio_pct}% respecto al periodo previo."
    )
    if not api_key:
        return fallback_nombre, fallback_desc

    contexto_noticias = ""
    if noticias:
        titulos = "; ".join(f"{t} ({r})" for t, r, _ in noticias[:5])
        contexto_noticias = f" Noticias relacionadas encontradas: {titulos}."

    prompt = (
        f"Ruptura estadística {severidad.lower()} detectada en la variable de mercado "
        f"'{variable}' (sigma={sigma}, cambio={cambio_pct}%).{contexto_noticias} "
        "Esto es para el mercado siderúrgico mexicano (TYASA). Responde EXACTAMENTE en este formato, "
        "sin nada más:\nNOMBRE: <máximo 8 palabras>\nDESCRIPCION: <máximo 2 frases>"
    )
    try:
        respuesta = _call_gemini_text(prompt, api_key, max_output_tokens=200, temperature=0.3)
        m_nombre = re.search(r"NOMBRE:\s*(.+)", respuesta)
        m_desc = re.search(r"DESCRIPCION:\s*(.+)", respuesta, re.DOTALL)
        nombre = m_nombre.group(1).strip() if m_nombre else fallback_nombre
        descripcion = m_desc.group(1).strip() if m_desc else fallback_desc
        return nombre[:200], descripcion[:2000]
    except Exception as e:
        print(f"  Aviso: Gemini no respondió ({e}), usando descripción estadística.")
        return fallback_nombre, fallback_desc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fecha", help="FECHA_DETECT a procesar (YYYY-MM-DD). Default: hoy.")
    args = parser.parse_args()
    fecha_detect = datetime.strptime(args.fecha, "%Y-%m-%d").date() if args.fecha else date.today()

    api_key = _get_gemini_key()
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER SESSION DISABLE PARALLEL DML")

        quiebres = _quiebres_severos(cursor, fecha_detect)
        print(f"Quiebres severos en {fecha_detect}: {len(quiebres)}")
        if not quiebres:
            return

        for variable, fecha_corte, sigma, cambio_pct, severidad in quiebres:
            # Las noticias se buscan alrededor de fecha_corte (cuándo empezó el
            # movimiento real), pero el evento se fecha con fecha_detect (cuándo
            # el sistema lo marcó como significativo) — con el algoritmo actual
            # de update_market_data.py, fecha_corte puede quedar varios meses
            # atrás dentro de la ventana de detección, lo que dispersaría el
            # mismo evento en meses viejos y confundiría la vista por año.
            noticias = _noticias_relacionadas(cursor, variable, fecha_corte)
            nombre, descripcion = _sintetizar(variable, sigma, cambio_pct, severidad, noticias, api_key)

            evento_id = f"auto_{variable}_{fecha_detect.strftime('%Y%m')}"
            fuente = "; ".join(url for _, _, url in noticias) if noticias else "Detección estadística automática"

            cursor.execute("""
                MERGE INTO ADMIN.GOLD_EVENTOS_HISTORICOS t
                USING (SELECT :id AS ID FROM dual) s
                ON (t.ID = s.ID)
                WHEN MATCHED THEN UPDATE SET
                    FECHA_FIN = :fecha_detect, NOMBRE = :nombre, DESCRIPCION = :descripcion,
                    VARIABLES_RELACIONADAS = :variable, FUENTE = :fuente
                WHEN NOT MATCHED THEN INSERT
                    (ID, FECHA_INICIO, FECHA_FIN, NOMBRE, DESCRIPCION, VARIABLES_RELACIONADAS, FUENTE)
                    VALUES (:id, :fecha_detect, :fecha_detect, :nombre, :descripcion, :variable, :fuente)
            """, {
                "id": evento_id, "fecha_detect": fecha_detect, "nombre": nombre,
                "descripcion": descripcion, "variable": variable, "fuente": fuente[:500],
            })
            conn.commit()
            print(f"  OK {evento_id}: {nombre}")

        print(f"\n{len(quiebres)} eventos procesados.")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
