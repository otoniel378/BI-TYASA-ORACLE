"""
ai_analysis.py — Análisis inteligente de sentimiento de mercado.

Flujo:
  1. Recibe lista de noticias (dicts con titulo/descripcion/url)
  2. Opcionalmente scrapea el contenido completo del artículo (trafilatura → BS4)
  3. Construye prompt de analista senior de commodities
  4. Llama a Gemini API (gemini-2.0-flash o gemini-1.5-flash)
  5. Cachea el resultado en cache/ai_summaries/<hash>.json para no repetir llamadas

Cache key: MD5(variable + str(round(sigma, 1)) + fecha_hoy)
"""

from __future__ import annotations
import hashlib
import json
import os
import re
import time
from datetime import datetime, date
from pathlib import Path

import requests

# ── Ruta de caché ─────────────────────────────────────────────────────────────
_ROOT_DIR   = Path(__file__).resolve().parents[2]          # raíz del proyecto
CACHE_DIR   = _ROOT_DIR / "cache" / "ai_summaries"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Timeout HTTP general ───────────────────────────────────────────────────────
HTTP_TIMEOUT = 10  # segundos

# ── Modelos Gemini disponibles (en orden de preferencia) ──────────────────────
_DEFAULT_MODEL   = "gemini-3.5-flash"
_FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash")

# ══════════════════════════════════════════════════════════════════════════════
# SCRAPING DE ARTÍCULOS
# ══════════════════════════════════════════════════════════════════════════════

def _scrape_trafilatura(url: str) -> str:
    """Extrae texto del artículo usando trafilatura (mejor calidad)."""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False,
                                        include_tables=False)
            return (text or "").strip()
    except ImportError:
        pass
    except Exception:
        pass
    return ""


def _scrape_bs4(url: str) -> str:
    """Fallback: extrae texto con requests + BeautifulSoup4."""
    try:
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TyasaBI/1.0)"}
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.content, "html.parser")
        # Eliminar script, style, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        # Extraer párrafos
        paras = [p.get_text(separator=" ").strip()
                 for p in soup.find_all("p") if len(p.get_text()) > 60]
        return " ".join(paras[:30])          # máx ~30 párrafos
    except ImportError:
        pass
    except Exception:
        pass
    return ""


def scrape_articulo(url: str, max_chars: int = 2000) -> str:
    """
    Intenta trafilatura primero, BS4 de fallback.
    Trunca a max_chars para no sobrepasar el contexto del LLM.
    """
    if not url or not url.startswith("http"):
        return ""
    text = _scrape_trafilatura(url) or _scrape_bs4(url)
    return text[:max_chars] if text else ""


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL PROMPT
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """Eres un analista senior de commodities con 20 años de experiencia \
en mercados de acero, energía, fletes y divisas emergentes. Trabajas para TYASA, \
acería mexicana que produce acero plano vía horno eléctrico de arco.

Tu tarea: analizar el movimiento inusual de una variable de mercado y generar \
un resumen ejecutivo conciso en español para el equipo directivo."""

_USER_TEMPLATE = """## Variable: {variable}
- Sigma actual: {sigma:+.2f}σ  (movimiento {sigma_desc})
- Cambio 7 días: {cambio7:+.1f}%
- Valor actual: {valor:.2f}  |  Media histórica base: {media_base:.2f}
- Tendencia: {tendencia}

## Noticias recientes ({n_noticias} artículos):
{noticias_txt}

---
Con base en lo anterior, genera un análisis ejecutivo con EXACTAMENTE este formato JSON \
(sin markdown extra, solo el JSON):

{{
  "puntos_clave": [
    "Punto 1 (máx 25 palabras)",
    "Punto 2 (máx 25 palabras)",
    "Punto 3 (máx 25 palabras)",
    "Punto 4 (máx 25 palabras)",
    "Punto 5 (máx 25 palabras)"
  ],
  "driver_principal": "Oferta | Demanda | Geopolitica | Macro | Sectorial",
  "sentimiento": "Alcista | Bajista | Neutral",
  "confianza": "Alta | Media | Baja",
  "impacto_tyasa": "una oración de máx 30 palabras sobre el impacto directo en TYASA"
}}"""


