"""
categorias.py — Clasificación temática de noticias siderúrgicas para TYASA.

Asigna a cada noticia UNA de 11 categorías de negocio. Esta es la MISMA taxonomía
que usa el clasificador local de producción (ml/categoria_noticias/inferencia.py,
embeddings preentrenados + LogisticRegression, F1 macro 0.75 en gold set) — antes
había 15 categorías, pero "Business"/"Politics" se retiraron por falta de señal
(eran cajón de sastre sin datos suficientes) y dos pares que se confundían
sistemáticamente se fusionaron: "T-MEC y Tratados"+"Defensa Comercial" ->
"Comercio y Aranceles", "Mercado Global"+"Precios y Materias Primas" ->
"Mercado Global y Precios" (ver ml/categoria_noticias/preprocesamiento.py).

Este módulo (Gemini) ya NO se usa en el pipeline diario de producción — quedó
como ruta de respaldo/manual (botón "Análisis en Tiempo Real" del dashboard) y
como etiquetador débil para generar datasets de entrenamiento nuevos.

Mismo patrón de caché y llamada a Gemini que sentimiento.py (caché local por
hash de URL + fecha, SDK google-genai con fallback REST).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# ── Caché ─────────────────────────────────────────────────────────────────────
_ROOT     = Path(__file__).resolve().parents[3]
_CAT_DIR  = _ROOT / "cache" / "categorias"
_CAT_DIR.mkdir(parents=True, exist_ok=True)

# ── Taxonomía (11 categorías, unificada con el modelo local) ─────────────────
CATEGORIAS_TODAS = [
    "Mercado Global y Precios",
    "Tecnología",
    "Comercio y Aranceles",
    "Nearshoring",
    "Sustentabilidad",
    "Socios Siderúrgicos",
    "Macroeconomía",
    "Logística Nacional",
    "Geopolítica y Logística",
    "Descarbonización",
    "Sectores Consumidores",
]

# Fallback cuando Gemini no responde o no se puede parsear su respuesta.
_CATEGORIA_DEFAULT = "Mercado Global y Precios"

# ── System prompt específico para TYASA EAF ───────────────────────────────────
_SYSTEM_CATEGORIA = """Eres analista senior de mercados para TYASA, acería mexicana que produce \
acero plano (HRC, CRC, galvanizado) mediante horno eléctrico de arco (EAF).

Tu tarea es clasificar cada noticia en EXACTAMENTE UNA de las 11 categorías de negocio
que usa TYASA para organizar su monitoreo de mercado.
Elige la categoría que mejor describe el TEMA CENTRAL de la noticia, no el sentimiento.

REGLA CLAVE: elige siempre la categoría MÁS ESPECÍFICA que aplique.
Ejemplos: una inversión de una automotriz en México es "Nearshoring". Una noticia
sobre aranceles, T-MEC o defensa comercial (dumping, cuotas) es "Comercio y Aranceles".
Una noticia sobre acero verde/CO2/hidrógeno es "Descarbonización", no "Tecnología"."""

_PROMPT_TMPL = """Clasifica esta noticia en UNA sola categoría de la siguiente lista cerrada:

{categorias}

Título: {titulo}
Fuente: {fuente}
Fecha: {fecha}
Descripción: {descripcion}

