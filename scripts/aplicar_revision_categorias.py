"""
aplicar_revision_categorias.py — Fusiona la revisión manual de
data/categorias_revision.csv sobre data/categorias_bootstrap.csv y separa
el resultado en dos archivos para entrenamiento y validación:

  data/categorias_train.csv     — TODO el bootstrap (etiqueta = categoria_final
                                   si se llenó, si no categoria_gemini), EXCLUYENDO
                                   las URLs que fueron revisadas a mano.
  data/categorias_gold_val.csv  — SOLO las noticias revisadas a mano (held-out,
                                   nunca se usan para entrenar). Este es el set
                                   que mide si el modelo realmente sirve.

Uso:
  python scripts/aplicar_revision_categorias.py
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import pandas as pd

from mercado_noticias.analytics.categorias import CATEGORIAS_TODAS

DATA_DIR = _root.parent / "data"


def run():
    bootstrap_path = DATA_DIR / "categorias_bootstrap.csv"
    revision_path  = DATA_DIR / "categorias_revision.csv"

    if not bootstrap_path.exists():
        print(f"ERROR: no existe {bootstrap_path}. Corre bootstrap_dataset_categorias.py")
        sys.exit(1)
    if not revision_path.exists():
        print(f"ERROR: no existe {revision_path}. Corre muestra_revision_categorias.py "
              "y llena 'categoria_final' en Excel antes de este paso.")
        sys.exit(1)

    df_full = pd.read_csv(bootstrap_path, encoding="utf-8-sig")
    df_rev  = pd.read_csv(revision_path, encoding="utf-8-sig")

    # Validar categorías escritas a mano contra la taxonomía cerrada
    validas = set(CATEGORIAS_TODAS)
    escritas = df_rev["categoria_final"].dropna().astype(str).str.strip()
    escritas = escritas[escritas != ""]
    invalidas = sorted(set(escritas) - validas)
    if invalidas:
        print("ERROR: las siguientes categorías en 'categoria_final' no existen en la "
              "taxonomía (revisa mayúsculas/acentos exactos):")
        for c in invalidas:
            print(f"  - {c!r}")
        sys.exit(1)

    # Etiqueta final de la muestra revisada: categoria_final si se llenó, si no categoria_gemini
    df_rev["categoria_final"] = df_rev["categoria_final"].fillna("").astype(str).str.strip()
    df_rev["categoria_oro"] = df_rev.apply(
        lambda r: r["categoria_final"] if r["categoria_final"] else r["categoria_gemini"],
        axis=1,
    )
    n_corregidas = int((df_rev["categoria_final"] != "").sum())
    print(f"Revisión manual: {len(df_rev)} noticias, {n_corregidas} corregidas por el usuario")

    gold_cols = ["url", "titulo", "descripcion", "fuente", "fecha_pub", "categoria_oro"]
    df_gold = df_rev[[c for c in gold_cols if c in df_rev.columns]].copy()
    df_gold = df_gold.rename(columns={"categoria_oro": "categoria"})

    gold_path = DATA_DIR / "categorias_gold_val.csv"
    df_gold.to_csv(gold_path, index=False, encoding="utf-8-sig")
    print(f"Gold validation set: {len(df_gold)} filas -> {gold_path}")

    print("\nDistribución del gold set:")
    for cat in CATEGORIAS_TODAS:
        n = int((df_gold["categoria"] == cat).sum())
        print(f"  {cat:30s} {n:5d}")

    # Train set: resto del bootstrap, excluyendo las URLs ya revisadas a mano
    urls_revisadas = set(df_rev["url"])
    df_train_src = df_full[~df_full["url"].isin(urls_revisadas)].copy()
    df_train_src["categoria"] = df_train_src["categoria_gemini"]

    train_cols = ["url", "titulo", "descripcion", "fuente", "fecha_pub", "categoria"]
    df_train = df_train_src[[c for c in train_cols if c in df_train_src.columns]]

    train_path = DATA_DIR / "categorias_train.csv"
    df_train.to_csv(train_path, index=False, encoding="utf-8-sig")
    print(f"\nTrain set: {len(df_train)} filas -> {train_path}")

    print("\nDistribución del train set (etiquetas débiles de Gemini):")
    for cat in CATEGORIAS_TODAS:
        n = int((df_train["categoria"] == cat).sum())
        print(f"  {cat:30s} {n:5d}")

    print("\nLISTO. Siguiente paso: python ml/categoria_noticias/train_lstm.py")


if __name__ == "__main__":
    run()