def _build_prompt(
    variable: str,
    sigma: float,
    cambio7: float,
    valor: float,
    media_base: float,
    tendencia: str,
    noticias: list[dict],
    scrape: bool = False,
) -> str:
    sigma_desc = (
        "EXTREMO — posible crisis"    if abs(sigma) >= 4 else
        "muy alto — alerta crítica"   if abs(sigma) >= 3 else
        "alto — vigilancia activa"    if abs(sigma) >= 2 else
        "moderado"
    )

    lineas = []
    for i, n in enumerate(noticias[:10], 1):
        titulo = (n.get("titulo", "") or "").strip()
        desc   = (n.get("descripcion", "") or "").strip()[:180]
        fecha  = (n.get("fecha_pub", "") or "").strip()
        body   = ""
        if scrape and n.get("url"):
            body = scrape_articulo(n["url"], max_chars=800)

        linea = f"{i}. [{fecha}] {titulo}"
        if desc:
            linea += f"\n   {desc}"
        if body:
            linea += f"\n   [Contenido] {body[:400]}"
        lineas.append(linea)

    noticias_txt = "\n".join(lineas) if lineas else "(Sin noticias disponibles)"

    return _USER_TEMPLATE.format(
        variable    = variable.replace("_", " "),
        sigma       = sigma,
        sigma_desc  = sigma_desc,
        cambio7     = cambio7,
        valor       = valor,
        media_base  = media_base,
        tendencia   = tendencia,
        n_noticias  = len(noticias[:10]),
        noticias_txt = noticias_txt,
    )


# ══════════════════════════════════════════════════════════════════════════════
# LLAMADA A GEMINI API
# ══════════════════════════════════════════════════════════════════════════════

def _models_to_try(model: str) -> tuple:
    """Devuelve lista única de modelos a intentar, poniendo el solicitado primero."""
    seen: dict = {}
    for m in (model,) + _FALLBACK_MODELS:
        seen[m] = None
    return tuple(seen)