Responde ÚNICAMENTE con este JSON exacto (sin markdown, sin texto extra):
{{
  "categoria": "una de las categorías exactas de la lista",
  "confianza": "Alta" | "Media" | "Baja"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
def _hash_noticia(url: str) -> str:
    hoy = date.today().isoformat()
    return hashlib.md5(f"{url}|{hoy}".encode()).hexdigest()[:16]


def _cache_load(h: str) -> dict | None:
    p = _CAT_DIR / f"{h}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _cache_save(h: str, data: dict) -> None:
    (_CAT_DIR / f"{h}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _parse_json(raw: str) -> dict | None:
    try:
        clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("`").strip()
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return None


def _normalizar_categoria(cat: str) -> str:
    """Ajusta la categoría devuelta por Gemini a la etiqueta exacta de la taxonomía
    (Gemini a veces devuelve variantes de mayúsculas/acentos)."""
    if not cat:
        return _CATEGORIA_DEFAULT
    cat = cat.strip()
    for c in CATEGORIAS_TODAS:
        if c.lower() == cat.lower():
            return c
    # Coincidencia parcial (ej. "Nearshoring México" -> "Nearshoring")
    for c in CATEGORIAS_TODAS:
        if c.lower() in cat.lower() or cat.lower() in c.lower():
            return c
    return _CATEGORIA_DEFAULT


# ─────────────────────────────────────────────────────────────────────────────
def clasificar_categoria_noticia(
    noticia: dict,
    gemini_key: str,
    model: str = "gemini-3.5-flash",
    force_refresh: bool = False,
) -> dict:
    """
    Clasifica la categoría temática de una noticia individual.
    Retorna dict con: categoria, confianza.
    """
    url   = noticia.get("url", "")
    h     = _hash_noticia(url)
    cache = _cache_load(h)
    if cache and not force_refresh:
        cache["_cached"] = True
        return cache

    prompt = _PROMPT_TMPL.format(
        categorias  = " | ".join(CATEGORIAS_TODAS),
        titulo      = (noticia.get("titulo", "") or "")[:300],
        fuente      = (noticia.get("fuente", "") or "")[:80],
        fecha       = (noticia.get("fecha_pub", "") or "")[:10],
        descripcion = (noticia.get("descripcion", "") or "")[:400],
    )

    resultado = _llamar_gemini(prompt, gemini_key, model)
    fallo = resultado is None
    if fallo:
        resultado = {"categoria": _CATEGORIA_DEFAULT, "confianza": "Baja"}

    resultado["categoria"] = _normalizar_categoria(resultado.get("categoria", ""))
    resultado["_cached"]   = False
    resultado["url"]       = url
    resultado["titulo"]    = (noticia.get("titulo", "") or "")[:300]
    resultado["descripcion"] = (noticia.get("descripcion", "") or "")[:1000]
    resultado["fuente"]    = (noticia.get("fuente", "") or "")[:100]
    resultado["fecha_pub"] = (noticia.get("fecha_pub", "") or "")[:10]
    resultado["grupo"]     = noticia.get("grupo", "")

    # No cachear resultados por defecto (Gemini falló) — si se cachearan, un
    # reintento el mismo día devolvería el mismo default en vez de reintentar.
    if not fallo:
        _cache_save(h, resultado)
    return resultado


def _llamar_gemini(prompt: str, api_key: str, model: str) -> dict | None:
    # Intento SDK google-genai
    try:
        from google import genai                          # type: ignore
        from google.genai import types as genai_types    # type: ignore
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=_SYSTEM_CATEGORIA,
                temperature=0.1,
                max_output_tokens=256,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (resp.text or "").strip()
        return _parse_json(raw) if raw else None
    except ImportError:
        pass
    except Exception as e:
        print(f"[categorias] SDK error: {e}")

    # Fallback REST
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": _SYSTEM_CATEGORIA}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 256},
        }
        resp = requests.post(url, json=body, timeout=25)
        if resp.status_code != 200:
            print(f"[categorias] REST HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return _parse_json(raw)
    except Exception as e:
        print(f"[categorias] REST error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
def clasificar_categoria_lote(
    noticias: list[dict],
    gemini_key: str,
    model: str = "gemini-3.5-flash",
    max_noticias: int | None = None,
) -> list[dict]:
    """Clasifica un lote de noticias por categoría. Respeta caché — solo llama Gemini
    para noticias nuevas. max_noticias=None procesa la lista completa (usado por el
    script de bootstrap del dataset)."""
    lote = noticias if max_noticias is None else noticias[:max_noticias]
    resultados = []
    for n in lote:
        try:
            r = clasificar_categoria_noticia(n, gemini_key, model=model)
            resultados.append(r)
            if not r.get("_cached"):
                time.sleep(0.5)  # margen defensivo contra rate limit por ráfaga
        except Exception as e:
            print(f"[categorias] Error clasificando {n.get('url','')[:50]}: {e}")
    return resultados


# ─────────────────────────────────────────────────────────────────────────────
def resultados_a_dataframe(resultados: list[dict]) -> pd.DataFrame:
    """Convierte lista de resultados de categorización a DataFrame."""
    if not resultados:
        return pd.DataFrame()
    rows = []
    for r in resultados:
        rows.append({
            "hash_url":    _hash_noticia(r.get("url", "")),
            "titulo":      (r.get("titulo", "") or "")[:500],
            "descripcion": (r.get("descripcion", "") or "")[:1000],
            "fuente":      (r.get("fuente", "") or "")[:200],
            "url":         (r.get("url", "") or "")[:500],
            "fecha_pub":   r.get("fecha_pub", "")[:10] or None,
            "grupo":       (r.get("grupo", "") or "")[:100],
            "categoria_gemini": r.get("categoria", _CATEGORIA_DEFAULT),
            "confianza":   (r.get("confianza", "Baja") or "Baja")[:20],
        })
    return pd.DataFrame(rows)
