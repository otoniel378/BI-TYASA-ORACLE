"""
competencia.py — Monitor de Competencia Siderúrgica TYASA BI.

Fuentes:
  1. Google News RSS — noticias en medios por empresa (gratis)
  2. Apify           — posts reales LinkedIn · Instagram · Facebook · Twitter/X
       Actores verificados:
         LinkedIn  : harvestapi~linkedin-company-posts  (sin cookies, 6K+ usuarios)
         Instagram : apify~instagram-scraper
         Facebook  : apify~facebook-posts-scraper
         Twitter/X : apidojo~tweet-scraper
       Requiere APIFY_API_TOKEN en .streamlit/secrets.toml

Caché:
  - Noticias Google : @st.cache_data(ttl=1800) en la página
  - Redes sociales  : cache/social/{red}_{hash_4h}.json  (bloque 4h)
"""

import hashlib
import json
import time
from datetime import datetime, date
from pathlib import Path

import requests

from mercado_noticias.analytics.noticias import _buscar_google_news

# ── Directorios de caché ──────────────────────────────────────────────────────
_ROOT         = Path(__file__).resolve().parents[2]
_SOCIAL_CACHE = _ROOT / "cache" / "social"
_SOCIAL_CACHE.mkdir(parents=True, exist_ok=True)

# ── Apify REST base URL ───────────────────────────────────────────────────────
_APIFY_BASE = "https://api.apify.com/v2"