def _call_gemini(prompt: str, api_key: str, model: str = _DEFAULT_MODEL) -> dict | None:
    """
    Llama a Gemini via google-genai SDK (nuevo) con fallback a REST directo.
    Prueba varios modelos si el principal no está disponible.
    Retorna dict con los campos del análisis, o None si falla.
    """
    models = _models_to_try(model)

    # Intentar con SDK google-genai
    try:
        from google import genai                          # type: ignore
        from google.genai import types as genai_types    # type: ignore
        client = genai.Client(api_key=api_key)

        for m in models:
            try:
                cfg_kwargs: dict = dict(
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=0.3,
                    max_output_tokens=2048,
                )
                try:
                    cfg_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)
                except Exception:
                    pass
                resp = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(**cfg_kwargs),
                )
                raw = resp.text.strip() if resp.text else ""
                if raw:
                    return _parse_json_response(raw)
            except Exception as e:
                print(f"[ai_analysis] SDK {m} error: {e}")
    except ImportError:
        pass  # SDK no instalado → usar requests

    # Fallback: REST directo (no requiere SDK)
    for m in models:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{m}:generateContent?key={api_key}"
            )
            body = {
                "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
            }
            resp = requests.post(url, json=body, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                raw  = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return _parse_json_response(raw)
            print(f"[ai_analysis] REST {m} {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            print(f"[ai_analysis] REST error ({m}): {e}")
    return None


def _parse_json_response(raw: str) -> dict | None:
    """Extrae JSON del texto crudo del LLM (puede venir dentro de ```json ... ```)."""
    try:
        # Eliminar bloques markdown ```json ... ```
        clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("`").strip()
        # Buscar el primer { ... }
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"[ai_analysis] JSON parse error: {e}\nRaw: {raw[:300]}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CACHÉ JSON
# ══════════════════════════════════════════════════════════════════════════════

def _cache_key(variable: str, sigma: float) -> str:
    hoy   = date.today().isoformat()
    sigma_r = round(sigma, 1)
    raw   = f"{variable}|{sigma_r}|{hoy}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _cache_load(key: str) -> dict | None:
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _cache_save(key: str, data: dict) -> None:
    path = CACHE_DIR / f"{key}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ai_analysis] Cache write error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════════════════

def analizar_alerta(
    variable: str,
    sigma: float,
    cambio7: float,
    valor: float,
    media_base: float,
    tendencia: str,
    noticias: list[dict],
    api_key: str,
    model: str = _DEFAULT_MODEL,
    scrape_articles: bool = False,
    force_refresh: bool = False,
) -> dict | None:
    """
    Función principal. Retorna dict con:
      - puntos_clave: list[str]   (5 puntos)
      - driver_principal: str     (Oferta/Demanda/Geopolitica/Macro/Sectorial)
      - sentimiento: str          (Alcista/Bajista/Neutral)
      - confianza: str            (Alta/Media/Baja)
      - impacto_tyasa: str
      - _cached: bool             (True si vino del caché)
      - _error: str | None

    Retorna None si no hay API key.
    """
    if not api_key:
        return None

    ckey   = _cache_key(variable, sigma)
    cached = _cache_load(ckey)
    if cached and not force_refresh:
        cached["_cached"] = True
        return cached

    prompt = _build_prompt(
        variable, sigma, cambio7, valor, media_base, tendencia, noticias,
        scrape=scrape_articles,
    )

    resultado = _call_gemini(prompt, api_key, model=model)

    if resultado:
        resultado["_cached"] = False
        resultado["_error"]  = None
        _cache_save(ckey, resultado)
        return resultado

    return {
        "puntos_clave":     [],
        "driver_principal": "—",
        "sentimiento":      "—",
        "confianza":        "—",
        "impacto_tyasa":    "No se pudo generar el análisis. Verifica la API key y la conexión.",
        "_cached":          False,
        "_error":           "Gemini no respondió o la respuesta no pudo ser parseada.",
    }


# ════════════════════════════════════════════════════════════════════════════
# CHAT / TEXTO LIBRE
# ════════════════════════════════════════════════════════════════════════════

_SYSTEM_CHAT = (
    "Eres un analista senior de commodities y mercados de acero con 20 años de "
    "experiencia. Trabajas para TYASA, acería mexicana con horno eléctrico de arco. "
    "Responde de forma concisa, técnica y en español. Máximo 3 párrafos cortos."
)


def _call_gemini_text(
    prompt: str,
    api_key: str,
    system: str = _SYSTEM_CHAT,
    model: str = _DEFAULT_MODEL,
    max_output_tokens: int = 600,
    temperature: float = 0.5,
) -> str:
    """Llama a Gemini y retorna texto libre (para chat y síntesis abierta).
    Prueba varios modelos si el principal no está disponible."""
    models = _models_to_try(model)

    # SDK google-genai
    try:
        from google import genai                       # type: ignore
        from google.genai import types as genai_types  # type: ignore
        client = genai.Client(api_key=api_key)

        for m in models:
            try:
                cfg_kwargs: dict = dict(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
                try:
                    cfg_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)
                except Exception:
                    pass
                resp = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(**cfg_kwargs),
                )
                return (resp.text or "").strip() or "Sin respuesta."
            except Exception as e:
                print(f"[ai_analysis] _call_gemini_text SDK {m} error: {e}")
    except ImportError:
        pass

    # REST fallback
    for m in models:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{m}:generateContent?key={api_key}"
            )
            body = {
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_output_tokens,
                },
            }
            resp = requests.post(url, json=body, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"[ai_analysis] REST {m} {resp.status_code}: {resp.text[:200]}")
        except Exception as e2:
            print(f"[ai_analysis] _call_gemini_text REST error ({m}): {e2}")
    return "Error al consultar la IA."


# ════════════════════════════════════════════════════════════════════════════
# SÍNTESIS INDUSTRIAL (Monitor Siderúrgico)
# ════════════════════════════════════════════════════════════════════════════

_SINTESIS_TMPL = """Eres analista senior de la industria siderúrgica para TYASA México (acería EAF).

Con base en las siguientes noticias recientes de la industria, genera una síntesis ejecutiva
en JSON con EXACTAMENTE este formato (sin markdown extra):

{{
  "impacto_precios": "2-3 oraciones sobre movimientos de precios HRC/CRC/insumos/fletes",
  "tendencias_mexico": "2-3 oraciones sobre el mercado mexicano: inversiones, nearshoring, demanda",
  "riesgos_globales": "2-3 oraciones sobre riesgos: sobrecapacidad China, aranceles, demanda global",
  "nivel_alerta": "Alto | Medio | Bajo",
  "recomendacion": "una oración de acción concreta para el equipo comercial de TYASA"
}}

## Noticias recientes ({n} artículos):
{noticias_txt}
"""


