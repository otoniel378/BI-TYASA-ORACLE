"""
mananera.py — Analiza la conferencia mañanera presidencial para impacto siderúrgico.

Flujo:
  1. Busca en YouTube múltiples candidatos (yt-dlp) — en vivo o grabado
  2. Obtiene la transcripción con 3 métodos: youtube-transcript-api → yt-dlp list() → yt-dlp subtítulos directos
  3. Prueba cada candidato hasta obtener transcripción válida
  4. Filtra y analiza con Gemini: solo información relevante para acero
  5. Caché por fecha en cache/mananera/ (máx 3 días, limpieza automática)
"""
from __future__ import annotations

import json
import re
import datetime
import urllib.request
from pathlib import Path
import requests

# ── Rutas ─────────────────────────────────────────────────────────────────────
_ROOT_DIR = Path(__file__).resolve().parents[2]
MANANERA_CACHE_DIR = _ROOT_DIR / "cache" / "mananera"
MANANERA_CACHE_DAYS = 3

# ── Meses en español ──────────────────────────────────────────────────────────
_MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

# Palabras clave para identificar el canal oficial
_OFFICIAL_KW = {"presidencia", "gobierno", "sheinbaum", "claudia", "gob.mx"}

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """\
Eres el analista senior de inteligencia comercial de TYASA, empresa siderúrgica \
mexicana que opera hornos de arco eléctrico (EAF).

PORTAFOLIO TYASA:
- Tubería OCTG (API 5CT): casing y tubing para PEMEX y operadoras privadas
- Tubería mecánica y estructural (HSS/RHS): manufactura, maquinaria, construcción metálica
- Perfiles estructurales: ángulos, canales, vigas IPR para construcción e industria
- SBQ (Special Bar Quality): barras de calidad especial para autopartes y maquinaria
- Lámina negra (HRC/CRC): manufactura general, automotriz, línea blanca
- Lámina galvanizada y recubiertos: construcción, línea blanca, automotriz

CLIENTES CLAVE: PEMEX y operadoras privadas de petróleo y gas, armadoras y Tier-1 \
automotriz, constructoras y distribuidores de acero, manufactura de maquinaria y equipo.

Tu rol es analizar la conferencia mañanera y extraer SOLO lo que impacta en ventas, \
costos, demanda o regulación de TYASA. Responde ÚNICAMENTE con JSON válido, sin \
markdown ni texto fuera del JSON.\
"""

