"""
update_sentimiento_noticias.py — Procesa noticias siderúrgicas y clasifica sentimiento con Gemini.
Guarda en Oracle ADW (ADMIN.GOLD_SENTIMIENTO_NOTICIAS) via MERGE sobre ID (hash de URL+fecha).

Uso:
  python scripts/update_sentimiento_noticias.py            # usa token de secrets.toml o .env
  GEMINI_API_KEY=xxx python scripts/update_sentimiento_noticias.py

Corre diariamente (recomendado).
"""

import os, sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import pandas as pd
import oracledb
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

MAX_POR_GRUPO = 8   # noticias a buscar por grupo temático
MAX_TOTAL     = 60  # límite total para no exceder tokens de Gemini


def _get_gemini_key() -> str:
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


def _to_pydate(v):
    """Convierte a datetime.date; NaT/None/'' -> None (oracledb no acepta NaT ni strings sueltas)."""
    ts = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(ts) else ts.to_pydatetime()


def _upsert_oracle(conn: oracledb.Connection, df: pd.DataFrame) -> int:
    """MERGE sobre ID (hash_url) — inserta noticias nuevas, actualiza las que ya existían."""
    if df.empty:
        return 0

    rows = [
        {
            "id": r["hash_url"], "fecha_pub": _to_pydate(r["fecha_pub"]),
            "fecha_analisis": r["fecha_analisis"], "titulo": r["titulo"], "fuente": r["fuente"],
            "url": r["url"], "grupo_tematico": r["grupo_tematico"],
            "variable_principal": r["variable_principal"], "alcance": r["alcance"],
            "sentimiento": r["sentimiento"], "score": r["score"], "senal": r["señal"],
            "razon": r["razon"], "confianza": r["confianza"],
        }
        for r in df.to_dict(orient="records")
    ]

    # Binds nombrados (no posicionales): oracledb cuenta cada *ocurrencia* de un
    # bind posicional como un valor distinto, así que ":1" repetido en USING/VALUES
    # exige duplicar el valor en la tupla — con binds nombrados cada valor se
    # provee una sola vez aunque se use varias veces en el SQL.
    merge_sql = """
        MERGE INTO ADMIN.GOLD_SENTIMIENTO_NOTICIAS T
        USING (SELECT :id AS ID FROM dual) S
        ON (T.ID = S.ID)
        WHEN MATCHED THEN UPDATE SET
            FECHA_ANALISIS     = :fecha_analisis,
            SENTIMIENTO        = :sentimiento,
            SCORE              = :score,
            VARIABLE_PRINCIPAL = :variable_principal,
            SENAL              = :senal,
            ALCANCE            = :alcance,
            RAZON              = :razon,
            CONFIANZA          = :confianza
        WHEN NOT MATCHED THEN INSERT
            (ID, FECHA_PUB, FECHA_ANALISIS, TITULO, FUENTE, URL, GRUPO_TEMATICO,
             VARIABLE_PRINCIPAL, ALCANCE, SENTIMIENTO, SCORE, SENAL, RAZON, CONFIANZA)
        VALUES
            (:id, :fecha_pub, :fecha_analisis, :titulo, :fuente, :url, :grupo_tematico,
             :variable_principal, :alcance, :sentimiento, :score, :senal, :razon, :confianza)
    """
    cursor = conn.cursor()
    try:
        # ADW paraleliza DML por default; varios MERGE seguidos sobre la misma
        # tabla en una transacción sin esto disparan ORA-12838.
        cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
        cursor.executemany(merge_sql, rows)
        conn.commit()
    finally:
        cursor.close()
    return len(rows)


def run():
    print("=" * 60)
    print(f"TYASA BI — Sentimiento Noticias — {date.today()}")
    print("=" * 60)

    gemini_key = _get_gemini_key()
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY no encontrada.")
        sys.exit(1)
    print(f"  Gemini key: ...{gemini_key[-6:]}")

    # Importar módulos del proyecto
    from mercado_noticias.analytics.noticias import (
        buscar_noticias_sector,
        GRUPOS_INDUSTRIA, GRUPOS_NACIONAL, GRUPOS_INTERNACIONAL,
    )
    from mercado_noticias.analytics.sentimiento import (
        clasificar_lote, resultados_a_dataframe,
    )

    # Recopilar noticias de todos los grupos
    todos_grupos = {
        **GRUPOS_INDUSTRIA,
        **GRUPOS_NACIONAL,
        **GRUPOS_INTERNACIONAL,
    }

    todas_noticias: list[dict] = []
    seen_urls: set[str] = set()

    print(f"\n  Buscando noticias en {len(todos_grupos)} grupos temáticos...")
    for grupo in todos_grupos:
        try:
            nots = buscar_noticias_sector(grupo, max_resultados=MAX_POR_GRUPO)
            for n in nots:
                url = n.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    n["grupo"] = grupo
                    todas_noticias.append(n)
        except Exception as e:
            print(f"    [WARN] {grupo}: {e}")

    print(f"  Total noticias únicas: {len(todas_noticias)}")

    if not todas_noticias:
        print("  Sin noticias para procesar.")
        return

    # Clasificar sentimiento con Gemini
    print(f"\n  Clasificando sentimiento (máx {MAX_TOTAL} noticias)...")
    resultados = clasificar_lote(todas_noticias, gemini_key, max_noticias=MAX_TOTAL)

    cached  = sum(1 for r in resultados if r.get("_cached"))
    nuevas  = len(resultados) - cached
    print(f"  Clasificadas: {len(resultados)} ({nuevas} nuevas con Gemini, {cached} desde caché)")

    if not resultados:
        print("  Sin resultados para guardar.")
        return

    # Convertir a DataFrame
    df_sent = resultados_a_dataframe(resultados)
    print(f"  DataFrame: {len(df_sent)} filas")

    df_sent["fecha_analisis"] = datetime.utcnow()

    # Guardar en Oracle ADW
    print("\n  Guardando en Oracle ADW...")
    conn = get_conn()
    try:
        n_guardadas = _upsert_oracle(conn, df_sent)
    finally:
        conn.close()
    print(f"  Guardadas/actualizadas: {n_guardadas} noticias")

    # Resumen de sentimiento
    n_pos = (df_sent["sentimiento"] == "positivo").sum()
    n_neg = (df_sent["sentimiento"] == "negativo").sum()
    n_neu = (df_sent["sentimiento"] == "neutro").sum()
    score_avg = df_sent["score"].mean()
    print(f"\n  Sentimiento del día:")
    print(f"    Positivas: {n_pos} | Negativas: {n_neg} | Neutras: {n_neu}")
    print(f"    Score promedio: {score_avg:+.3f}")
    print("\n  LISTO")


if __name__ == "__main__":
    run()