def sintesis_industrial(
    noticias_por_grupo: dict[str, list[dict]],
    api_key: str,
    model: str = _DEFAULT_MODEL,
    force_refresh: bool = False,
) -> dict | None:
    """
    Síntesis de industria siderúrgica. Caché diario en disco.
    Retorna dict: impacto_precios, tendencias_mexico, riesgos_globales,
                  nivel_alerta, recomendacion, _cached, _error
    """
    hoy  = date.today().isoformat()
    ckey = hashlib.md5(f"industria|{hoy}".encode()).hexdigest()[:16]

    cached = _cache_load(ckey)
    if cached and not force_refresh:
        cached["_cached"] = True
        return cached

    todos: list[str] = []
    for grupo, noticias in noticias_por_grupo.items():
        for n in noticias[:4]:
            titulo = (n.get("titulo", "") or "").strip()
            desc   = (n.get("descripcion", "") or "").strip()[:100]
            fecha  = (n.get("fecha_pub", "") or "")
            todos.append(f"[{grupo}·{fecha}] {titulo}. {desc}")

    noticias_txt = "\n".join(todos[:20]) if todos else "(sin noticias disponibles)"
    prompt = _SINTESIS_TMPL.format(n=len(todos), noticias_txt=noticias_txt)

    resultado = _call_gemini(prompt, api_key, model=model)
    if resultado:
        resultado["_cached"] = False
        resultado["_error"]  = None
        _cache_save(ckey, resultado)
        return resultado

    return {
        "impacto_precios":   "No se pudo generar la síntesis.",
        "tendencias_mexico": "",
        "riesgos_globales":  "",
        "nivel_alerta":      "—",
        "recomendacion":     "",
        "_cached": False,
        "_error":  "Gemini no respondió o la respuesta no pudo ser parseada.",
    }


# ════════════════════════════════════════════════════════════════════════════
# SÍNTESIS GLOBAL — Resumen ejecutivo con referencias a noticias (10 categorías)
# ════════════════════════════════════════════════════════════════════════════

_GLOBAL_SYSTEM = (
    "Eres analista sénior de la industria siderúrgica para TYASA México "
    "(acería EAF, produce lámina negra, galvanizado y SBQ). "
    "Responde SIEMPRE con JSON válido únicamente, sin texto antes ni después del JSON."
)

_GLOBAL_TMPL = """Hoy es {hoy}. Eres analista senior de TYASA México. Analiza las noticias de TODAS las siguientes categorías y genera un resumen ejecutivo completo.

CATEGORÍAS ANALIZADAS: {categorias}

NOTICIAS POR CATEGORÍA (título | URL | fuente | fecha):
{noticias_txt}

Genera EXCLUSIVAMENTE este JSON (sin markdown, sin explicaciones adicionales):
{{
  "estado_mercado": "2-3 oraciones sobre precios HRC/CRC/chatarra, demanda global y tendencias relevantes",
  "impacto_mexico": "2-3 oraciones sobre T-MEC, nearshoring, costos CFE/gas, logística, aranceles y demanda local para TYASA",
  "nivel_alerta": "Medio",
  "resumen_por_area": [
    {{"area": "NOMBRE EXACTO DE LA CATEGORÍA", "resumen": "1 oración con el hallazgo más relevante", "ref_url": "https://url-del-articulo-fuente", "ref_titulo": "título corto del artículo"}},
    {{"area": "...", "resumen": "...", "ref_url": "https://...", "ref_titulo": "..."}}
  ],
  "riesgos": [
    {{"texto": "riesgo en máx 18 palabras — puede ser de CUALQUIER categoría incluida Logística", "ref_titulo": "título corto", "ref_url": "https://..."}},
    {{"texto": "segundo riesgo", "ref_titulo": "...", "ref_url": "https://..."}},
    {{"texto": "tercer riesgo", "ref_titulo": "...", "ref_url": "https://..."}},
    {{"texto": "cuarto riesgo si hay algo relevante", "ref_titulo": "...", "ref_url": "https://..."}}
  ],
  "oportunidades": [
    {{"texto": "oportunidad en máx 18 palabras — puede ser de CUALQUIER categoría", "ref_titulo": "título corto", "ref_url": "https://..."}},
    {{"texto": "segunda oportunidad", "ref_titulo": "...", "ref_url": "https://..."}},
    {{"texto": "tercera oportunidad", "ref_titulo": "...", "ref_url": "https://..."}},
    {{"texto": "cuarta oportunidad si hay algo relevante", "ref_titulo": "...", "ref_url": "https://..."}}
  ],
  "recomendacion": "acción concreta para TYASA esta semana integrando logística, precios y política comercial — máx 35 palabras"
}}

REGLAS CRÍTICAS:
- "resumen_por_area" DEBE ser un ARRAY con un objeto por CADA categoría de CATEGORÍAS ANALIZADAS
- Cada objeto en resumen_por_area DEBE incluir "ref_url" con la URL literal de una noticia de esa categoría
- Los riesgos y oportunidades deben cubrir al menos 3 categorías distintas
- Si hay bloqueos, accidentes o disrupciones en Logística Nacional, DEBEN aparecer en riesgos
- nivel_alerta: "Alto", "Medio" o "Bajo" según urgencia real para TYASA
- Usa SOLO URLs que aparezcan literalmente en las noticias de arriba
- Responde EXCLUSIVAMENTE con el JSON, sin texto adicional"""


