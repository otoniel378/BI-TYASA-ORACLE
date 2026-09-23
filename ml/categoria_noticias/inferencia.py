"""
inferencia.py — Clasificador de categoría de PRODUCCIÓN para el pipeline diario
(scripts/update_sentimiento_noticias.py). Reemplaza las llamadas a Gemini
(categorias.py) para esta tarea: embeddings de oración multilingües
preentrenados (embeddings_utils.py) + LogisticRegression entrenado en
train_embeddings.py (F1 macro 0.74 en gold set revisado a mano).

Gratis y local — no consume cuota de Gemini ni depende de la red para
clasificar (solo la primera vez, para descargar el modelo de embeddings).

Requiere los artefactos de ml/categoria_noticias/artifacts_embeddings/
(clasificador_lr.pkl, label_encoder.pkl) generados por train_embeddings.py.
"""

from __future__ import annotations

import pickle
from pathlib import Path

from ml.categoria_noticias.preprocesamiento import construir_texto
from ml.categoria_noticias.embeddings_utils import embed_textos

_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts_embeddings"

_clasificador = None
_label_encoder = None


def _cargar_artefactos():
    global _clasificador, _label_encoder
    if _clasificador is None:
        with open(_ARTIFACTS_DIR / "clasificador_lr.pkl", "rb") as f:
            _clasificador = pickle.load(f)
        with open(_ARTIFACTS_DIR / "label_encoder.pkl", "rb") as f:
            _label_encoder = pickle.load(f)
    return _clasificador, _label_encoder


def clasificar_categoria_lote_local(noticias: list[dict]) -> list[dict]:
    """
    Clasifica la categoría de un lote de noticias con el modelo local.
    Retorna una lista de dicts con: url, categoria, confianza (Alta/Media/Baja),
    mismo shape de salida que clasificar_categoria_lote() de categorias.py para
    que update_sentimiento_noticias.py pueda usarlas indistintamente.
    """
    if not noticias:
        return []

    clasificador, label_encoder = _cargar_artefactos()

    textos = [
        construir_texto(n.get("titulo", ""), n.get("descripcion", ""))
        for n in noticias
    ]
    X = embed_textos(textos)

    probs = clasificador.predict_proba(X)
    import numpy as np
    idx_pred = np.argmax(probs, axis=1)
    categorias_pred = label_encoder.inverse_transform(idx_pred)
    confianzas = probs[np.arange(len(probs)), idx_pred]

    resultados = []
    for n, cat, conf in zip(noticias, categorias_pred, confianzas):
        nivel_confianza = "Alta" if conf >= 0.6 else ("Media" if conf >= 0.35 else "Baja")
        resultados.append({
            "url":       n.get("url", ""),
            "categoria": cat,
            "confianza": nivel_confianza,
            "confianza_score": float(conf),
        })
    return resultados
