"""
sentimiento.py — Clasificación de sentimiento de noticias siderúrgicas para TYASA.

Interpreta cada noticia desde la perspectiva de TYASA como productora EAF de acero plano:
  positivo  → beneficia a TYASA (alza de precios HRC, demanda sube, aranceles protegen)
  negativo  → perjudica a TYASA (chatarra cara, dumping chino, baja demanda)
  neutro    → informativo sin impacto directo claro

Usa Gemini con JSON estructurado. Caché local por hash de URL + fecha.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# ── Caché ─────────────────────────────────────────────────────────────────────
_ROOT     = Path(__file__).resolve().parents[3]
_SENT_DIR = _ROOT / "cache" / "sentimiento"
_SENT_DIR.mkdir(parents=True, exist_ok=True)

# ── Variables principales a mapear ────────────────────────────────────────────
VARIABLES_ACERO = [
    "HRC_laminado_caliente",
    "CRC_laminado_frio",
    "galvanizado",
    "chatarra_scrap",
    "mineral_hierro",
    "carbon_coquizable",
    "zinc_galvanizado",
    "energia_electricidad",
    "tipo_cambio",
    "aranceles_comercio",
    "automotriz",
    "construccion",
    "nearshoring_manufactura",
    "competidores_ternium_arcelor",
    "china_sobrecapacidad",
    "demanda_general",
    "otro",
]

# ── Grupos temáticos relevantes ───────────────────────────────────────────────
GRUPOS_RELEVANTES = [
    "Urgente", "Tendencias", "Empresas", "Insumos",
    "Mercado Global", "Materias Primas", "Comercio",
    "Regulación", "Energía", "Infraestructura", "Industria", "Economía",
]

# ── System prompt específico para TYASA EAF ───────────────────────────────────
_SYSTEM_SENT = """Eres analista senior de mercados para TYASA, acería mexicana que produce \
acero plano (HRC, CRC, galvanizado) mediante horno eléctrico de arco (EAF).

CONTEXTO TYASA:
- Vende: acero plano (lámina HR, CR, galvanizada) al mercado mexicano
- Insumos principales: chatarra ferrosa (mayor costo), electricidad, zinc para galvanizado
- Competencia: Ternium MX, importaciones de China/Asia (dumping)
- Clientes: automotriz, construcción, electrodomésticos, manufactura general
- Riesgo principal: sobrecapacidad china, aranceles cambiantes, alza en chatarra

Tu perspectiva al clasificar sentimiento:
  positivo = bueno para TYASA (precios HRC suben, demanda sube, aranceles protegen mercado local)
  negativo = malo para TYASA (chatarra cara, dumping importaciones, demanda cae, energía cara)
  neutro   = sin impacto claro o balanceado"""

_PROMPT_TMPL = """Analiza esta noticia y clasifica su sentimiento DESDE LA PERSPECTIVA DE TYASA.

Título: {titulo}
Fuente: {fuente}
Fecha: {fecha}
Descripción: {descripcion}