def cargar_sintesis_latest() -> dict | None:
    """Carga la síntesis global más reciente (sin importar la fecha).
    Útil al inicio del día siguiente cuando no hay caché para hoy todavía.
    """
    cached = _cache_load("sintesis_global_latest")
    if cached:
        cached["_cached"] = True
    return cached


def cargar_cache_hoy(tipo: str, cat_keys: list[str] | None = None) -> dict | None:
    """Carga el resultado cacheado del día actual para un tipo dado.

    cat_keys — lista de nombres de categoría (misma que se usó al guardar).
    Si se omite, busca con la clave de solo fecha (compatibilidad legada).
    """
    hoy = date.today().isoformat()
    if cat_keys:
        cat_fp = "|".join(sorted(cat_keys))
        ckey = hashlib.md5(f"{tipo}|{hoy}|{cat_fp}".encode()).hexdigest()[:16]
    else:
        ckey = hashlib.md5(f"{tipo}|{hoy}".encode()).hexdigest()[:16]
    cached = _cache_load(ckey)
    if cached:
        cached["_cached"] = True
    return cached


def sintesis_global(
    noticias_por_grupo: dict[str, list[dict]],
    api_key: str,
    model: str = _DEFAULT_MODEL,
    force_refresh: bool = False,
) -> dict:
    """
    Resumen ejecutivo global de todas las categorías estratégicas con URLs de artículos.
    Caché diario en disco, con huella de categorías para invalidar automáticamente
    cuando se agregan/eliminan secciones.
    """
    hoy        = date.today().isoformat()
    cat_fp     = "|".join(sorted(noticias_por_grupo.keys()))
    ckey       = hashlib.md5(f"sintesis_global|{hoy}|{cat_fp}".encode()).hexdigest()[:16]

    cached = _cache_load(ckey)
    if cached and not force_refresh:
        cached["_cached"] = True
        return cached

    # Construir texto de noticias (máx 5 por categoría para mejor cobertura)
    lineas: list[str] = []
    referencias_pool: list[dict] = []

    for grupo, nots in noticias_por_grupo.items():
        top = [n for n in (nots or []) if n.get("url") and n.get("titulo")][:5]
        if not top:
            lineas.append(f"[{grupo}]")
            lineas.append("  (sin noticias disponibles hoy)")
            continue
        lineas.append(f"[{grupo}]")
        for n in top:
            titulo = (n.get("titulo") or "")[:85]
            url    = n.get("url", "")
            fuente = n.get("fuente", "")
            fecha  = n.get("fecha_pub", "")
            lineas.append(f"  • {titulo} | {url} | {fuente} | {fecha}")
            referencias_pool.append({
                "titulo": titulo,
                "url":    url,
                "fuente": fuente,
                "grupo":  grupo,
                "fecha":  fecha,
            })

    if not lineas:
        return {
            "estado_mercado": "",
            "impacto_mexico": "",
            "nivel_alerta": "—",
            "resumen_por_area": {},
            "riesgos": [],
            "oportunidades": [],
            "recomendacion": "",
            "_referencias": [],
            "_fecha": hoy,
            "_cached": False,
            "_error": "No hay noticias disponibles para generar la síntesis.",
        }

    categorias_txt = ", ".join(noticias_por_grupo.keys())
    noticias_txt   = "\n".join(lineas)
    prompt = _GLOBAL_TMPL.format(
        hoy=hoy,
        categorias=categorias_txt,
        noticias_txt=noticias_txt,
    )

    # 8192 tokens: necesario para JSON con 11 categorías + resumen_por_area con URLs
    raw = _call_gemini_text(
        prompt, api_key,
        system=_GLOBAL_SYSTEM,
        model=model,
        max_output_tokens=8192,
        temperature=0.2,
    )

    resultado = _parse_json_response(raw) if raw and raw != "Error al consultar la IA." else None

    if resultado:
        resultado.setdefault("resumen_por_area", [])
        resultado["_cached"]      = False
        resultado["_error"]       = None
        resultado["_fecha"]       = hoy
        resultado["_referencias"] = referencias_pool
        _cache_save(ckey, resultado)
        _cache_save("sintesis_global_latest", resultado)  # para reload entre días
        return resultado

    # Debug: guardar respuesta cruda para diagnóstico
    print(f"[sintesis_global] respuesta cruda (primeros 500 chars): {raw[:500] if raw else 'VACÍA'}")
    return {
        "estado_mercado": "",
        "impacto_mexico": "",
        "nivel_alerta": "—",
        "resumen_por_area": [],
        "riesgos": [],
        "oportunidades": [],
        "recomendacion": "",
        "_referencias": referencias_pool,
        "_fecha": hoy,
        "_cached": False,
        "_error": f"No se pudo generar la síntesis. Respuesta de IA: {(raw or 'vacía')[:200]}",
    }


