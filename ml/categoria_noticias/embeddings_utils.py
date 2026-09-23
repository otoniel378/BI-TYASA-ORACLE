"""
embeddings_utils.py — Embeddings de oración multilingües preentrenados
(paraphrase-multilingual-MiniLM-L12-v2, 384 dim, cubre 50+ idiomas incluidos
español e inglés) para el clasificador de categorías.

Por qué esto en vez de que la red aprenda las palabras desde cero (train_lstm.py):
las noticias de TYASA mezclan español e inglés (RSS en ambos idiomas + NewsAPI
solo en inglés), y con ~1700 ejemplos no hay forma de que un Embedding()
entrenado desde cero aprenda representaciones útiles de vocabulario en dos
idiomas. Un modelo preentrenado en cientos de millones de oraciones ya "sabe"
qué palabras son similares entre sí (en cualquiera de los dos idiomas) — el
clasificador que se entrena encima solo tiene que aprender a mapear esas
representaciones a las 12 categorías, con muchos menos ejemplos.

Cachea embeddings en disco por hash del texto para no recalcularlos entre
corridas (train_embeddings.py / evaluar_embeddings.py).
"""

import hashlib
import json
from pathlib import Path

import numpy as np

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_CACHE_DIR = Path(__file__).resolve().parent / "artifacts_embeddings" / "cache_vectores"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_modelo = None


def _get_modelo():
    global _modelo
    if _modelo is None:
        from sentence_transformers import SentenceTransformer
        _modelo = SentenceTransformer(_MODEL_NAME)
    return _modelo


def _cache_path(texto: str) -> Path:
    h = hashlib.md5(texto.encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{h}.json"


def embed_textos(textos: list[str], batch_size: int = 64) -> np.ndarray:
    """Devuelve un array (n, 384) de embeddings — usa caché en disco por texto."""
    resultado: list[np.ndarray | None] = [None] * len(textos)
    faltantes_idx: list[int] = []
    faltantes_textos: list[str] = []

    for i, t in enumerate(textos):
        p = _cache_path(t)
        if p.exists():
            resultado[i] = np.array(json.loads(p.read_text(encoding="utf-8")))
        else:
            faltantes_idx.append(i)
            faltantes_textos.append(t)

    if faltantes_textos:
        modelo = _get_modelo()
        nuevos = modelo.encode(faltantes_textos, batch_size=batch_size, show_progress_bar=False)
        for idx, texto, vec in zip(faltantes_idx, faltantes_textos, nuevos):
            resultado[idx] = vec
            _cache_path(texto).write_text(json.dumps(vec.tolist()), encoding="utf-8")

    return np.vstack(resultado)
