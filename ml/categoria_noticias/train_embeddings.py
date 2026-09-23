"""
train_embeddings.py — Entrena el clasificador de categorías sobre embeddings
de oración multilingües preentrenados (ver embeddings_utils.py), en vez de
tokenizar y aprender un Embedding() desde cero como en train_lstm.py.

Usa el mismo dataset y la misma simplificación de taxonomía (12 clases,
ver preprocesamiento.py) que el experimento LSTM, para que los resultados
sean directamente comparables en evaluar_embeddings.py.

Uso:
  python ml/categoria_noticias/train_embeddings.py
"""

import pickle
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight

from ml.categoria_noticias.preprocesamiento import (
    construir_texto, es_boilerplate_mercado, simplificar_categoria,
)
from ml.categoria_noticias.embeddings_utils import embed_textos

DATA_DIR      = _root.parent / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts_embeddings"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

EPOCHS     = 40
BATCH_SIZE = 32
VAL_SPLIT  = 0.15


def cargar_dataset() -> pd.DataFrame:
    path = DATA_DIR / "categorias_train.csv"
    if not path.exists():
        print(f"ERROR: no existe {path}. Corre antes bootstrap_dataset_categorias.py "
              "y aplicar_revision_categorias.py")
        sys.exit(1)
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.dropna(subset=["categoria"])

    df["categoria"] = df["categoria"].apply(simplificar_categoria)
    df = df.dropna(subset=["categoria"])

    antes = len(df)
    df = df[~df["titulo"].apply(es_boilerplate_mercado)]
    print(f"Filtrados {antes - len(df)} títulos boilerplate de 'market research' "
          f"(quedan {len(df)})")

    df["texto"] = df.apply(
        lambda r: construir_texto(r.get("titulo", ""), r.get("descripcion", "")), axis=1,
    )
    df = df[df["texto"].str.len() > 0]
    return df


def run():
    print("=" * 60)
    print("TYASA BI — Entrenamiento con embeddings preentrenados")
    print("=" * 60)

    df = cargar_dataset()
    print(f"\nDataset de entrenamiento: {len(df)} noticias, "
          f"{df['categoria'].nunique()} categorías")
    print(df["categoria"].value_counts())

    print("\nCalculando embeddings (paraphrase-multilingual-MiniLM-L12-v2)...")
    X = embed_textos(df["texto"].tolist())
    print(f"Embeddings: {X.shape}")

    label_encoder = LabelEncoder()
    y_int = label_encoder.fit_transform(df["categoria"])
    n_clases = len(label_encoder.classes_)

    X_train, X_val, y_train, y_val = train_test_split(
        X, y_int, test_size=VAL_SPLIT, random_state=42, stratify=y_int,
    )
    print(f"\nTrain: {len(X_train)} | Val interno: {len(X_val)}")

    # ── Clasificador de producción: LogisticRegression sobre los embeddings ────
    # En el gold set rindió igual o mejor que una red densa (F1 macro 0.751 vs
    # 0.737) y no necesita TensorFlow en inferencia — solo sentence-transformers
    # (para el embedding) + scikit-learn (ya está en requirements.txt). Este es
    # el modelo que carga ml/categoria_noticias/inferencia.py en producción.
    clasificador = LogisticRegression(max_iter=2000, class_weight="balanced")
    clasificador.fit(X_train, y_train)
    acc_base = clasificador.score(X_val, y_val)
    print(f"\nLogisticRegression sobre embeddings — val interno accuracy: {acc_base:.3f}")

    with open(ARTIFACTS_DIR / "clasificador_lr.pkl", "wb") as f:
        pickle.dump(clasificador, f)
    with open(ARTIFACTS_DIR / "label_encoder.pkl", "wb") as f:
        pickle.dump(label_encoder, f)

    # ── Modelo de referencia/comparación: red densa sobre los embeddings ───────
    # No es el modelo de producción (ver comentario arriba) — se entrena y se
    # guarda solo para comparar contra el LogisticRegression en evaluar_embeddings.py.
    import tensorflow as tf
    from tensorflow.keras.utils import to_categorical
    from tensorflow.keras import layers, models, callbacks

    y_train_cat = to_categorical(y_train, num_classes=n_clases)
    y_val_cat   = to_categorical(y_val, num_classes=n_clases)

    pesos = compute_class_weight("balanced", classes=np.unique(y_train), y=y_train)
    class_weight = {i: w for i, w in enumerate(pesos)}

    modelo = models.Sequential([
        layers.Input(shape=(X.shape[1],)),
        layers.Dense(128, activation="relu"),
        layers.Dropout(0.3),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.2),
        layers.Dense(n_clases, activation="softmax"),
    ])
    modelo.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    modelo.summary()

    early_stop = callbacks.EarlyStopping(
        monitor="val_loss", patience=6, restore_best_weights=True,
    )

    modelo.fit(
        X_train, y_train_cat,
        validation_data=(X_val, y_val_cat),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        class_weight=class_weight,
        callbacks=[early_stop],
        verbose=2,
    )

    val_loss, val_acc = modelo.evaluate(X_val, y_val_cat, verbose=0)
    print(f"\nVal interno (mismo origen que el train, NO es el gold set) — "
          f"accuracy: {val_acc:.3f}, loss: {val_loss:.3f}")

    modelo.save(ARTIFACTS_DIR / "model.keras")

    print(f"\nArtefactos guardados en {ARTIFACTS_DIR}")
    print("  clasificador_lr.pkl  <- modelo de producción (ml/categoria_noticias/inferencia.py)")
    print("  model.keras          <- solo referencia/comparación")
    print("\nSiguiente paso: python ml/categoria_noticias/evaluar_embeddings.py")


if __name__ == "__main__":
    run()