_PROMPT_TEMPLATE = """\
Analiza esta transcripción de la mañanera del {fecha}.

REGLA: IGNORA política partidista, seguridad pública, programas sociales sin impacto \
económico, temas sin conexión con industria, manufactura, energía o comercio.

EXTRAE y CONECTA cada tema con TYASA usando este mapa:

ENERGÍA:
- CFE/electricidad → costo directo del EAF (horno electro-intensivo, ~40% del costo)
- Gas natural/CENAGAS → preheating, hornos de tratamiento térmico
- PEMEX proyectos/presupuesto → demanda de Tubería OCTG (API 5CT)
- Tarifas CFE → margen de contribución en todos los productos

REGULACIÓN Y COMERCIO:
- Aranceles a importaciones → protección vs. acero chino/global en lámina, perfiles, tubería
- T-MEC / reglas de origen → nuevas plantas automotrices = demanda SBQ y Lámina CRC
- Antidumping / cuotas compensatorias → protección tubería OCTG, lámina galvanizada, perfiles
- Tipo de cambio peso/dólar → costo insumos importados vs. precios de venta en pesos

DEMANDA E INFRAESTRUCTURA:
- Construcción / vivienda → Perfiles estructurales, ángulos, canales, tubería estructural
- Obra pública (trenes, puertos, carreteras, presas) → Placa, perfiles, tubería estructural
- Inversión industrial / nearshoring / parques → Tubería mecánica, estructural, perfiles
- Automotriz / maquinaria / herramientas → SBQ, Lámina CRC, Tubería mecánica

MACROECONOMÍA:
- PIB / actividad industrial → demanda general; correlación directa con volumen TYASA
- Inflación / tasas Banxico → costos financieros y poder de compra de clientes distribuidores
- Devaluación peso → encarece chatarra/DRI importada pero protege precio local en pesos

Responde con este JSON exacto (sin markdown):

{{
  "tiene_contenido_relevante": true,
  "resumen_ejecutivo": [
    "Punto 1 conciso, máx 80 palabras",
    "Punto 2 conciso, máx 80 palabras",
    "Punto 3 si aplica",
    "Punto 4 si aplica",
    "Punto 5 si aplica"
  ],
  "analisis_impacto": [
    {{
      "punto": "Título del tema en 10-15 palabras",
      "tipo": "Regulación | Energía | Demanda | Riesgo | Oportunidad | Macroeconomía",
      "impacto": "Alto | Medio | Bajo",
      "direccion": "Positivo | Negativo | Neutral",
      "productos_afectados": ["Tubería OCTG", "Tubería Mecánica", "Perfiles", "SBQ", "Lámina Negra", "Galvanizado"],
      "areas_afectadas": ["SBQ", "Aceros Planos", "Aceros Largos", "Energía/Costos", "Comercial"],
      "explicacion": "2-3 oraciones específicas: qué ocurrió, por qué impacta a TYASA y magnitud estimada."
    }}
  ],
  "alertas_criticas": [],
  "insight_estrategico": "2-3 oraciones con implicaciones concretas para precios, costos o demanda de TYASA en el corto plazo.",
  "recomendacion": "Empieza con verbo de acción en segunda persona (Evalúa / Considera / Revisa / Acelera / Prioriza / Asegura). Acción específica y concreta dirigida a TYASA."
}}

Si NO hay contenido relevante:
{{"tiene_contenido_relevante": false, "resumen_ejecutivo": [], \
"analisis_impacto": [], "alertas_criticas": [], \
"insight_estrategico": "", "recomendacion": ""}}

TRANSCRIPCIÓN ({chars} caracteres):
{transcripcion}"""


# ── Caché ─────────────────────────────────────────────────────────────────────

def _cleanup_old_cache(days: int = MANANERA_CACHE_DAYS) -> None:
    if not MANANERA_CACHE_DIR.exists():
        return
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    for f in MANANERA_CACHE_DIR.glob("*.json"):
        try:
            if datetime.date.fromisoformat(f.stem) < cutoff:
                f.unlink()
        except (ValueError, OSError):
            pass


def _cache_load(fecha: str) -> dict | None:
    path = MANANERA_CACHE_DIR / f"{fecha}.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _cache_save(fecha: str, data: dict) -> None:
    MANANERA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = MANANERA_CACHE_DIR / f"{fecha}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[mananera] Cache write error: {e}")


# ── YouTube helpers ───────────────────────────────────────────────────────────

def _find_video_candidates(fecha: str) -> tuple[list[dict], str]:
    """
    Busca la mañanera de `fecha` en YouTube con múltiples estrategias.
    Retorna (lista_de_candidatos, error_msg).
    Cada candidato: {"id": str, "is_live": bool, "duration": float, "priority": int}

    Prioridades (menor = mejor):
      1. Canal oficial + duración >= 45 min  → priority 1
      2. Canal oficial en vivo (live)         → priority 2
      3. Cualquier video >= 45 min            → priority 3
      4. Cualquier live                       → priority 4
      5. Primer resultado                     → priority 5
    """
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        return [], "yt-dlp no instalado — ejecuta: pip install yt-dlp"

    try:
        dt = datetime.date.fromisoformat(fecha)
        mes = _MESES[dt.month]
        dia = dt.day
        year = dt.year
    except Exception:
        return [], f"Fecha inválida: {fecha}"

    # Múltiples queries para aumentar probabilidad de encontrar el video
    queries = [
        f"conferencia mañanera Claudia Sheinbaum {dia} {mes} {year}",
        f"mañanera presidencial {dia} {mes} {year}",
        f"conferencia mañanera presidencia Mexico {fecha}",
        f"mañanera {dia} de {mes} {year}",
    ]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    seen_ids: set[str] = set()
    candidates: list[dict] = []

    for query in queries:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(f"ytsearch10:{query}", download=False)
                entries = [
                    e for e in (result or {}).get("entries", [])
                    if e and e.get("id")
                ]
                if not entries:
                    continue

                def _is_official(e: dict) -> bool:
                    uploader = (
                        e.get("uploader") or e.get("channel") or
                        e.get("uploader_id") or ""
                    ).lower()
                    return any(kw in uploader for kw in _OFFICIAL_KW)

                def _is_live(e: dict) -> bool:
                    return bool(
                        e.get("is_live") or
                        e.get("live_status") in ("is_live", "is_upcoming")
                    )

                for e in entries:
                    vid = e["id"]
                    if vid in seen_ids:
                        continue
                    seen_ids.add(vid)

                    is_official = _is_official(e)
                    is_live = _is_live(e)
                    duration = e.get("duration") or 0

                    if is_official and duration >= 2700:
                        priority = 1
                    elif is_official and is_live:
                        priority = 2
                    elif duration >= 2700:
                        priority = 3
                    elif is_live:
                        priority = 4
                    else:
                        priority = 5

                    candidates.append({
                        "id": vid,
                        "is_live": is_live,
                        "duration": duration,
                        "priority": priority,
                    })

        except Exception:
            continue

    # Ordenar por prioridad y deduplicar
    candidates.sort(key=lambda c: (c["priority"], c["duration"] * -1))
    return candidates, ""