# ════════════════════════════════════════════════════════════════════════════
# ANÁLISIS DE INDICADORES INEGI
# ════════════════════════════════════════════════════════════════════════════

_INEGI_SYSTEM = (
    "Eres analista macroeconómico senior para TYASA, acería mexicana de acero plano "
    "vía horno eléctrico de arco (EAF). Tu cliente es el equipo directivo. "
    "Responde en español técnico y ejecutivo. Sé preciso y conciso."
)

_INEGI_TMPL = """## Indicador INEGI bajo análisis
**{label}** — Grupo: {group_label}
*{group_desc}*

## Estado actual
- Nivel de alerta Z-score: **{alerta}** (z = {z_score:+.2f}σ)
- Valor más reciente: {ult_valor}
- Variación mensual (MoM): {var_mom}
- Variación anual (YoY): {var_yoy}
- Media 24 meses: {media}

## Últimos 12 meses (fecha: valor)
{tabla}

---
Genera un análisis ejecutivo en 3 párrafos breves (sin encabezados markdown):

1. Qué está pasando — interpreta el movimiento en contexto macroeconómico mexicano
2. Impacto en TYASA — efecto concreto sobre demanda de acero, precios de insumos o competitividad
3. Señales a vigilar — qué monitorear en los próximos 2-3 meses

Máximo 180 palabras totales. Párrafos directos separados por salto de línea doble."""


def _fmt_num_inegi(v) -> str:
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:.2f}M"
        if abs(f) >= 1_000:
            return f"{f:,.0f}"
        return f"{f:.2f}"
    except Exception:
        return "—"


def analizar_indicador_inegi(
    clave: str,
    label: str,
    group_label: str,
    group_desc: str,
    alerta: str,
    z_score: float,
    ult_valor,
    var_mom,
    var_yoy,
    media,
    valores_recientes: list,
    api_key: str,
    force_refresh: bool = False,
) -> dict:
    """
    Análisis IA de un indicador INEGI con contexto TYASA.
    Retorna dict: analisis (str), _cached (bool), _error (str|None).
    """
    if not api_key:
        return {"analisis": "", "_cached": False, "_error": "Sin API key de Gemini"}

    hoy  = date.today().isoformat()
    ckey = hashlib.md5(f"inegi|{clave}|{hoy}".encode()).hexdigest()[:16]

    cached = _cache_load(ckey)
    if cached and not force_refresh:
        cached["_cached"] = True
        return cached

    tabla_lines = [
        f"  {str(f)[:7]}: {_fmt_num_inegi(v)}"
        for f, v in (valores_recientes or [])[-12:]
    ]
    tabla = "\n".join(tabla_lines) if tabla_lines else "  (sin datos)"

    def _pct(v):
        try:
            return f"{float(v):+.1f}%"
        except Exception:
            return "—"

    prompt = _INEGI_TMPL.format(
        label       = label,
        group_label = group_label,
        group_desc  = group_desc,
        alerta      = alerta,
        z_score     = (lambda v: v if v == v else 0.0)(float(z_score) if z_score is not None else 0.0),
        ult_valor   = _fmt_num_inegi(ult_valor),
        var_mom     = _pct(var_mom),
        var_yoy     = _pct(var_yoy),
        media       = _fmt_num_inegi(media),
        tabla       = tabla,
    )

    text = _call_gemini_text(prompt, api_key, system=_INEGI_SYSTEM)
    resultado = {"analisis": text, "_cached": False, "_error": None}
    _cache_save(ckey, resultado)
    return resultado


