"""
preprocesamiento.py — Limpieza de texto compartida entre entrenamiento y
evaluación del clasificador de categorías. Los textos de entrada son cortos
(título + snippet RSS), así que la limpieza es deliberadamente ligera: no se
quitan stopwords en español porque en textos cortos suelen llevar señal
(negaciones, preposiciones que distinguen "acero PARA construcción" de
"acero DE construcción", etc.).
"""

import re

# Títulos de "market research" sindicados (MarketsandMarkets, Fortune Business
# Insights, Market Data Forecast, etc.) repiten la misma plantilla genérica
# ("X Market Size, Share, Trends... Report, 2030") sin importar el tema real —
# título+snippet no traen señal suficiente para distinguirlos, y contaminan el
# entrenamiento (el modelo aprende a mapear la plantilla a una sola categoría
# "cajón de sastre" en vez de aprender el tema real).
_BOILERPLATE_RE = re.compile(
    r"market\s+(size|share|report|forecast|analysis|growth|trends|data)",
    re.IGNORECASE,
)


def es_boilerplate_mercado(titulo: str) -> bool:
    return bool(_BOILERPLATE_RE.search(titulo or ""))


# ── Simplificación de taxonomía SOLO para el experimento LSTM ────────────────
# La matriz de confusión del primer entrenamiento (ver ml/categoria_noticias/
# artifacts/matriz_confusion.csv) mostró dos pares con traslape fuerte y
# consistente (no ruido aleatorio):
#   - T-MEC y Tratados <-> Defensa Comercial   (10 cruces entre sí)
#   - Mercado Global <-> Precios y Materias Primas (14 cruces, un solo sentido)
# Se fusionan solo para entrenar/evaluar el LSTM — la taxonomía de 15
# categorías de categorias.py (Gemini, producción) NO cambia.
# Business y Politics se excluyen del LSTM: su matriz de confusión no muestra
# ningún patrón dominante (errores repartidos al azar entre todas las demás
# categorías), señal de que con el texto disponible no hay nada que aprender,
# no de que falte volumen.
MAPEO_LSTM: dict[str, str | None] = {
    "T-MEC y Tratados":          "Comercio y Aranceles",
    "Defensa Comercial":         "Comercio y Aranceles",
    "Mercado Global":            "Mercado Global y Precios",
    "Precios y Materias Primas": "Mercado Global y Precios",
    "Business":                  None,
    "Politics":                  None,
}


def simplificar_categoria(categoria: str) -> str | None:
    """Aplica MAPEO_LSTM; None significa 'excluir esta fila del LSTM'."""
    return MAPEO_LSTM.get(categoria, categoria)


def construir_texto(titulo: str, descripcion: str) -> str:
    """Concatena título + descripción — es todo el texto disponible por noticia."""
    titulo = (titulo or "").strip()
    descripcion = (descripcion or "").strip()
    if titulo and descripcion:
        return f"{titulo}. {descripcion}"
    return titulo or descripcion


def limpiar_texto(texto: str) -> str:
    texto = (texto or "").lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-záéíóúüñ0-9%\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto
