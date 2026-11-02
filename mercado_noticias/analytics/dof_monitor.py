"""
dof_monitor.py — Monitorea el Diario Oficial de la Federación (DOF) por decretos
y acuerdos con impacto directo en TYASA (comercio exterior/aranceles, Hacienda,
energía/CFE, Banco de México).

Motivación (2026-11-02): un decreto real (Regla 8va para bolas de molienda,
DOF 30/10/2026) tocó fracciones arancelarias propias de TYASA y el equipo se
enteró por un aviso de WhatsApp/LinkedIn de un tercero, no por el monitor de
noticias — Google News casi nunca indexa publicaciones del DOF con el lenguaje
técnico exacto ("Regla 8va", fracción arancelaria), así que se necesita una
fuente dedicada.

Flujo:
  1. fetch_sumario_dof()   — baja el sumario del día (dof.gob.mx/sumario.xml).
  2. filtrar_candidatos()  — se queda con lo publicado por dependencias que
     pueden afectar a TYASA, o que menciona palabras clave de comercio
     exterior/energía aunque la dependencia no haga match exacto.
  3. analizar_decreto()    — para cada candidato, baja el texto completo de la
     nota (#DivDetalleNota), busca fracciones arancelarias propias de TYASA
     (scripts/fracciones_tyasa.py) y llama a Gemini para decidir si hay
     impacto real y describirlo en términos de negocio.

A propósito NO importa streamlit (mismo patrón que correo_noticias.py /
sentimiento.py) — lo usa scripts/monitor_dof.py, que corre como script plano
tanto localmente como en GitHub Actions.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

import requests

from scripts.fracciones_tyasa import FRACCIONES_TYASA, es_fraccion_tyasa

SUMARIO_URL = "https://dof.gob.mx/sumario.xml"
HTTP_TIMEOUT = 20

# Dependencias cuyos acuerdos/decretos pueden afectar directo a TYASA —
# confirmado con el usuario 2026-11-02 (Economía ya probó ser relevante;
# Hacienda/Energía/Banxico se agregan por aranceles vía decreto presidencial,
# tarifas eléctricas/CFE y tipo de cambio/tasas).
_DEPENDENCIAS_RELEVANTES = (
    "SECRETARIA DE ECONOMIA",
    "SECRETARIA DE HACIENDA",
    "SECRETARIA DE ENERGIA",
    "BANCO DE MEXICO",
    "COMISION FEDERAL DE ELECTRICIDAD",
    "COMISION REGULADORA DE ENERGIA",
)

# Respaldo por palabra clave — por si el título no trae la dependencia exacta
# (acuerdos conjuntos, publicados por Presidencia, organismos descentralizados).
_KEYWORDS_RESPALDO = (
    "arancel", "comercio exterior", "importacion", "importaciones",
    "exportacion", "exportaciones", "antidumping", "dumping",
    "cuota compensatoria", "regla 8", "regla octava", "tigie",
    "fraccion arancelaria", "fracciones arancelarias", "t-mec", "tmec",
    "siderurg", "acero", "tarifa electrica", "tarifas electricas", "cfe",
    "gas natural", "tipo de cambio", "tasa de interes", "banxico",
)

_FRACCION_RE = re.compile(r"\b\d{4}\.\d{2}\.\d{2}\b|\b\d{8}\b")


def _norm(texto: str) -> str:
    """minúsculas + sin acentos, para comparar contra listas de keywords."""
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


# ── 1. Sumario del día ───────────────────────────────────────────────────────

def fetch_sumario_dof(fecha: str | None = None) -> list[dict]:
    """
    Baja el sumario de publicaciones del DOF. `fecha` no filtra la petición
    (el feed siempre trae "hoy" en hora de México) — se usa solo para
    confirmar/etiquetar los resultados.
    Retorna lista de dicts: {titulo, descripcion, url, codigo, fecha_dof}.
    """
    try:
        resp = requests.get(
            SUMARIO_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TyasaBI/1.0)"},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[dof_monitor] Error bajando sumario.xml: {e}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"[dof_monitor] Error parseando sumario.xml: {e}")
        return []

    items = []
    for item in root.findall(".//item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        descripcion = (item.findtext("description") or "").strip()
        fecha_dof = (item.findtext("valueDate") or "").strip()

        m = re.search(r"codigo=(\d+)", link)
        codigo = m.group(1) if m else None
        if not codigo:
            continue

        items.append({
            "codigo": codigo,
            "titulo": titulo,
            "descripcion": descripcion,
            "url": link,
            "fecha_dof": fecha_dof,
        })
    return items


def filtrar_candidatos(items: list[dict]) -> list[dict]:
    """Se queda con lo publicado por dependencias relevantes, o que menciona
    alguna palabra clave de comercio exterior/energía en título o descripción."""
    candidatos = []
    for it in items:
        texto = _norm(f"{it['titulo']} {it['descripcion']}")
        dependencia_ok = any(_norm(dep) in texto for dep in _DEPENDENCIAS_RELEVANTES)
        keyword_ok = any(kw in texto for kw in _KEYWORDS_RESPALDO)
        if dependencia_ok or keyword_ok:
            candidatos.append(it)
    return candidatos


# ── 2. Texto completo de la nota ─────────────────────────────────────────────

def _fetch_texto_completo(url: str) -> str:
    """Baja el texto íntegro de la nota del DOF (incluye tablas, ej. de
    fracciones arancelarias) desde el div #DivDetalleNota."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TyasaBI/1.0)"},
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return ""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        div = soup.find("div", id="DivDetalleNota")
        if not div:
            return ""
        return div.get_text(separator=" ", strip=True)
    except ImportError:
        print("[dof_monitor] beautifulsoup4 no instalado — no se puede leer el texto de la nota.")
        return ""
    except Exception as e:
        print(f"[dof_monitor] Error bajando nota {url}: {e}")
        return ""


def _extraer_fracciones_tyasa(texto: str) -> list[str]:
    """Fracciones arancelarias (8 dígitos) mencionadas en el texto que son
    propias de TYASA (scripts/fracciones_tyasa.py) — máxima señal de relevancia:
    si el decreto cita una fracción que TYASA usa para importar/exportar, es
    relevante sin importar qué tan genérico suene el resto del texto."""
    encontradas = {m.replace(".", "") for m in _FRACCION_RE.findall(texto)}
    return sorted(f for f in encontradas if es_fraccion_tyasa(f))


# ── 3. Gemini: ¿es relevante y qué significa para TYASA? ────────────────────

_SYSTEM_DOF = """\
Eres el analista senior de inteligencia comercial de TYASA, empresa siderúrgica \
mexicana que opera hornos de arco eléctrico (EAF).

PORTAFOLIO TYASA:
- Tubería OCTG (API 5CT): casing y tubing para PEMEX y operadoras privadas
- Tubería mecánica y estructural (HSS/RHS): manufactura, maquinaria, construcción metálica
- Perfiles estructurales: ángulos, canales, vigas IPR para construcción e industria
- SBQ (Special Bar Quality): barras de calidad especial para autopartes y maquinaria
- Lámina negra (HRC/CRC): manufactura general, automotriz, línea blanca
- Lámina galvanizada y recubiertos: construcción, línea blanca, automotriz
- Insumos propios: chatarra/DRI, ferroaleaciones, energía eléctrica (CFE) y gas natural

Tu tarea es leer UNA publicación del Diario Oficial de la Federación (decreto,
acuerdo o regla) y decidir si afecta de forma real y concreta a TYASA: costos,
ventas, competitividad frente a importaciones, o cumplimiento regulatorio.
Si el decreto cita explícitamente fracciones arancelarias que son de TYASA, el \
impacto es automáticamente Alto o Medio (nunca Bajo), aunque el resto del texto \
parezca genérico. Si el decreto es de un tema sin ninguna conexión real con \
TYASA (ej. otro sector, trámites administrativos sin relación), marca \
tiene_contenido_relevante=false. Responde ÚNICAMENTE con JSON válido, sin \
markdown ni texto fuera del JSON.\
"""

_PROMPT_TMPL_DOF = """\
Publicación del DOF del {fecha_dof} — dependencia: {dependencia}

TÍTULO: {titulo}

{fracciones_block}

TEXTO COMPLETO:
{texto}

Responde con este JSON exacto (sin markdown):

{{
  "tiene_contenido_relevante": true,
  "resumen": "1-2 oraciones de qué dice el decreto/acuerdo, en términos simples",
  "impacto": "Alto | Medio | Bajo",
  "direccion": "Positivo | Negativo | Neutral",
  "productos_afectados": ["Tubería OCTG", "Tubería Mecánica", "Perfiles", "SBQ", "Lámina Negra", "Galvanizado"],
  "explicacion": "2-3 oraciones específicas: qué cambia, por qué impacta a TYASA y magnitud estimada.",
  "fecha_vigencia": "fecha o frase textual de cuándo entra en vigor, si el decreto lo menciona; si no, deja vacío",
  "recomendacion": "Empieza con verbo de acción en segunda persona (Evalúa / Considera / Revisa / Acelera / Prioriza / Asegura). Acción específica dirigida a TYASA."
}}

Si NO hay impacto real para TYASA:
{{"tiene_contenido_relevante": false, "resumen": "", "impacto": "Bajo", \
"direccion": "Neutral", "productos_afectados": [], "explicacion": "", \
"fecha_vigencia": "", "recomendacion": ""}}"""

_DOF_MODELS = ("gemini-3.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash")


def _call_gemini(prompt: str, api_key: str) -> dict | None:
    try:
        from google import genai  # type: ignore
        from google.genai import types as T  # type: ignore

        client = genai.Client(api_key=api_key)
        for model in _DOF_MODELS:
            try:
                cfg_kwargs: dict = dict(
                    system_instruction=_SYSTEM_DOF,
                    temperature=0.1,
                    max_output_tokens=1500,
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
                print(f"[dof_monitor] Gemini SDK {model} error: {e}")
    except ImportError:
        pass

    # Fallback REST
    for model in _DOF_MODELS:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            )
            base_cfg = {"temperature": 0.1, "maxOutputTokens": 1500}
            body = {
                "system_instruction": {"parts": [{"text": _SYSTEM_DOF}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {**base_cfg, "thinkingConfig": {"thinkingBudget": 0}},
            }
            resp = requests.post(url, json=body, timeout=60)
            if resp.status_code == 400:
                body["generationConfig"] = base_cfg
                resp = requests.post(url, json=body, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("`").strip()
                m = re.search(r"\{.*\}", clean, re.DOTALL)
                return json.loads(m.group()) if m else None
            print(f"[dof_monitor] REST {model} {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[dof_monitor] REST error ({model}): {e}")
    return None


def analizar_decreto(item: dict, gemini_key: str) -> dict | None:
    """
    Baja el texto completo de un candidato y lo analiza con Gemini.
    Retorna el dict del item fusionado con el análisis (tiene_contenido_relevante,
    resumen, impacto, direccion, productos_afectados, explicacion, fecha_vigencia,
    recomendacion, fracciones_tyasa) o None si no se pudo bajar/analizar.
    """
    texto = _fetch_texto_completo(item["url"])
    if not texto:
        return None

    fracciones = _extraer_fracciones_tyasa(texto)
    fracciones_block = (
        f"FRACCIONES ARANCELARIAS PROPIAS DE TYASA ENCONTRADAS EN EL TEXTO: {', '.join(fracciones)}"
        if fracciones else
        "No se detectaron fracciones arancelarias propias de TYASA en el texto (puede seguir siendo "
        "relevante por otros motivos: energía, tipo de cambio, comercio exterior en general)."
    )

    prompt = _PROMPT_TMPL_DOF.format(
        fecha_dof=item.get("fecha_dof", ""),
        dependencia=item.get("titulo", ""),
        titulo=item.get("descripcion", "")[:300] or item.get("titulo", ""),
        fracciones_block=fracciones_block,
        texto=texto[:12_000],
    )
    resultado = _call_gemini(prompt, gemini_key)
    if resultado is None:
        return None

    resultado.update({
        "codigo": item["codigo"],
        "titulo_dependencia": item.get("titulo", ""),
        "descripcion": item.get("descripcion", ""),
        "url": item.get("url", ""),
        "fecha_dof": item.get("fecha_dof", ""),
        "fracciones_tyasa": fracciones,
    })
    return resultado


# ── 4. Email de alerta ───────────────────────────────────────────────────────

_IMPACTO_COLORES = {
    "alto":  ("#DC2626", "#FEE2E2"),
    "medio": ("#D97706", "#FEF3C7"),
    "bajo":  ("#64748B", "#F1F5F9"),
}


def construir_email_alerta_dof(analisis: dict) -> tuple[str, str]:
    """Arma el HTML + subject del correo 'ALERTA DOF', estilo aviso urgente
    (no el periódico virtual de noticias — esto se manda aparte e inmediato)."""
    impacto = (analisis.get("impacto") or "Medio").strip()
    color, bg = _IMPACTO_COLORES.get(impacto.lower(), _IMPACTO_COLORES["medio"])
    titulo_dep = analisis.get("titulo_dependencia", "")
    resumen = analisis.get("resumen", "")
    explicacion = analisis.get("explicacion", "")
    recomendacion = analisis.get("recomendacion", "")
    vigencia = analisis.get("fecha_vigencia", "")
    url = analisis.get("url", "#")
    fecha_dof = analisis.get("fecha_dof", "")
    productos = analisis.get("productos_afectados") or []
    fracciones = analisis.get("fracciones_tyasa") or []

    productos_html = "".join(
        f'<span style="display:inline-block;background:#E2E8F0;color:#1B3A5C;'
        f'font-size:11px;font-weight:600;padding:3px 9px;border-radius:10px;'
        f'margin:0 6px 6px 0;">{p}</span>'
        for p in productos
    )
    fracciones_html = (
        f"""<div style="margin-top:10px;font-size:12px;color:#991B1B;">
            <b>Fracciones arancelarias propias de TYASA citadas:</b> {', '.join(fracciones)}
          </div>"""
        if fracciones else ""
    )
    vigencia_html = (
        f'<div style="margin-top:8px;font-size:12.5px;color:#334155;"><b>Vigencia:</b> {vigencia}</div>'
        if vigencia else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Segoe UI,Arial,sans-serif;background:#F3F4F6;margin:0;padding:20px;">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;
     box-shadow:0 2px 8px rgba(0,0,0,.08);">
  <div style="background:#1B3A5C;padding:18px 26px;">
    <h1 style="color:#fff;margin:0;font-size:18px;font-weight:800;letter-spacing:.02em;">
      TYASA BI &middot; ALERTA DOF
    </h1>
    <div style="font-size:10.5px;color:rgba(255,255,255,.6);text-transform:uppercase;
         letter-spacing:.08em;margin-top:2px;">Diario Oficial de la Federación &middot; {fecha_dof}</div>
  </div>
  <div style="padding:20px 26px;background:{bg};border-bottom:3px solid {color};">
    <div style="font-size:10.5px;font-weight:800;color:{color};text-transform:uppercase;
         letter-spacing:.08em;margin-bottom:8px;">Impacto {impacto} &middot; {analisis.get('direccion','')}</div>
    <div style="font-size:11px;color:#64748B;margin-bottom:6px;">{titulo_dep}</div>
    <a href="{url}" style="text-decoration:none;">
      <h2 style="margin:0 0 10px;font-size:18px;line-height:1.35;color:#0F172A;font-weight:700;">{resumen}</h2>
    </a>
    <p style="margin:0;font-size:13.5px;color:#334155;line-height:1.6;">{explicacion}</p>
    {vigencia_html}
    {fracciones_html}
    <div style="margin-top:12px;">{productos_html}</div>
  </div>
  <div style="padding:16px 26px;">
    <div style="font-size:11px;font-weight:700;color:#1B3A5C;text-transform:uppercase;
         letter-spacing:.06em;margin-bottom:4px;">Recomendación</div>
    <p style="margin:0;font-size:13px;color:#334155;line-height:1.6;">{recomendacion}</p>
    <a href="{url}" style="display:inline-block;margin-top:14px;font-size:12px;color:#1B3A5C;font-weight:600;">
      Ver publicación completa en el DOF &rarr;
    </a>
  </div>
  <div style="background:#F9FAFB;padding:12px 26px;border-top:1px solid #E5E7EB;">
    <div style="font-size:11px;color:#9CA3AF;">Generado automáticamente por TYASA BI &middot; No responder este mensaje</div>
  </div>
</div>
</body></html>"""

    subject = f"TYASA BI · ALERTA DOF ({impacto}) · {resumen[:70]}"
    return html, subject