Responde ÚNICAMENTE con este JSON exacto (sin markdown, sin texto extra):
{{
  "sentimiento": "positivo" | "neutro" | "negativo",
  "score": número entre -1.0 y 1.0 (negativo = malo para TYASA, positivo = bueno),
  "variable_principal": "{vars}",
  "señal": "precio_sube" | "precio_baja" | "demanda_sube" | "demanda_baja" | "costo_sube" | "costo_baja" | "riesgo_regulatorio" | "oportunidad" | "neutro",
  "alcance": "nacional" | "internacional" | "ambos",
  "razon": "máximo 15 palabras explicando el impacto en TYASA",
  "confianza": "Alta" | "Media" | "Baja"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
def _hash_noticia(url: str) -> str:
    hoy = date.today().isoformat()
    return hashlib.md5(f"{url}|{hoy}".encode()).hexdigest()[:16]


def _cache_load(h: str) -> dict | None:
    p = _SENT_DIR / f"{h}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _cache_save(h: str, data: dict) -> None:
    (_SENT_DIR / f"{h}.json").write_text(
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


# ─────────────────────────────────────────────────────────────────────────────
def clasificar_noticia(
    noticia: dict,
    gemini_key: str,
    model: str = "gemini-3.5-flash",
    force_refresh: bool = False,
) -> dict:
    """
    Clasifica el sentimiento de una noticia individual desde la perspectiva de TYASA.
    Retorna dict con: sentimiento, score, variable_principal, señal, alcance, razon, confianza.
    """
    url   = noticia.get("url", "")
    h     = _hash_noticia(url)
    cache = _cache_load(h)
    if cache and not force_refresh:
        cache["_cached"] = True
        return cache

    vars_opts = " | ".join(VARIABLES_ACERO)
    prompt = _PROMPT_TMPL.format(
        titulo      = (noticia.get("titulo", "") or "")[:300],
        fuente      = (noticia.get("fuente", "") or "")[:80],
        fecha       = (noticia.get("fecha_pub", "") or "")[:10],
        descripcion = (noticia.get("descripcion", "") or "")[:400],
        vars        = vars_opts,
    )

    resultado = _llamar_gemini(prompt, gemini_key, model)
    if not resultado:
        resultado = {
            "sentimiento":        "neutro",
            "score":              0.0,
            "variable_principal": "otro",
            "señal":              "neutro",
            "alcance":            "ambos",
            "razon":              "No se pudo clasificar",
            "confianza":          "Baja",
        }

    resultado["_cached"] = False
    resultado["url"]      = url
    resultado["titulo"]   = (noticia.get("titulo", "") or "")[:300]
    resultado["fuente"]   = (noticia.get("fuente", "") or "")[:100]
    resultado["fecha_pub"] = (noticia.get("fecha_pub", "") or "")[:10]
    resultado["grupo"]    = noticia.get("grupo", "")

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
                system_instruction=_SYSTEM_SENT,
                temperature=0.2,
                max_output_tokens=512,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (resp.text or "").strip()
        return _parse_json(raw) if raw else None
    except ImportError:
        pass
    except Exception as e:
        print(f"[sentimiento] SDK error: {e}")

    # Fallback REST
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": _SYSTEM_SENT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 512},
        }
        resp = requests.post(url, json=body, timeout=25)
        if resp.status_code != 200:
            return None
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return _parse_json(raw)
    except Exception as e:
        print(f"[sentimiento] REST error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
def clasificar_lote(
    noticias: list[dict],
    gemini_key: str,
    model: str = "gemini-3.5-flash",
    max_noticias: int = 30,
) -> list[dict]:
    """Clasifica un lote de noticias. Respeta caché — solo llama Gemini para noticias nuevas."""
    resultados = []
    for n in noticias[:max_noticias]:
        try:
            r = clasificar_noticia(n, gemini_key, model=model)
            resultados.append(r)
        except Exception as e:
            print(f"[sentimiento] Error clasificando {n.get('url','')[:50]}: {e}")
    return resultados


# ─────────────────────────────────────────────────────────────────────────────
def calcular_indice_sentimiento(resultados: list[dict]) -> dict:
    """
    Calcula el índice global de sentimiento de mercado para TYASA.
    Retorna: indice (-1 a +1), nivel, color, resumen por variable, resumen por señal.
    """
    if not resultados:
        return {
            "indice": 0.0, "nivel": "Neutro", "color": "#64748B",
            "n_positivas": 0, "n_negativas": 0, "n_neutras": 0,
            "por_variable": {}, "por_señal": {}, "por_alcance": {},
        }

    scores = [float(r.get("score", 0.0) or 0.0) for r in resultados]
    indice = sum(scores) / len(scores)

    n_pos = sum(1 for r in resultados if r.get("sentimiento") == "positivo")
    n_neg = sum(1 for r in resultados if r.get("sentimiento") == "negativo")
    n_neu = len(resultados) - n_pos - n_neg

    if indice >= 0.2:
        nivel, color = "Favorable",  "#16A34A"
    elif indice >= 0.05:
        nivel, color = "Ligeramente positivo", "#65A30D"
    elif indice <= -0.2:
        nivel, color = "Adverso",    "#DC2626"
    elif indice <= -0.05:
        nivel, color = "Ligeramente negativo", "#EA580C"
    else:
        nivel, color = "Neutro",     "#64748B"

    # Agrupaciones
    por_var = {}
    for r in resultados:
        v = r.get("variable_principal", "otro")
        if v not in por_var:
            por_var[v] = {"positivo": 0, "neutro": 0, "negativo": 0, "score_sum": 0.0, "n": 0}
        por_var[v][r.get("sentimiento", "neutro")] += 1
        por_var[v]["score_sum"] += float(r.get("score", 0.0) or 0.0)
        por_var[v]["n"] += 1

    for v in por_var:
        por_var[v]["score_avg"] = round(por_var[v]["score_sum"] / por_var[v]["n"], 2)

    por_señal = {}
    for r in resultados:
        s = r.get("señal", "neutro")
        por_señal[s] = por_señal.get(s, 0) + 1

    por_alcance = {}
    for r in resultados:
        a = r.get("alcance", "ambos")
        por_alcance[a] = por_alcance.get(a, 0) + 1

    return {
        "indice":       round(indice, 3),
        "nivel":        nivel,
        "color":        color,
        "n_positivas":  n_pos,
        "n_negativas":  n_neg,
        "n_neutras":    n_neu,
        "total":        len(resultados),
        "por_variable": por_var,
        "por_señal":    por_señal,
        "por_alcance":  por_alcance,
    }


# ─────────────────────────────────────────────────────────────────────────────
def resultados_a_dataframe(resultados: list[dict]) -> pd.DataFrame:
    """Convierte lista de resultados de clasificación a DataFrame listo para BigQuery."""
    if not resultados:
        return pd.DataFrame()
    rows = []
    for r in resultados:
        rows.append({
            "hash_url":           _hash_noticia(r.get("url", "")),
            "fecha_pub":          r.get("fecha_pub", "")[:10] or None,
            "fecha_analisis":     date.today().isoformat(),
            "titulo":             (r.get("titulo", "") or "")[:500],
            "fuente":             (r.get("fuente", "") or "")[:200],
            "url":                (r.get("url", "") or "")[:500],
            "grupo_tematico":     (r.get("grupo", "") or "")[:100],
            "variable_principal": (r.get("variable_principal", "otro") or "otro")[:100],
            "alcance":            (r.get("alcance", "ambos") or "ambos")[:50],
            "sentimiento":        (r.get("sentimiento", "neutro") or "neutro")[:20],
            "score":              float(r.get("score", 0.0) or 0.0),
            "señal":              (r.get("señal", "neutro") or "neutro")[:60],
            "razon":              (r.get("razon", "") or "")[:300],
            "confianza":          (r.get("confianza", "Baja") or "Baja")[:20],
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
def detectar_cambio_sentimiento(
    df_historico: pd.DataFrame,
    ventana_reciente: int = 3,
    ventana_base: int = 10,
) -> list[dict]:
    """
    Detecta cambios bruscos de sentimiento en los últimos días vs base histórica.
    Retorna lista de alertas: variable, cambio_score, nivel (Alta/Media/Baja).
    """
    alertas = []
    if df_historico.empty or "variable_principal" not in df_historico.columns:
        return alertas

    df = df_historico.copy()
    df["fecha_pub"] = pd.to_datetime(df["fecha_pub"], errors="coerce")
    df = df.dropna(subset=["fecha_pub"]).sort_values("fecha_pub", ascending=False)

    hoy   = pd.Timestamp.today()
    corte = hoy - pd.Timedelta(days=ventana_reciente)
    base  = hoy - pd.Timedelta(days=ventana_base)

    reciente = df[df["fecha_pub"] >= corte]
    historico = df[(df["fecha_pub"] < corte) & (df["fecha_pub"] >= base)]

    if reciente.empty or historico.empty:
        return alertas

    for var in reciente["variable_principal"].unique():
        s_rec  = reciente[reciente["variable_principal"] == var]["score"].mean()
        s_hist = historico[historico["variable_principal"] == var]["score"].mean() \
                 if var in historico["variable_principal"].values else 0.0

        cambio = s_rec - s_hist
        if abs(cambio) < 0.15:
            continue

        nivel = "Alta" if abs(cambio) >= 0.4 else "Media" if abs(cambio) >= 0.25 else "Baja"
        dir_txt = "empeoró" if cambio < 0 else "mejoró"
        alertas.append({
            "variable":     var,
            "score_reciente": round(float(s_rec), 2),
            "score_base":     round(float(s_hist), 2),
            "cambio":         round(float(cambio), 2),
            "direccion":      dir_txt,
            "nivel":          nivel,
            "descripcion":    f"Sentimiento en {var.replace('_',' ')} {dir_txt} {abs(cambio):.2f} pts en últimos {ventana_reciente}d",
        })

    return sorted(alertas, key=lambda x: abs(x["cambio"]), reverse=True)