def _get_transcript_yt_dlp(video_id: str) -> str | None:
    """Extrae subtítulos usando yt-dlp directamente (más resistente a bloqueos)."""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["es", "es-MX", "es-419"],
        "subtitlesformat": "json3",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            # Buscar subtítulos en español: manuales primero, luego automáticos
            subtitles = info.get("subtitles") or {}
            auto_subs = info.get("automatic_captions") or {}

            for src in [subtitles, auto_subs]:
                for lang_key in ["es-MX", "es-419", "es"]:
                    if lang_key in src:
                        for sub_entry in src[lang_key]:
                            if sub_entry.get("ext") in ("json3", "json"):
                                req = urllib.request.Request(
                                    sub_entry["url"],
                                    headers={"User-Agent": "Mozilla/5.0"}
                                )
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    data = json.loads(resp.read().decode("utf-8"))
                                parts = []
                                for event in data.get("events", []):
                                    segs = event.get("segs") or []
                                    for seg in segs:
                                        t = seg.get("utf8", "").strip()
                                        if t:
                                            parts.append(t)
                                text = " ".join(parts)
                                if len(text) > 100:
                                    return text
    except Exception:
        pass

    return None


def _get_transcript(video_id: str) -> tuple[str | None, str]:
    """Obtiene la transcripción en español con múltiples métodos."""
    # ── Método 1: youtube-transcript-api ──────────────────────────────────
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["es", "es-MX", "es-419", "es-ES", "es-US"])
        text = " ".join(s.text for s in fetched).strip()
        if text:
            return text, ""
    except ImportError:
        pass  # lib no instalada, intentar fallback
    except Exception:
        pass  # YouTube bloqueó la API, intentar fallback

    # ── Método 2: youtube-transcript-api vía list() ──────────────────────
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        api2 = YouTubeTranscriptApi()
        for t in api2.list(video_id):
            if t.language_code.startswith("es"):
                fetched2 = t.fetch()
                text2 = " ".join(s.text for s in fetched2).strip()
                if text2:
                    return text2, ""
    except Exception:
        pass

    # ── Método 3: yt-dlp subtítulos directos ─────────────────────────────
    text3 = _get_transcript_yt_dlp(video_id)
    if text3:
        return text3, ""

    return None, "El video no tiene transcripción ni subtítulos en español disponibles."


# ── Gemini ────────────────────────────────────────────────────────────────────

_MANANERA_MODELS = ("gemini-3.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash")


def _call_gemini(prompt: str, api_key: str) -> dict | None:
    # SDK google-genai — prueba modelos en orden hasta que uno responda
    try:
        from google import genai  # type: ignore
        from google.genai import types as T  # type: ignore

        client = genai.Client(api_key=api_key)
        for model in _MANANERA_MODELS:
            try:
                cfg_kwargs: dict = dict(
                    system_instruction=_SYSTEM,
                    temperature=0.2,
                    max_output_tokens=3000,
                )
                try:
                    cfg_kwargs["thinking_config"] = T.ThinkingConfig(thinking_budget=0)
                except Exception:
                    pass
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=T.GenerateContentConfig(**cfg_kwargs),
                )
                raw = (resp.text or "").strip()
                if not raw:
                    continue
                clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("`").strip()
                m = re.search(r"\{.*\}", clean, re.DOTALL)
                return json.loads(m.group()) if m else None
            except Exception as e:
                print(f"[mananera] Gemini SDK {model} error: {e}")
    except ImportError:
        pass

    # REST fallback
    for model in _MANANERA_MODELS:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            )
            body = {
                "system_instruction": {"parts": [{"text": _SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 3000},
            }
            resp = requests.post(url, json=body, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                raw  = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("`").strip()
                m = re.search(r"\{.*\}", clean, re.DOTALL)
                return json.loads(m.group()) if m else None
            print(f"[mananera] REST {model} {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[mananera] REST error ({model}): {e}")
    return None


# ── API pública ───────────────────────────────────────────────────────────────

def analizar_mananera(
    api_key: str,
    fecha: str | None = None,
    force_refresh: bool = False,
) -> dict:
    """
    Analiza la mañanera de `fecha` (YYYY-MM-DD, default: hoy).
    Soporta videos en vivo (is_live=True) y grabados.

    Retorna dict con:
      tiene_contenido_relevante, resumen_ejecutivo, analisis_impacto,
      alertas_criticas, insight_estrategico, recomendacion,
      _cached, _error (opcional), _video_id (opcional), _is_live, fecha
    """
    if fecha is None:
        fecha = str(datetime.date.today())

    MANANERA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_old_cache()

    if not force_refresh:
        cached = _cache_load(fecha)
        if cached:
            cached["_cached"] = True
            return cached

    # Paso 1 — buscar videos candidatos
    candidates, err = _find_video_candidates(fecha)
    if not candidates:
        return {
            "tiene_contenido_relevante": False,
            "_error": err,
            "_cached": False,
            "fecha": fecha,
            "_is_live": False,
        }

    # Paso 2 — intentar transcripción en cada candidato hasta que funcione
    transcript = None
    video_id = None
    is_live = False
    tried = 0
    for cand in candidates:
        tried += 1
        transcript, _ = _get_transcript(cand["id"])
        if transcript:
            video_id = cand["id"]
            is_live = cand["is_live"]
            break
        # Si no funciona, seguir con el siguiente candidato

    if not transcript:
        if is_live:
            msg = (
                "La conferencia está en vivo o acaba de terminar. "
                "Las transcripciones automáticas de YouTube quedan disponibles "
                "aproximadamente 15-30 minutos después de finalizar la transmisión. "
                "Intenta de nuevo en unos minutos."
            )
        else:
            msg = f"No se obtuvo transcripción de {tried} video(s) intentados."
        return {
            "tiene_contenido_relevante": False,
            "_error": msg,
            "_cached": False,
            "fecha": fecha,
            "_video_id": candidates[0]["id"] if candidates else None,
            "_is_live": False,
        }

    # Paso 3 — Gemini (truncar a 40 000 chars ≈ 1 h de discurso)
    trunc = transcript[:40_000]
    prompt = _PROMPT_TEMPLATE.format(
        fecha=fecha, chars=len(trunc), transcripcion=trunc
    )
    result = _call_gemini(prompt, api_key)

    if result is None:
        return {
            "tiene_contenido_relevante": False,
            "_error": "Gemini no pudo procesar la transcripción.",
            "_cached": False,
            "fecha": fecha,
            "_video_id": video_id,
            "_is_live": is_live,
        }

    result.update({
        "_cached": False,
        "fecha": fecha,
        "_video_id": video_id,
        "_is_live": is_live,
    })
    result.pop("_error", None)
    # No cachear videos en vivo (transcripción puede ser parcial)
    if not is_live:
        _cache_save(fecha, result)
    return result
