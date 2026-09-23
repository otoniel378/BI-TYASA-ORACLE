"""
evaluar.py — Mide el desempeño REAL del clasificador LSTM sobre
data/categorias_gold_val.csv (las noticias revisadas a mano por el usuario).

Este es el único número que importa para decidir si el modelo "sirve":
el accuracy/F1 sobre el train set o el val interno de train_lstm.py están
inflados porque comparten el mismo origen de etiquetas débiles (Gemini).

Umbral de referencia (ver plan): F1 macro >= 0.65 en el gold set para
considerar que el LSTM puede reemplazar al clasificador por prompt de Gemini
en producción. Si no lo alcanza, categorias.py (Gemini) se queda como la
ruta de categorización en producción.

Uso:
  python ml/categoria_noticias/evaluar.py
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

from ml.categoria_noticias.preprocesamiento import (
    construir_texto, limpiar_texto, simplificar_categoria,
)

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DATA_DIR      = _root.parent / "data"
UMBRAL_F1_MACRO = 0.65


def run():
    print("=" * 60)
    print("TYASA BI — Evaluación LSTM categorías (gold set revisado a mano)")
    print("=" * 60)

    gold_path = DATA_DIR / "categorias_gold_val.csv"
    if not gold_path.exists():
        print(f"ERROR: no existe {gold_path}. Corre aplicar_revision_categorias.py primero.")
        sys.exit(1)

    for nombre in ["model.keras", "tokenizer.json", "label_encoder.pkl"]:
        if not (ARTIFACTS_DIR / nombre).exists():
            print(f"ERROR: falta {ARTIFACTS_DIR / nombre}. Corre train_lstm.py primero.")
            sys.exit(1)

    import tensorflow as tf
    from tensorflow.keras.preprocessing.text import tokenizer_from_json
    from tensorflow.keras.preprocessing.sequence import pad_sequences

    modelo = tf.keras.models.load_model(ARTIFACTS_DIR / "model.keras")
    tokenizer = tokenizer_from_json((ARTIFACTS_DIR / "tokenizer.json").read_text(encoding="utf-8"))
    with open(ARTIFACTS_DIR / "label_encoder.pkl", "rb") as f:
        label_encoder = pickle.load(f)

    df = pd.read_csv(gold_path, encoding="utf-8-sig")
    df = df.dropna(subset=["categoria"])
    # Misma simplificación de taxonomía usada al entrenar (ver preprocesamiento.py) —
    # comparar contra las etiquetas originales de 15 clases invalidaría la evaluación.
    df["categoria"] = df["categoria"].apply(simplificar_categoria)
    df = df.dropna(subset=["categoria"])
    df["texto"] = df.apply(
        lambda r: limpiar_texto(construir_texto(r.get("titulo", ""), r.get("descripcion", ""))),
        axis=1,
    )

    # Filtrar categorías del gold set que el modelo no vio en entrenamiento
    conocidas = set(label_encoder.classes_)
    desconocidas = set(df["categoria"]) - conocidas
    if desconocidas:
        print(f"[AVISO] categorías en el gold set ausentes del train set (se excluyen "
              f"de la evaluación): {sorted(desconocidas)}")
        df = df[df["categoria"].isin(conocidas)]

    max_len = modelo.input_shape[1]
    secuencias = tokenizer.texts_to_sequences(df["texto"])
    X = pad_sequences(secuencias, maxlen=max_len, padding="post", truncating="post")

    probs = modelo.predict(X, verbose=0)
    y_pred_int = np.argmax(probs, axis=1)
    y_pred = label_encoder.inverse_transform(y_pred_int)
    y_true = df["categoria"].values

    acc = accuracy_score(y_true, y_pred)
    f1_macro = f1_score(y_true, y_pred, average="macro", zero_division=0)

    print(f"\nGold set: {len(df)} noticias revisadas a mano")
    print(f"Accuracy:  {acc:.3f}")
    print(f"F1 macro:  {f1_macro:.3f}  (umbral de referencia: {UMBRAL_F1_MACRO})")

    if f1_macro >= UMBRAL_F1_MACRO:
        print("\n>>> PASA el umbral: el LSTM puede considerarse para producción "
              "(ver paso 7 del plan: integración a Oracle + dashboard).")
    else:
        print("\n>>> NO alcanza el umbral: se recomienda seguir usando el clasificador "
              "por prompt de Gemini (categorias.py) en producción por ahora.")

    print("\nReporte por categoría:")
    print(classification_report(y_true, y_pred, zero_division=0))

    etiquetas = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=etiquetas)
    df_cm = pd.DataFrame(cm, index=etiquetas, columns=etiquetas)
    cm_path = ARTIFACTS_DIR / "matriz_confusion.csv"
    df_cm.to_csv(cm_path, encoding="utf-8-sig")
    print(f"\nMatriz de confusión guardada en {cm_path}")

    # Peores errores: mal clasificados, ordenados por confianza del modelo (más
    # confiado + equivocado = el patrón de confusión más preocupante)
    confianza_pred = probs[np.arange(len(probs)), y_pred_int]
    df_err = df[["url", "titulo", "categoria"]].copy()
    df_err["categoria_predicha"] = y_pred
    df_err["confianza_modelo"] = confianza_pred
    df_err = df_err[df_err["categoria"] != df_err["categoria_predicha"]]
    df_err = df_err.sort_values("confianza_modelo", ascending=False)

    err_path = ARTIFACTS_DIR / "errores.csv"
    df_err.to_csv(err_path, index=False, encoding="utf-8-sig")
    print(f"Errores de clasificación ({len(df_err)}) guardados en {err_path}")
    if len(df_err) > 0:
        print("\nTop 10 errores más confiados (posibles categorías confusas o ambiguas):")
        print(df_err.head(10)[["titulo", "categoria", "categoria_predicha", "confianza_modelo"]]
              .to_string(index=False))


if __name__ == "__main__":
    run()
