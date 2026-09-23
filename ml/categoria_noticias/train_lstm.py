"""
train_lstm.py — Entrena un clasificador LSTM de categorías de noticias TYASA.

Patrón: Tokenizer -> secuencias con padding -> Embedding entrenable ->
BiLSTM -> Dropout -> Dense(softmax), con class_weight para compensar el
desbalance entre las 15 categorías (inspirado en
https://github.com/mmalam3/BBC-News-Classification-using-LSTM-and-TensorFlow,
adaptado a español y a texto corto de título+snippet en vez de artículos completos).

Entrena SOLO con data/categorias_train.csv (etiquetas débiles de Gemini).
El desempeño real se mide aparte con evaluar.py sobre data/categorias_gold_val.csv
(las noticias revisadas a mano) — nunca se debe ajustar el modelo mirando el gold set.

Uso:
  python ml/categoria_noticias/train_lstm.py
"""

import json
import pickle
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight

from ml.categoria_noticias.preprocesamiento import (
    construir_texto, es_boilerplate_mercado, limpiar_texto, simplificar_categoria,
)

DATA_DIR      = _root.parent / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

VOCAB_SIZE  = 12000
MAX_LEN     = 60      # títulos + snippet corto rara vez pasan de ~60 tokens
EMBED_DIM   = 100
LSTM_UNITS  = 64
EPOCHS      = 30
BATCH_SIZE  = 32
VAL_SPLIT   = 0.15


def cargar_dataset() -> pd.DataFrame:
    path = DATA_DIR / "categorias_train.csv"
    if not path.exists():
        print(f"ERROR: no existe {path}. Corre antes bootstrap_dataset_categorias.py "
              "y aplicar_revision_categorias.py")
        sys.exit(1)
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.dropna(subset=["categoria"])

    df["categoria"] = df["categoria"].apply(simplificar_categoria)
    df = df.dropna(subset=["categoria"])  # descarta Business/Politics (mapean a None)

    antes = len(df)
    df = df[~df["titulo"].apply(es_boilerplate_mercado)]
    print(f"Filtrados {antes - len(df)} títulos boilerplate de 'market research' "
          f"(quedan {len(df)})")

    df["texto"] = df.apply(
        lambda r: limpiar_texto(construir_texto(r.get("titulo", ""), r.get("descripcion", ""))),
        axis=1,
    )
    df = df[df["texto"].str.len() > 0]
    return df


def run():
    print("=" * 60)
    print("TYASA BI — Entrenamiento LSTM categorías de noticias")
    print("=" * 60)

    df = cargar_dataset()
    print(f"\nDataset de entrenamiento: {len(df)} noticias, "
          f"{df['categoria'].nunique()} categorías")
    print(df["categoria"].value_counts())

    # Importar TF aquí (no al tope del módulo) para que el resto de la app
    # nunca pague el costo de import de TensorFlow si no se está entrenando.
    import tensorflow as tf
    from tensorflow.keras.preprocessing.text import Tokenizer
    from tensorflow.keras.preprocessing.sequence import pad_sequences
    from tensorflow.keras.utils import to_categorical
    from tensorflow.keras import layers, models, callbacks

    label_encoder = LabelEncoder()
    y_int = label_encoder.fit_transform(df["categoria"])
    n_clases = len(label_encoder.classes_)
    y = to_categorical(y_int, num_classes=n_clases)

    tokenizer = Tokenizer(num_words=VOCAB_SIZE, oov_token="<OOV>")
    tokenizer.fit_on_texts(df["texto"])
    secuencias = tokenizer.texts_to_sequences(df["texto"])
    X = pad_sequences(secuencias, maxlen=MAX_LEN, padding="post", truncating="post")

    X_train, X_val, y_train, y_val, y_int_train, _ = train_test_split(
        X, y, y_int, test_size=VAL_SPLIT, random_state=42, stratify=y_int,
    )
    print(f"\nTrain: {len(X_train)} | Val interno: {len(X_val)}")

    pesos = compute_class_weight("balanced", classes=np.unique(y_int_train), y=y_int_train)
    class_weight = {i: w for i, w in enumerate(pesos)}

    modelo = models.Sequential([
        layers.Embedding(input_dim=VOCAB_SIZE, output_dim=EMBED_DIM, input_length=MAX_LEN),
        layers.Bidirectional(layers.LSTM(LSTM_UNITS)),
        layers.Dropout(0.5),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.3),
        layers.Dense(n_clases, activation="softmax"),
    ])
    modelo.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    modelo.summary()

    early_stop = callbacks.EarlyStopping(
        monitor="val_loss", patience=4, restore_best_weights=True,
    )

    modelo.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        class_weight=class_weight,
        callbacks=[early_stop],
        verbose=2,
    )

    val_loss, val_acc = modelo.evaluate(X_val, y_val, verbose=0)
    print(f"\nVal interno (mismo origen que el train, NO es el gold set) — "
          f"accuracy: {val_acc:.3f}, loss: {val_loss:.3f}")

    # Guardar artefactos
    modelo.save(ARTIFACTS_DIR / "model.keras")
    with open(ARTIFACTS_DIR / "tokenizer.json", "w", encoding="utf-8") as f:
        f.write(tokenizer.to_json())
    with open(ARTIFACTS_DIR / "label_encoder.pkl", "wb") as f:
        pickle.dump(label_encoder, f)
    with open(ARTIFACTS_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump({"max_len": MAX_LEN, "vocab_size": VOCAB_SIZE}, f)

    print(f"\nArtefactos guardados en {ARTIFACTS_DIR}")
    print("\nSiguiente paso: python ml/categoria_noticias/evaluar.py "
          "(mide el desempeño real sobre las noticias revisadas a mano)")


if __name__ == "__main__":
    run()
