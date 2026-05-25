"""
update_sentimiento_noticias.py — Procesa noticias siderúrgicas y clasifica sentimiento con Gemini.

Uso:
  python scripts/update_sentimiento_noticias.py            # usa token de secrets.toml
  GEMINI_API_KEY=xxx python scripts/update_sentimiento_noticias.py

Corre diariamente (recomendado). Guarda en gold_sentimiento_noticias via MERGE.
"""

import os, sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import pandas as pd
from datetime import date

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID   = "project-d0cf2519-d089-47d3-930"
DATASET      = "tyasa_bi"
TABLE_SENT   = f"{PROJECT_ID}.{DATASET}.gold_sentimiento_noticias"
TABLE_STAGING = f"{PROJECT_ID}.{DATASET}._staging_sentimiento"

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


def _get_bq_client():
    from google.cloud import bigquery
    return bigquery.Client(project=PROJECT_ID)


def _crear_tabla_si_no_existe(client):
    from google.cloud import bigquery
    schema = [
        bigquery.SchemaField("hash_url",           "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("fecha_pub",           "DATE"),
        bigquery.SchemaField("fecha_analisis",      "DATE"),
        bigquery.SchemaField("titulo",              "STRING"),
        bigquery.SchemaField("fuente",              "STRING"),
        bigquery.SchemaField("url",                 "STRING"),
        bigquery.SchemaField("grupo_tematico",      "STRING"),
        bigquery.SchemaField("variable_principal",  "STRING"),
        bigquery.SchemaField("alcance",             "STRING"),
        bigquery.SchemaField("sentimiento",         "STRING"),
        bigquery.SchemaField("score",               "FLOAT64"),
        bigquery.SchemaField("señal",               "STRING"),
        bigquery.SchemaField("razon",               "STRING"),
        bigquery.SchemaField("confianza",           "STRING"),
    ]
    table = bigquery.Table(TABLE_SENT, schema=schema)
    client.create_table(table, exists_ok=True)
    print(f"  Tabla {TABLE_SENT} lista.")


def _upsert_bq(client, df: pd.DataFrame) -> int:
    """Carga df a staging y hace MERGE sobre hash_url."""
    if df.empty:
        return 0

    from google.cloud import bigquery
    job_cfg = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("hash_url",          "STRING"),
            bigquery.SchemaField("fecha_pub",          "DATE"),
            bigquery.SchemaField("fecha_analisis",     "DATE"),
            bigquery.SchemaField("titulo",             "STRING"),
            bigquery.SchemaField("fuente",             "STRING"),
            bigquery.SchemaField("url",                "STRING"),
            bigquery.SchemaField("grupo_tematico",     "STRING"),
            bigquery.SchemaField("variable_principal", "STRING"),
            bigquery.SchemaField("alcance",            "STRING"),
            bigquery.SchemaField("sentimiento",        "STRING"),
            bigquery.SchemaField("score",              "FLOAT64"),
            bigquery.SchemaField("señal",              "STRING"),
            bigquery.SchemaField("razon",              "STRING"),
            bigquery.SchemaField("confianza",          "STRING"),
        ]
    )
    df["fecha_pub"]       = pd.to_datetime(df["fecha_pub"], errors="coerce").dt.date
    df["fecha_analisis"]  = pd.to_datetime(df["fecha_analisis"], errors="coerce").dt.date

    client.load_table_from_dataframe(df, TABLE_STAGING, job_config=job_cfg).result()

    merge_sql = f"""
    MERGE `{TABLE_SENT}` T
    USING `{TABLE_STAGING}` S ON T.hash_url = S.hash_url
    WHEN NOT MATCHED THEN INSERT ROW
    WHEN MATCHED THEN UPDATE SET
      fecha_analisis     = S.fecha_analisis,
      sentimiento        = S.sentimiento,
      score              = S.score,
      variable_principal = S.variable_principal,
      señal              = S.señal,
      alcance            = S.alcance,
      razon              = S.razon,
      confianza          = S.confianza
    """
    client.query(merge_sql).result()
    client.delete_table(TABLE_STAGING, not_found_ok=True)
    return len(df)


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

    # Guardar en BigQuery
    print("\n  Guardando en BigQuery...")
    client = _get_bq_client()
    _crear_tabla_si_no_existe(client)
    n_guardadas = _upsert_bq(client, df_sent)
    print(f"  Guardadas/actualizadas: {n_guardadas} noticias")

    # Resumen de sentimiento
    n_pos = (df_sent["sentimiento"] == "positivo").sum()
    n_neg = (df_sent["sentimiento"] == "negativo").sum()
    n_neu = (df_sent["sentimiento"] == "neutro").sum()
    score_avg = df_sent["score"].mean()
    print(f"\n  Sentimiento del día:")
    print(f"    ✅ Positivas: {n_pos} | ❌ Negativas: {n_neg} | ⚪ Neutras: {n_neu}")
    print(f"    Score promedio: {score_avg:+.3f}")
    print("\n  ✅ LISTO")


if __name__ == "__main__":
    run()