# ════════════════════════════════════════════════════════════════════════════
# EMPRESAS A MONITOREAR
# linkedin_id = slug exacto de la URL linkedin.com/company/<SLUG>/
# ════════════════════════════════════════════════════════════════════════════
EMPRESAS_COMPETENCIA: dict[str, dict] = {
    "ArcelorMittal": {
        "color": "#1B3A5C", "bg": "#E8EFF6", "icon": "⚙️",
        "linkedin_id":    "arcelormittal",
        "facebook_user":  "ArcelorMittalMexico",
        "instagram_user": "arcelormittalmx",
        "instagram_id":   "10147215594",
        "twitter_user":   "ArcelorMittalMX",
        "queries_google": [
            "ArcelorMittal México producción planta acero",
            "ArcelorMittal acero inversión resultados expansión",
            "ArcelorMittal steel Mexico market production",
            "ArcelorMittal directivos ejecutivos nombramientos",
        ],
    },
    "Ternium": {
        "color": "#DC2626", "bg": "#FEE2E2", "icon": "🔩",
        "linkedin_id":    "ternium",
        "facebook_user":  "Ternium.mx",
        "instagram_user": "aceroternium",
        "twitter_user":   "Ternium",
        "queries_google": [
            "Ternium México expansión producción acero planta",
            "Ternium acero inversión resultados financieros",
            "Ternium steel Mexico capacity expansion",
            "Ternium directivos ejecutivos nombramientos",
        ],
    },
    "Deacero": {
        "color": "#059669", "bg": "#D1FAE5", "icon": "🏭",
        "linkedin_id":    "deacero",
        "facebook_user":  "grupodeacero",
        "instagram_user": "grupodeacero",
        "instagram_id":   "7425175980",
        "twitter_user":   "GRUPODEACERO",
        "queries_google": [
            "Deacero México acero producción planta expansión",
            "Deacero inversión nuevos productos capacidad",
            "Deacero steel Mexico market",
        ],
    },
    "Tenaris TAMSA": {
        "color": "#7C3AED", "bg": "#EDE9FE", "icon": "🔧",
        "linkedin_id":    "tenaris",
        "facebook_user":  "TenarisEvents",
        "instagram_user": "tenaristamsa",
        "twitter_user":   "TenarisTamsa",
        "queries_google": [
            "Tenaris TAMSA tubería OCTG México producción",
            "Tenaris steel pipe results expansion Mexico",
            "TAMSA Veracruz tubería acero producción",
            "Tenaris directivos ejecutivos resultados financieros",
        ],
    },
    "Grupo SIMEC": {
        "color": "#D97706", "bg": "#FEF3C7", "icon": "📊",
        "linkedin_id":    "grupo-simec",
        "facebook_user":  "",
        "instagram_user": "",
        "twitter_user":   "",
        "queries_google": [
            "Grupo SIMEC acero largo México producción",
            "SIMEC acero inversión planta expansión resultados",
            "Grupo SIMEC steel Mexico market",
        ],
    },
    "AHMSA": {
        "color": "#374151", "bg": "#F3F4F6", "icon": "🏗️",
        "linkedin_id":    "altos-hornos-de-mexico",
        "facebook_user":  "",
        "instagram_user": "aceroahmsa",
        "twitter_user":   "AceroAHMSA",
        "queries_google": [
            "AHMSA Altos Hornos México situación producción acero",
            "AHMSA acero Monclova Coahuila noticias",
            "Altos Hornos Mexico steel production",
        ],
    },
    "Gerdau": {
        "color": "#0F766E", "bg": "#CCFBF1", "icon": "⛏️",
        "linkedin_id":    "gerdau",
        "facebook_user":  "gerdaueng",
        "instagram_user": "",
        "twitter_user":   "gerdau",
        "queries_google": [
            "Gerdau México acero producción planta",
            "Gerdau steel Brazil Mexico expansion results",
            "Gerdau acero chatarra horno eléctrico México",
        ],
    },
    "Corsa Acero": {
        "color": "#92400E", "bg": "#FEF3C7", "icon": "🔨",
        "linkedin_id":    "corsa-acero",
        "facebook_user":  "GerdauCorsaOficial",
        "instagram_user": "gerdaucorsamx",
        "twitter_user":   "",
        "queries_google": [
            "Corsa Acero México producción expansión planta",
            "Gerdau Corsa acero inversión nuevos productos México",
            "Corsa steel Mexico market production",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════
# CACHÉ GENÉRICO PARA REDES SOCIALES
# ════════════════════════════════════════════════════════════════════════════

def _social_cache_key(red: str, empresa: str) -> str:
    hoy    = date.today().isoformat()
    bloque = datetime.now().hour // 4
    raw    = f"{red}|{empresa}|{hoy}|{bloque}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _social_cache_load(red: str, empresa: str) -> list[dict] | None:
    key  = _social_cache_key(red, empresa)
    path = _SOCIAL_CACHE / f"{red}_{key}.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Lista vacía = la llamada anterior falló; no la usamos como hit
            return data if data else None
        except Exception:
            pass
    return None


def limpiar_cache_social() -> None:
    """Elimina todos los archivos de caché de redes sociales."""
    for p in _SOCIAL_CACHE.glob("*.json"):
        try:
            p.unlink()
        except Exception:
            pass
    for p in _SOCIAL_CACHE.glob("ig_id_*.txt"):
        try:
            p.unlink()
        except Exception:
            pass


def _social_cache_save(red: str, empresa: str, data: list[dict]) -> None:
    key  = _social_cache_key(red, empresa)
    path = _SOCIAL_CACHE / f"{red}_{key}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[competencia] cache write error ({red}/{empresa}): {e}")


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE NEWS — Noticias por empresa
# ════════════════════════════════════════════════════════════════════════════

def buscar_noticias_empresa(empresa: str, max_r: int = 8) -> list[dict]:
    meta = EMPRESAS_COMPETENCIA.get(empresa)
    if not meta:
        return []
    todos: list[dict] = []
    seen:  set[str]   = set()
    for q in meta["queries_google"][:4]:
        for r in _buscar_google_news(q, max_resultados=6):
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                r["empresa"] = empresa
                r["red"]     = "noticias"
                todos.append(r)
    todos.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return todos[:max_r]


def get_todas_noticias(empresas: list[str], max_r_por_empresa: int = 5) -> list[dict]:
    todos: list[dict] = []
    seen:  set[str]   = set()
    for emp in empresas:
        for n in buscar_noticias_empresa(emp, max_r=max_r_por_empresa):
            url = n.get("url", "")
            if url and url not in seen:
                seen.add(url)
                todos.append(n)
    todos.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return todos


# ════════════════════════════════════════════════════════════════════════════
def _normalizar_fecha(raw) -> str:
    if isinstance(raw, (int, float)):
        try:
            ts = raw / 1000 if raw > 1e10 else raw
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            return ""
    if isinstance(raw, str):
        return raw[:10]
    return ""


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — extrae lista de posts de una respuesta que puede ser list o dict
# ════════════════════════════════════════════════════════════════════════════
def _empresa_badge(empresa: str) -> str:
    meta = EMPRESAS_COMPETENCIA.get(empresa, {})
    c, bg, icon = meta.get("color", "#374151"), meta.get("bg", "#F3F4F6"), meta.get("icon", "🏭")
    return (
        f"<span style='background:{bg};color:{c};padding:2px 9px;"
        f"border-radius:14px;font-size:9px;font-weight:700;"
        f"white-space:nowrap;'>{icon} {empresa}</span>"
    )


_IC_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*{box-sizing:border-box;margin:0;padding:0;}
.ic{font-family:'Inter',sans-serif;color:#191C1D;}
.ic-count{font-size:11px;color:#6B7280;margin-bottom:14px;font-weight:500;letter-spacing:.02em;}

/* ── Social card grid ── */
.ic-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}
.ic-card{background:#fff;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;
  display:flex;flex-direction:column;transition:box-shadow .25s,transform .25s;}
.ic-card:hover{box-shadow:0 8px 28px rgba(0,0,0,.10);transform:translateY(-3px);}
.ic-card-top{height:72px;position:relative;display:flex;align-items:flex-end;
  padding:10px 12px;overflow:hidden;}
.ic-card-top::before{content:'';position:absolute;inset:0;background:rgba(0,0,0,.18);}
.ic-net-pill{position:relative;z-index:1;display:inline-flex;align-items:center;gap:4px;
  padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;
  background:rgba(255,255,255,.92);white-space:nowrap;}
.ic-card-body{padding:13px 14px;flex:1;display:flex;flex-direction:column;gap:8px;}
.ic-card-header{display:flex;justify-content:space-between;align-items:center;gap:4px;}
.ic-company-row{display:flex;align-items:center;gap:7px;min-width:0;}
.ic-avatar{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:13px;flex-shrink:0;}
.ic-co-name{font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ic-date{font-size:10px;color:#9CA3AF;white-space:nowrap;flex-shrink:0;}
.ic-text{font-size:11.5px;color:#4B5563;line-height:1.64;flex:1;
  display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;}
.ic-card-footer{display:flex;justify-content:space-between;align-items:center;
  padding-top:9px;border-top:1px solid #F3F4F6;margin-top:auto;}
.ic-stats{display:flex;gap:9px;flex-wrap:wrap;}
.ic-stat{display:flex;align-items:center;gap:3px;font-size:10px;color:#6B7280;font-weight:600;}
.ic-link{display:flex;align-items:center;justify-content:center;width:26px;height:26px;
  border-radius:8px;background:#F3F4F6;color:#374151;text-decoration:none;font-size:15px;
  transition:background .2s,color .2s;flex-shrink:0;}
.ic-link:hover{background:#384CD2;color:#fff;}

/* ── News card grid ── */
.ic-news-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}
.ic-nc{background:#fff;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;
  display:flex;flex-direction:column;transition:box-shadow .2s;}
.ic-nc:hover{box-shadow:0 6px 20px rgba(0,0,0,.08);}
.ic-nc-top{height:4px;}
.ic-nc-body{padding:14px 15px;flex:1;display:flex;flex-direction:column;gap:7px;}
.ic-nc-meta{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px;}
.ic-nc-date{font-size:9px;color:#9CA3AF;}
.ic-nc-title{font-size:14px;font-weight:700;color:#111827;line-height:1.44;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
.ic-nc-desc{font-size:11px;color:#6B7280;line-height:1.62;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.ic-nc-footer{display:flex;justify-content:space-between;align-items:center;
  margin-top:auto;padding-top:9px;border-top:1px solid #F3F4F6;}
.ic-source{font-size:9px;font-weight:700;padding:2px 8px;border-radius:10px;
  background:#F3F4F6;color:#6B7280;}
.ic-read{font-size:10px;font-weight:700;text-decoration:none;}

/* ── Benchmarking table ── */
.bm-table{width:100%;border-collapse:collapse;font-size:12px;}
.bm-table th{padding:9px 12px;font-size:10px;font-weight:700;color:#6B7280;
  text-align:left;background:#F8FAFC;border-bottom:2px solid #E2E8F0;letter-spacing:.04em;}
.bm-table td{padding:10px 12px;border-bottom:1px solid #F3F4F6;color:#374151;}
.bm-table tr:hover td{background:#F9FAFB;}
.bm-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;
  border-radius:20px;font-size:10px;font-weight:700;white-space:nowrap;}
.bm-bar-wrap{display:flex;align-items:center;gap:8px;}
.bm-bar-bg{flex:1;height:6px;background:#F3F4F6;border-radius:3px;overflow:hidden;min-width:60px;}
.bm-bar-fill{height:100%;border-radius:3px;}
.bm-bar-val{font-size:11px;font-weight:700;color:#374151;white-space:nowrap;}

/* ── Empty states ── */
.ic-empty{text-align:center;padding:52px 0;color:#9CA3AF;font-family:'Inter',sans-serif;}
.ic-empty-icon{font-size:42px;margin-bottom:12px;}
.ic-empty-title{font-size:14px;font-weight:600;margin-bottom:6px;color:#6B7280;}
.ic-empty-sub{font-size:11.5px;color:#D1D5DB;max-width:360px;margin:0 auto;line-height:1.55;}
</style>
"""


def render_feed_noticias(
    noticias: list[dict],
    empresas_activas: list[str],
    fecha_desde: str = "",
    fecha_hasta: str = "",
) -> str:
    filtradas = [
        n for n in noticias
        if n.get("empresa") in empresas_activas
        and (not fecha_desde or (n.get("fecha_pub") or "") >= fecha_desde)
        and (not fecha_hasta or (n.get("fecha_pub") or "") <= fecha_hasta)
    ]
    if not filtradas:
        return (
            _IC_CSS + '<div class="ic"><div class="ic-empty">'
            '<div class="ic-empty-icon">📭</div>'
            '<div class="ic-empty-title">Sin noticias en el período</div>'
            '<div class="ic-empty-sub">Ajusta el rango de fechas o selecciona más empresas.</div>'
            '</div></div>'
        )
    cards = []
    for n in filtradas:
        empresa = n.get("empresa", "")
        meta    = EMPRESAS_COMPETENCIA.get(empresa, {})
        c       = meta.get("color", "#374151")
        titulo  = (n.get("titulo", "") or "Sin título").strip()
        desc    = (n.get("descripcion", "") or "").strip()[:200]
        fuente  = (n.get("fuente", "") or "").strip()
        url     = (n.get("url", "") or "").strip()
        fecha   = (n.get("fecha_pub", "") or "").strip()
        leer    = (
            f'<a href="{url}" target="_blank" class="ic-read" style="color:{c};">Leer →</a>'
        ) if url else ""
        cards.append(
            f'<div class="ic-nc">'
            f'<div class="ic-nc-top" style="background:{c};"></div>'
            f'<div class="ic-nc-body">'
            f'<div class="ic-nc-meta">{_empresa_badge(empresa)}'
            f'<span class="ic-nc-date">📅 {fecha}</span></div>'
            f'<div class="ic-nc-title">{titulo}</div>'
            f'<div class="ic-nc-desc">{desc}</div>'
            f'<div class="ic-nc-footer"><span class="ic-source">{fuente}</span>{leer}</div>'
            f'</div></div>'
        )
    return (
        _IC_CSS
        + f'<div class="ic">'
        f'<div class="ic-count">{len(filtradas)} artículo(s) en el período</div>'
        f'<div class="ic-news-grid">{"".join(cards)}</div>'
        f'</div>'
    )


def render_feed_social(
    posts: list[dict],
    empresas_activas: list[str],
    redes_activas: list[str],
    fecha_desde: str = "",
    fecha_hasta: str = "",
    ordenar: str = "reciente",
) -> str:
    filtrados = [
        p for p in posts
        if p.get("empresa") in empresas_activas
        and p.get("red") in redes_activas
        and (not fecha_desde or (p.get("fecha_pub") or "") >= fecha_desde)
        and (not fecha_hasta or (p.get("fecha_pub") or "") <= fecha_hasta)
    ]
    if ordenar == "likes":
        filtrados.sort(key=lambda x: x.get("likes", 0) or 0, reverse=True)
    elif ordenar == "engagement":
        filtrados.sort(key=lambda x: (x.get("likes", 0) or 0) + (x.get("comentarios", 0) or 0), reverse=True)
    else:
        filtrados.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)

    if not filtrados:
        return (
            _IC_CSS + '<div class="ic"><div class="ic-empty">'
            '<div class="ic-empty-icon">📱</div>'
            '<div class="ic-empty-title">Sin publicaciones en el período</div>'
            '<div class="ic-empty-sub">Instagram está temporalmente bloqueado por rate-limit. '
            'Las tarjetas de presencia de LinkedIn, Facebook y X aparecen en las redes '
            'correspondientes. Haz clic en 🔄 Actualizar para reintentar Instagram.</div>'
            '</div></div>'
        )

    cards = []
    for p in filtrados:
        empresa   = p.get("empresa", "")
        red       = p.get("red", "")
        meta_e    = EMPRESAS_COMPETENCIA.get(empresa, {})
        meta_r    = _RED_META.get(red, {"label": red, "color": "#6B7280", "bg": "#F3F4F6", "icon": "🌐"})
        c         = meta_e.get("color", "#374151")
        bg        = meta_e.get("bg", "#F3F4F6")
        icon      = meta_e.get("icon", "🏭")
        rc        = meta_r["color"]
        texto     = (p.get("texto", "") or "").strip()
        snippet   = texto[:220] + ("…" if len(texto) > 220 else "")
        fecha     = (p.get("fecha_pub", "") or "").strip()
        likes     = p.get("likes", 0) or 0
        coments   = p.get("comentarios", 0) or 0
        shares    = p.get("compartidos", 0) or 0
        vistas    = p.get("vistas", 0) or 0
        url       = (p.get("url", "") or "").strip()
        es_perfil = p.get("es_perfil", False)

        net_pill = (
            f'<span class="ic-net-pill" style="color:{rc};">'
            f'{meta_r["icon"]} {meta_r["label"]}</span>'
        )
        stats_html = []
        if es_perfil:
            seg_label = "👥 Seguidores"
            if red == "facebook":
                seg_label = "👍 Likes"
            if likes:  stats_html.append(f'<span class="ic-stat">{seg_label}: {likes:,}</span>')
            if shares: stats_html.append(f'<span class="ic-stat">📝 {shares:,} tweets</span>')
        else:
            if likes:   stats_html.append(f'<span class="ic-stat">❤️ {likes:,}</span>')
            if coments: stats_html.append(f'<span class="ic-stat">💬 {coments:,}</span>')
            if shares:  stats_html.append(f'<span class="ic-stat">🔄 {shares:,}</span>')
            if vistas:  stats_html.append(f'<span class="ic-stat">👁 {vistas:,}</span>')
        if not stats_html:
            stats_html.append('<span class="ic-stat" style="color:#D1D5DB;">Sin métricas</span>')

        link_html = f'<a href="{url}" target="_blank" class="ic-link" title="Ver original">↗</a>' if url else ""

        cards.append(
            f'<div class="ic-card">'
            f'<div class="ic-card-top" style="background:{c};">{net_pill}</div>'
            f'<div class="ic-card-body">'
            f'<div class="ic-card-header">'
            f'<div class="ic-company-row">'
            f'<div class="ic-avatar" style="background:{bg};color:{c};">{icon}</div>'
            f'<span class="ic-co-name" style="color:{c};">{empresa}</span>'
            f'</div>'
            f'<span class="ic-date">{fecha}</span>'
            f'</div>'
            f'<div class="ic-text">{snippet if snippet else "<em style=\'color:#D1D5DB;\'>Sin texto disponible</em>"}</div>'
            f'<div class="ic-card-footer">'
            f'<div class="ic-stats">{"".join(stats_html)}</div>'
            f'{link_html}'
            f'</div>'
            f'</div>'
            f'</div>'
        )
    return (
        _IC_CSS
        + f'<div class="ic">'
        f'<div class="ic-count">{len(filtrados)} publicación(es)</div>'
        f'<div class="ic-grid">{"".join(cards)}</div>'
        f'</div>'
    )

def _apify_run(actor_id: str, run_input: dict, api_token: str,
               timeout_secs: int = 60) -> list[dict]:
    """Ejecuta un actor de Apify y devuelve los items del dataset resultante."""
    url_run = f"{_APIFY_BASE}/acts/{actor_id}/runs"
    try:
        resp = requests.post(
            url_run,
            json=run_input,
            params={"token": api_token, "waitForFinish": timeout_secs},
            timeout=timeout_secs + 10,
        )
        if resp.status_code not in (200, 201):
            print(f"[apify] {actor_id} HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        run_data = resp.json().get("data", {})
        dataset_id = run_data.get("defaultDatasetId", "")
        if not dataset_id:
            print(f"[apify] {actor_id}: no dataset ID en respuesta")
            return []
        items_resp = requests.get(
            f"{_APIFY_BASE}/datasets/{dataset_id}/items",
            params={"token": api_token, "clean": "true", "limit": 20},
            timeout=20,
        )
        if items_resp.status_code != 200:
            print(f"[apify] dataset {dataset_id} HTTP {items_resp.status_code}")
            return []
        return items_resp.json() if isinstance(items_resp.json(), list) else []
    except Exception as e:
        print(f"[apify] {actor_id} error: {e}")
        return []


def _apify_instagram(empresa: str, api_token: str, n: int = 8) -> list[dict]:
    meta     = EMPRESAS_COMPETENCIA.get(empresa, {})
    username = meta.get("instagram_user", "")
    if not username:
        return []
    # Actor verificado: apify~instagram-scraper (4.7★, 322K usuarios)
    items = _apify_run("apify~instagram-scraper", {
        "directUrls":    [f"https://www.instagram.com/{username}/"],
        "resultsType":   "posts",
        "resultsLimit":  n,
        "addParentData": False,
    }, api_token)
    posts = []
    for it in items[:n]:
        img = (it.get("displayUrl") or it.get("thumbnailUrl") or
               (it.get("images") or [None])[0] or "")
        posts.append({
            "texto":       (it.get("caption") or it.get("alt") or "")[:2000],
            "fecha_pub":   _normalizar_fecha(it.get("timestamp") or it.get("takenAt")),
            "likes":       int(it.get("likesCount") or 0),
            "comentarios": int(it.get("commentsCount") or 0),
            "compartidos": 0,
            "vistas":      int(it.get("videoViewCount") or it.get("videoPlayCount") or 0),
            "url":         it.get("url") or it.get("shortCode") or "",
            "imagen":      img,
            "empresa":     empresa,
            "red":         "instagram",
        })
    return posts


def _apify_facebook(empresa: str, api_token: str, n: int = 8) -> list[dict]:
    meta    = EMPRESAS_COMPETENCIA.get(empresa, {})
    fb_user = meta.get("facebook_user", "")
    if not fb_user:
        return []
    # Actor verificado: apify~facebook-posts-scraper
    # Devuelve: text, time, likes, comments, shares, url, media
    items = _apify_run("apify~facebook-posts-scraper", {
        "startUrls": [{"url": f"https://www.facebook.com/{fb_user}"}],
        "maxPosts":  n,
    }, api_token)
    posts = []
    for it in items[:n]:
        if not isinstance(it, dict):
            continue
        posts.append({
            "texto":       (it.get("text") or it.get("story") or "")[:2000],
            "fecha_pub":   _normalizar_fecha(it.get("time") or it.get("timestamp")),
            "likes":       int(it.get("likes") or it.get("reactions") or 0),
            "comentarios": int(it.get("comments") or 0),
            "compartidos": int(it.get("shares") or 0),
            "vistas":      0,
            "url":         it.get("url") or it.get("postUrl") or "",
            "empresa":     empresa,
            "red":         "facebook",
        })
    return posts[:n]


def _apify_twitter(empresa: str, api_token: str, n: int = 8) -> list[dict]:
    meta   = EMPRESAS_COMPETENCIA.get(empresa, {})
    handle = meta.get("twitter_user", "")
    if not handle:
        return []
    # Actor verificado: apidojo~tweet-scraper (startUrls de perfil)
    # Devuelve: fullText, createdAt, likeCount, retweetCount, replyCount, viewCount, url
    items = _apify_run("apidojo~tweet-scraper", {
        "startUrls": [f"https://twitter.com/{handle}"],
        "maxItems":  n,
    }, api_token)
    posts = []
    for it in items[:n]:
        posts.append({
            "texto":       (it.get("fullText") or it.get("text") or "")[:2000],
            "fecha_pub":   _normalizar_fecha(it.get("createdAt") or it.get("created_at")),
            "likes":       int(it.get("likeCount") or it.get("favorite_count") or 0),
            "comentarios": int(it.get("replyCount") or it.get("reply_count") or 0),
            "compartidos": int(it.get("retweetCount") or it.get("retweet_count") or 0),
            "vistas":      int(it.get("viewCount") or it.get("views") or 0),
            "url":         it.get("twitterUrl") or it.get("url") or "",
            "empresa":     empresa,
            "red":         "twitter",
        })
    return posts


def _apify_linkedin(empresa: str, api_token: str, n: int = 8) -> list[dict]:
    """Posts reales de LinkedIn vía Apify.

    Actor: harvestapi~linkedin-company-posts (No cookies required, 6K+ usuarios)
    Estructura respuesta: postedAt.date, engagement.{likes,comments,shares},
                          content, shareLinkedinUrl
    """
    meta  = EMPRESAS_COMPETENCIA.get(empresa, {})
    li_id = meta.get("linkedin_id", "")
    if not li_id:
        return []
    items = _apify_run("harvestapi~linkedin-company-posts", {
        "companyUrls": [f"https://www.linkedin.com/company/{li_id}/"],
        "maxPosts":    n,
    }, api_token)
    posts = []
    for it in items[:n]:
        texto = (it.get("content") or it.get("text") or it.get("commentary") or "").strip()
        # postedAt es un dict: {"date": "2026-07-08T21:02:24.776Z", ...}
        posted_at = it.get("postedAt") or {}
        fecha_raw = (posted_at.get("date") if isinstance(posted_at, dict)
                     else posted_at) or it.get("createdAt") or ""
        # engagement es un dict: {"likes": N, "comments": N, "shares": N}
        eng = it.get("engagement") or {}
        likes = int(eng.get("likes") or 0) if isinstance(eng, dict) else 0
        coms  = int(eng.get("comments") or 0) if isinstance(eng, dict) else 0
        shares= int(eng.get("shares") or 0) if isinstance(eng, dict) else 0
        url   = it.get("shareLinkedinUrl") or it.get("url") or ""
        posts.append({
            "texto":       texto[:2000],
            "fecha_pub":   _normalizar_fecha(fecha_raw),
            "likes":       likes,
            "comentarios": coms,
            "compartidos": shares,
            "vistas":      0,
            "url":         url,
            "empresa":     empresa,
            "red":         "linkedin",
        })
    return posts


def get_apify_posts(
    empresa: str,
    api_token: str,
    redes: list[str],
    n: int = 8,
    force_refresh: bool = False,
    li_cookie: str = "",          # ya no se usa, se mantiene por compatibilidad
) -> list[dict]:
    """Obtiene posts reales de redes sociales vía Apify para una empresa.
    Las 4 redes funcionan sin cookies adicionales.
    """
    if not api_token:
        return []

    _fn_map = {
        "instagram": _apify_instagram,
        "facebook":  _apify_facebook,
        "twitter":   _apify_twitter,
        "linkedin":  _apify_linkedin,
    }

    todos: list[dict] = []
    for red in redes:
        fn = _fn_map.get(red)
        if not fn:
            continue
        cache_key_apify = f"apify_{red}"
        cached = _social_cache_load(cache_key_apify, empresa)
        if cached is not None and not force_refresh:
            todos.extend(cached[:n])
            continue
        print(f"[apify] Obteniendo {red} para {empresa}…")
        posts = fn(empresa, api_token, n=n)
        _social_cache_save(cache_key_apify, empresa, posts)
        todos.extend(posts)

    todos.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return todos


def get_apify_feed(
    empresas: list[str],
    api_token: str,
    redes: list[str] | None = None,
    n_por_empresa: int = 8,
    force_refresh: bool = False,
) -> list[dict]:
    """Agrega posts Apify de todas las empresas y redes en una sola lista."""
    _redes = redes or ["linkedin", "instagram", "facebook", "twitter"]
    todos: list[dict] = []
    for empresa in empresas:
        todos.extend(get_apify_posts(empresa, api_token, _redes, n=n_por_empresa,
                                     force_refresh=force_refresh))
    todos.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return todos


# ════════════════════════════════════════════════════════════════════════════
# NIVEL 1 + 2 — Métricas de benchmarking
# ════════════════════════════════════════════════════════════════════════════

def calcular_metricas_benchmarking(
    posts: list[dict],
    noticias: list[dict],
    empresas: list[str],
    fecha_desde: str = "",
    fecha_hasta: str = "",
) -> dict[str, dict]:
    """
    Calcula métricas de actividad y engagement por empresa.
    Cubre Nivel 1 (actividad) y Nivel 2 (engagement, top posts, timing).
    """
    from collections import defaultdict
    import datetime as _dt

    _DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    result: dict[str, dict] = {}
    for emp in empresas:
        result[emp] = {
            "total_posts": 0,
            "por_red": {"linkedin": 0, "instagram": 0, "facebook": 0, "twitter": 0},
            "noticias": 0, "posts_semana": 0.0,
            "avg_likes": 0.0, "avg_comentarios": 0.0, "avg_compartidos": 0.0,
            "total_engagement": 0, "avg_engagement": 0.0,
            "top_posts": [],
            "dias": {d: 0 for d in _DIAS},
            "red_mas_activa": "—", "red_mas_engagement": "—",
        }

    posts_filtrados = [
        p for p in posts
        if p.get("empresa") in empresas
        and (not fecha_desde or (p.get("fecha_pub") or "") >= fecha_desde)
        and (not fecha_hasta or (p.get("fecha_pub") or "") <= fecha_hasta)
    ]

    _likes_acum:  dict[str, list] = defaultdict(list)
    _coms_acum:   dict[str, list] = defaultdict(list)
    _shares_acum: dict[str, list] = defaultdict(list)
    _eng_por_red: dict[str, dict] = defaultdict(lambda: defaultdict(int))

    for p in posts_filtrados:
        emp   = p.get("empresa", "")
        red   = p.get("red", "")
        if emp not in result:
            continue
        likes  = int(p.get("likes", 0) or 0)
        coms   = int(p.get("comentarios", 0) or 0)
        shares = int(p.get("compartidos", 0) or 0)

        result[emp]["total_posts"] += 1
        if red in result[emp]["por_red"]:
            result[emp]["por_red"][red] += 1
        _likes_acum[emp].append(likes)
        _coms_acum[emp].append(coms)
        _shares_acum[emp].append(shares)
        _eng_por_red[emp][red] += likes + coms + shares

        fecha_str = (p.get("fecha_pub") or "")[:10]
        if fecha_str:
            try:
                dia_name = _DIAS[_dt.date.fromisoformat(fecha_str).weekday()]
                result[emp]["dias"][dia_name] += 1
            except Exception:
                pass

    dias_periodo = 30
    if fecha_desde and fecha_hasta:
        try:
            dias_periodo = max(1, (_dt.date.fromisoformat(fecha_hasta) -
                                   _dt.date.fromisoformat(fecha_desde)).days)
        except Exception:
            pass
    semanas = max(1, dias_periodo / 7)

    for emp in empresas:
        n = result[emp]["total_posts"]
        if n == 0:
            continue
        _avg = lambda lst: round(sum(lst) / len(lst), 1) if lst else 0.0
        result[emp]["avg_likes"]        = _avg(_likes_acum[emp])
        result[emp]["avg_comentarios"]  = _avg(_coms_acum[emp])
        result[emp]["avg_compartidos"]  = _avg(_shares_acum[emp])
        total_eng = sum(_likes_acum[emp]) + sum(_coms_acum[emp]) + sum(_shares_acum[emp])
        result[emp]["total_engagement"] = total_eng
        result[emp]["avg_engagement"]   = round(total_eng / n, 1)
        result[emp]["posts_semana"]     = round(n / semanas, 1)

        emp_posts = sorted(
            [p for p in posts_filtrados if p.get("empresa") == emp],
            key=lambda x: (x.get("likes",0) or 0)+(x.get("comentarios",0) or 0)+(x.get("compartidos",0) or 0),
            reverse=True,
        )
        result[emp]["top_posts"] = emp_posts[:3]

        por_red = result[emp]["por_red"]
        result[emp]["red_mas_activa"] = (
            max(por_red, key=lambda r: por_red[r]) if any(por_red.values()) else "—"
        )
        eng_red = dict(_eng_por_red[emp])
        result[emp]["red_mas_engagement"] = (
            max(eng_red, key=lambda r: eng_red[r]) if eng_red else "—"
        )

    for n in noticias:
        emp = n.get("empresa", "")
        if emp in result:
            result[emp]["noticias"] += 1

    return result


# ════════════════════════════════════════════════════════════════════════════
# NIVEL 3 — Clasificación de temas con IA (Gemini)
# ════════════════════════════════════════════════════════════════════════════

_TEMAS_SIDERURGICOS = [
    "Expansión / Capacidad",
    "Sustentabilidad",
    "Recursos Humanos",
    "Producto / Innovación",
    "Resultados Financieros",
    "Responsabilidad Social",
    "Marketing / Marca",
    "Otro",
]


def clasificar_temas_ia(posts: list[dict], gemini_key: str) -> dict[str, dict[str, int]]:
    """
    Clasifica posts por tema siderúrgico usando Gemini.
    Retorna: {"Ternium": {"Expansión / Capacidad": 3, "Sustentabilidad": 2, ...}}
    """
    if not gemini_key or not posts:
        return {}

    batch    = posts[:40]
    temas_str = " | ".join(_TEMAS_SIDERURGICOS)
    lineas   = [
        f"{i}|{p.get('empresa','')}|{p.get('red','')}|{(p.get('texto') or '')[:200].replace(chr(10),' ')}"
        for i, p in enumerate(batch)
    ]

    prompt = f"""Eres un analista de inteligencia competitiva para la industria siderúrgica mexicana.
Clasifica cada publicación en UNO de estos temas: {temas_str}

Publicaciones (formato: índice|empresa|red|texto):
{chr(10).join(lineas)}

Responde SOLO con JSON (sin texto adicional):
{{
  "clasificaciones": [
    {{"idx": 0, "empresa": "nombre", "tema": "tema exacto de la lista"}},
    ...
  ]
}}"""

    try:
        from mercado_noticias.analytics.ai_analysis import _call_gemini_text
        respuesta = _call_gemini_text(prompt, gemini_key)
        if not respuesta:
            return {}
        import re
        match = re.search(r"\{.*\}", respuesta, re.DOTALL)
        if not match:
            return {}
        data = json.loads(match.group())
    except Exception as e:
        print(f"[competencia] clasificar_temas_ia error: {e}")
        return {}

    from collections import defaultdict
    result: dict[str, dict[str, int]] = defaultdict(lambda: {t: 0 for t in _TEMAS_SIDERURGICOS})
    for cl in data.get("clasificaciones", []):
        idx  = cl.get("idx", -1)
        if 0 <= idx < len(batch):
            emp  = batch[idx].get("empresa", "")
            tema = cl.get("tema", "Otro")
            if tema not in _TEMAS_SIDERURGICOS:
                tema = "Otro"
            if emp:
                result[emp][tema] += 1
    return dict(result)