# ════════════════════════════════════════════════════════════════════════════
# BRIEFING DE VISITA — INTELIGENCIA DE CLIENTES
# ════════════════════════════════════════════════════════════════════════════

_BRIEF_SYSTEM = (
    "Eres analista comercial senior de TYASA, acería mexicana de acero plano (EAF). "
    "Tu misión: armar un briefing de visita ejecutivo y accionable para el equipo de ventas. "
    "Responde en español. Directo, sin fluff."
)

_BRIEF_TMPL = """# Briefing de visita — {cliente}

## Perfil
- Clase ABC: **{clase}** | División: {division} | Antigüedad: {antiguedad}
- Estado de actividad: **{estado}** ({dias} días sin pedido)
- Predicción próximo pedido: {pred_prox}
- Productos activos: {n_prods}

## Rendimiento reciente
- Prom. mensual últimos 3 meses: {avg_3m:.1f} ton
- Mismo período año anterior: {avg_3m_yoy:.1f} ton
- Variación interanual: {var_yoy}
- Tendencia 6 meses: {tendencia}

## Mix de productos principales
{lista_prods}

## Estacionalidad histórica
- Mes de mayor compra: {mes_peak}
- Mes con menor compra: {mes_low}
- Mes actual: {mes_actual}

---
Genera exactamente 4-5 bullets de acción para el vendedor antes de la visita.
Cada bullet: emoji relevante (💼 📦 📈 ⚠️ 💡 🎯 🔄) + máximo 25 palabras.
Foco: recuperar si inactivo, expandir mix si activo, anticipar estacionalidad, cross-sell, riesgo.
Sin introducción ni cierre — solo los bullets, uno por línea."""


def generar_briefing_cliente(
    cliente: str,
    clase: str,
    division: str,
    antiguedad: str,
    estado: str,
    dias: int,
    pred_prox: str,
    n_prods: int,
    avg_3m: float,
    avg_3m_yoy: float,
    tendencia: str,
    lista_prods: str,
    mes_peak: str,
    mes_low: str,
    mes_actual: str,
    api_key: str,
    force_refresh: bool = False,
) -> dict:
    """Genera un briefing de visita comercial para un cliente con IA."""
    if not api_key:
        return {"briefing": "", "_cached": False, "_error": "Sin API key de Gemini"}

    hoy  = date.today().isoformat()
    ckey = hashlib.md5(f"brief|{cliente}|{hoy}".encode()).hexdigest()[:16]

    cached = _cache_load(ckey)
    if cached and not force_refresh:
        cached["_cached"] = True
        return cached

    try:
        v = float(avg_3m_yoy)
        var_yoy_str = f"{(avg_3m - v) / v * 100:+.1f}%" if v != 0 else "—"
    except Exception:
        var_yoy_str = "—"

    prompt = _BRIEF_TMPL.format(
        cliente    = cliente,
        clase      = clase,
        division   = division,
        antiguedad = antiguedad,
        estado     = estado,
        dias       = dias,
        pred_prox  = pred_prox,
        n_prods    = n_prods,
        avg_3m     = avg_3m,
        avg_3m_yoy = avg_3m_yoy,
        var_yoy    = var_yoy_str,
        tendencia  = tendencia,
        lista_prods = lista_prods,
        mes_peak   = mes_peak,
        mes_low    = mes_low,
        mes_actual  = mes_actual,
    )

    text     = _call_gemini_text(prompt, api_key, system=_BRIEF_SYSTEM)
    resultado = {"briefing": text, "_cached": False, "_error": None}
    _cache_save(ckey, resultado)
    return resultado
