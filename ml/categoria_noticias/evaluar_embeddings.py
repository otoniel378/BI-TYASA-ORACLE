"""
evaluar_embeddings.py — Mide el desempeño real de los dos clasificadores
entrenados sobre embeddings preentrenados (train_embeddings.py) contra
data/categorias_gold_val.csv (noticias revisadas a mano): el LogisticRegression
(modelo de producción, clasificador_lr.pkl) y la red densa Keras (solo
referencia/comparación, model.keras). Mismo umbral de referencia que evaluar.py
(F1 macro >= 0.65).

Uso:
  python ml/categoria_noticias/evaluar_embeddings.py
"""

import pickle
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score,
)

from ml.categoria_noticias.preprocesamiento import construir_texto, simplificar_categoria
from ml.categoria_noticias.embeddings_utils import embed_textos

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts_embeddings"
DATA_DIR      = _root.parent / "data"
UMBRAL_F1_MACRO = 0.65


def _cargar_gold_set(clases_conocidas: set[str]) -> pd.DataFrame:
    gold_path = DATA_DIR / "categorias_gold_val.csv"
    if not gold_path.exists():
        print(f"ERROR: no existe {gold_path}. Corre aplicar_revision_categorias.py primero.")
        sys.exit(1)

    df = pd.read_csv(gold_path, encoding="utf-8-sig")
    df = df.dropna(subset=["categoria"])
    df["categoria"] = df["categoria"].apply(simplificar_categoria)
    df = df.dropna(subset=["categoria"])
    df["texto"] = df.apply(
        lambda r: construir_texto(r.get("titulo", ""), r.get("descripcion", "")), axis=1,
    )

    desconocidas = set(df["categoria"]) - clases_conocidas
    if desconocidas:
        print(f"[AVISO] categorías en el gold set ausentes del train set (se excluyen "
              f"de la evaluación): {sorted(desconocidas)}")
        df = df[df["categoria"].isin(clases_conocidas)]
    return df


def _reportar(nombre_modelo: str, df: pd.DataFrame, y_pred: np.ndarray, confianza_pred: np.ndarray,
              sufijo_artefacto: str) -> float:
    y_true = df["categoria"].values
    acc = accuracy_score(y_true, y_pred)
    f1_macro = f1_score(y_true, y_pred, average="macro", zero_division=0)

    print(f"\n{'-' * 60}\n{nombre_modelo}\n{'-' * 60}")
    print(f"Gold set: {len(df)} noticias revisadas a mano")
    print(f"Accuracy:  {acc:.3f}")
    print(f"F1 macro:  {f1_macro:.3f}  (umbral de referencia: {UMBRAL_F1_MACRO})")

    if f1_macro >= UMBRAL_F1_MACRO:
        print(">>> PASA el umbral")
    else:
        print(">>> NO alcanza el umbral")

    print("\nReporte por categoría:")
    print(classification_report(y_true, y_pred, zero_division=0))

    etiquetas = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=etiquetas)
    pd.DataFrame(cm, index=etiquetas, columns=etiquetas).to_csv(
        ARTIFACTS_DIR / f"matriz_confusion_{sufijo_artefacto}.csv", encoding="utf-8-sig"
    )

    df_err = df[["url", "titulo", "categoria"]].copy()
    df_err["categoria_predicha"] = y_pred
    df_err["confianza_modelo"] = confianza_pred
    df_err = df_err[df_err["categoria"] != df_err["categoria_predicha"]]
    df_err = df_err.sort_values("confianza_modelo", ascending=False)
    df_err.to_csv(ARTIFACTS_DIR / f"errores_{sufijo_artefacto}.csv", index=False, encoding="utf-8-sig")
    print(f"Matriz de confusión y errores guardados con sufijo '_{sufijo_artefacto}'")

    return f1_macro


def run():
    print("=" * 60)
    print("TYASA BI — Evaluación embeddings preentrenados (gold set revisado a mano)")
    print("=" * 60)

    for nombre in ["clasificador_lr.pkl", "model.keras", "label_encoder.pkl"]:
        if not (ARTIFACTS_DIR / nombre).exists():
            print(f"ERROR: falta {ARTIFACTS_DIR / nombre}. Corre train_embeddings.py primero.")
            sys.exit(1)

    with open(ARTIFACTS_DIR / "label_encoder.pkl", "rb") as f:
        label_encoder = pickle.load(f)

    df = _cargar_gold_set(set(label_encoder.classes_))

    print("\nCalculando embeddings del gold set...")
    X = embed_textos(df["texto"].tolist())

    # ── LogisticRegression (modelo de producción) ──────────────────────────────
    with open(ARTIFACTS_DIR / "clasificador_lr.pkl", "rb") as f:
        clasificador_lr = pickle.load(f)
    probs_lr = clasificador_lr.predict_proba(X)
    y_pred_int_lr = np.argmax(probs_lr, axis=1)
    y_pred_lr = label_encoder.inverse_transform(y_pred_int_lr)
    confianza_lr = probs_lr[np.arange(len(probs_lr)), y_pred_int_lr]
    f1_lr = _reportar("LogisticRegression (PRODUCCIÓN)", df, y_pred_lr, confianza_lr, "lr")

    # ── Red densa Keras (solo referencia) ──────────────────────────────────────
    import tensorflow as tf
    modelo_keras = tf.keras.models.load_model(ARTIFACTS_DIR / "model.keras")
    probs_k = modelo_keras.predict(X, verbose=0)
    y_pred_int_k = np.argmax(probs_k, axis=1)
    y_pred_k = label_encoder.inverse_transform(y_pred_int_k)
    confianza_k = probs_k[np.arange(len(probs_k)), y_pred_int_k]
    f1_k = _reportar("Red densa Keras (referencia)", df, y_pred_k, confianza_k, "keras")

    print(f"\n{'=' * 60}")
    print(f"Resumen: LogisticRegression F1={f1_lr:.3f} | Keras F1={f1_k:.3f}")
    print("=" * 60)


if __name__ == "__main__":
    run()
