"""
noticias.py — Búsqueda de noticias financieras en tiempo real.

Fuentes (en orden de prioridad):
  1. Google News RSS   — gratis, sin límite, sin API key, tiempo real
  2. NewsAPI           — como respaldo (100 req/día plan gratuito)
API Key NewsAPI: 6207d70b95eb40ea89b8081860b73aa3
"""

import xml.etree.ElementTree as ET
import urllib.parse
import pandas as pd
import requests
from datetime import datetime, timedelta
import hashlib

NEWSAPI_KEY = "6207d70b95eb40ea89b8081860b73aa3"
NEWSAPI_URL = "https://newsapi.org/v2/everything"

# ── Queries optimizadas por variable ─────────────────────────────────────────
# Lista: [query_corta_google, keyword_newsapi_1, keyword_newsapi_2, ...]
QUERIES = {
    "Brent_USD":         ["Brent crude oil price",      "Brent oil", "crude oil OPEC", "petróleo Brent precio"],
    "WTI_USD":           ["WTI crude oil price",        "West Texas oil", "crude oil Trump Iran", "petróleo precio"],
    "Gas_HenryHub_USD":  ["Henry Hub natural gas",      "natural gas price USA", "gas natural EE.UU."],
    "Gas_TTF_Europa":    ["TTF natural gas Europe",     "gas natural Europa precio", "European gas energy"],
    "Mineral_Hierro":    ["iron ore price",             "mineral hierro precio", "Vale iron ore", "Rio Tinto iron"],
    "Cobre_USD":         ["copper price LME",           "precio cobre Chile", "copper market"],
    "Aluminio_USD":      ["aluminum price LME",         "aluminium price", "aluminio precio LME"],
    "ETF_Acero_Global":  ["steel price global",         "precio acero global", "HRC steel hot rolled"],
    "Ternium_MX":        ["Ternium steel Mexico",       "Ternium acero", "acero México mercado"],
    "ArcelorMittal":     ["ArcelorMittal steel",        "ArcelorMittal results", "acería global"],
    "Nucor_EAF":         ["Nucor steel scrap",          "Nucor Corporation", "steel scrap price EAF"],
    "SteelDynamics_EAF": ["Steel Dynamics EAF",        "Steel Dynamics Inc", "electric arc furnace steel"],
    "ZIM_Contenedor":    ["container shipping rates",   "ZIM shipping", "flete contenedor Asia precio"],
    "ETF_Flete_Seco":    ["Baltic Dry Index shipping",  "BDI Baltic Dry", "dry bulk freight rates"],
    "BDI_Baltic_Dry":    ["Baltic Dry Index BDI",       "shipping freight rates", "bulk carrier rates"],
    "Matson_Pacifico":   ["Pacific shipping freight",   "Matson shipping", "transpacific freight"],
    "StarBulk":          ["Star Bulk shipping",         "dry bulk carrier market", "bulk shipping rates"],
    "VIX":               ["VIX volatility index",       "market volatility fear", "S&P 500 volatility"],
    "SP500":             ["S&P 500 market",             "stock market Wall Street", "bolsa valores EE.UU."],
    "Oro_USD":           ["gold price rally",           "gold market safe haven", "precio oro onza"],
    "Dolar_Index":       ["US dollar index DXY",        "dólar índice fortaleza", "dollar strength Fed"],
    "Bonos_20y":         ["US Treasury bonds yield",   "bonos tesoro EE.UU.", "interest rates Fed"],
    "Nikkei_Japon":      ["Nikkei Japan stock market", "bolsa Tokio Japón", "Japan economy yen"],
    "KOSPI_Corea":       ["KOSPI Korea stock market",  "bolsa Corea", "Korea economy POSCO"],
    "ETF_China":         ["China stock market economy","economía China Shanghai", "China trade tariffs"],
    "ETF_Alemania":      ["Germany economy DAX",       "Alemania economía acero", "ThyssenKrupp DAX"],
    "ETF_Mexico":        ["Mexico economy stocks",     "México economía BMV", "nearshoring México inversión"],
    "USD_MXN":           ["peso mexicano tipo cambio", "USD MXN dólar peso", "Banxico tipo cambio"],
    "ETF_Japon":         ["Japan economy manufacturing","Japón manufactura exportación", "yen dollar"],
    "ETF_Corea":         ["Korea economy Samsung",     "Corea economía manufactura", "Korea exports"],
    "ETF_Emergentes":    ["emerging markets economy",  "mercados emergentes", "EM stocks global"],
}


# ════════════════════════════════════════════════════════════════════════════
# FUENTE 1 — Google News RSS (principal, gratis, sin límites)
# ════════════════════════════════════════════════════════════════════════════

def _buscar_google_news(query: str, max_resultados: int = 10) -> list[dict]:
    """
    Busca en Google News RSS. Sin API key, sin límites diarios.
    Soporta español e inglés automáticamente según la query.
    """
    resultados = []
    # Buscar en inglés y español
    for hl, gl, ceid in [("en", "US", "US:en"), ("es", "MX", "MX:es")]:
        url = (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode({
                "q":    query,
                "hl":   hl,
                "gl":   gl,
                "ceid": ceid,
            })
        )
        try:
            resp = requests.get(url, timeout=8, headers={
                "User-Agent": "Mozilla/5.0 (compatible; TyasaBI/1.0)"
            })
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                continue
            for item in channel.findall("item")[:max_resultados]:
                titulo = item.findtext("title", "").strip()
                link   = item.findtext("link",  "").strip()
                desc   = item.findtext("description", "").strip()
                # Limpiar HTML del description si viene de Google
                if "<" in desc:
                    import re
                    desc = re.sub(r"<[^>]+>", "", desc).strip()
                pub_raw = item.findtext("pubDate", "")
                # Parsear fecha: "Wed, 09 Apr 2026 10:00:00 GMT"
                try:
                    from email.utils import parsedate_to_datetime
                    fecha_pub = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d")
                except Exception:
                    fecha_pub = pub_raw[:10] if pub_raw else ""
                # Fuente: viene en <source> o en el título "- Fuente"
                fuente_el = item.find("source")
                fuente = fuente_el.text if fuente_el is not None else ""
                if not fuente and " - " in titulo:
                    fuente = titulo.rsplit(" - ", 1)[-1]
                    titulo = titulo.rsplit(" - ", 1)[0].strip()

                if titulo and link:
                    resultados.append({
                        "titulo":      titulo,
                        "descripcion": desc,
                        "fuente":      fuente,
                        "url":         link,
                        "fecha_pub":   fecha_pub,
                        "fuente_api":  "Google News",
                    })
        except Exception as e:
            print(f"Google News RSS error ({hl}): {e}")

    return resultados


# ════════════════════════════════════════════════════════════════════════════
# FUENTE 2 — NewsAPI (respaldo)
# ════════════════════════════════════════════════════════════════════════════

def _buscar_newsapi(query: str, desde: str, hasta: str, max_resultados: int = 5) -> list[dict]:
    """Busca en NewsAPI solo en inglés (más resultados en plan free)."""
    params = {
        "q":        query,
        "from":     desde,
        "to":       hasta,
        "sortBy":   "publishedAt",
        "language": "en",
        "pageSize": max_resultados,
        "apiKey":   NEWSAPI_KEY,
    }
    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=8)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if data.get("status") != "ok":
            return []
        resultados = []
        for art in data.get("articles", []):
            resultados.append({
                "titulo":      art.get("title", ""),
                "descripcion": art.get("description", ""),
                "fuente":      art.get("source", {}).get("name", ""),
                "url":         art.get("url", ""),
                "fecha_pub":   (art.get("publishedAt") or "")[:10],
                "fuente_api":  "NewsAPI",
            })
        return resultados
    except Exception as e:
        print(f"NewsAPI error: {e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ════════════════════════════════════════════════════════════════════════════

def buscar_noticias_actuales(
    variable: str,
    dias: int = 7,
    max_resultados: int = 10,
) -> list[dict]:
    """
    Busca noticias de los últimos N días para una variable de mercado.
    Prioridad: Google News RSS → NewsAPI como respaldo.
    Sin límites de requests. Retorna hasta max_resultados artículos deduplicados.
    """
    queries = QUERIES.get(variable, [variable.replace("_", " ")])

    # Google News: busca con la primera query (más corta y específica)
    resultados = _buscar_google_news(queries[0], max_resultados=max_resultados)

    # Si Google News no dio suficientes, complementar con NewsAPI
    if len(resultados) < 3:
        hasta  = datetime.utcnow().strftime("%Y-%m-%d")
        desde  = (datetime.utcnow() - timedelta(days=dias)).strftime("%Y-%m-%d")
        newsapi_res = _buscar_newsapi(queries[0], desde, hasta, max_resultados=max_resultados)
        resultados.extend(newsapi_res)

    # Deduplicar por URL
    seen, final = set(), []
    for item in resultados:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            final.append(item)

    return final[:max_resultados]


def buscar_noticias_multifuente(
    variable: str,
    ventana_dias: int = 14,
    max_resultados: int = 15,
) -> list[dict]:
    """
    Búsqueda ampliada con múltiples queries para la misma variable.
    Retorna hasta max_resultados noticias deduplicadas, ordenadas por fecha.
    """
    queries = QUERIES.get(variable, [variable.replace("_", " ")])
    todos = []

    for q in queries[:3]:  # hasta 3 queries por variable
        res = _buscar_google_news(q, max_resultados=6)
        todos.extend(res)

    # Respaldo NewsAPI con la primera query
    if len(todos) < 5:
        hasta = datetime.utcnow().strftime("%Y-%m-%d")
        desde = (datetime.utcnow() - timedelta(days=ventana_dias)).strftime("%Y-%m-%d")
        todos.extend(_buscar_newsapi(queries[0], desde, hasta, max_resultados=8))

    # Deduplicar y ordenar por fecha desc
    seen, final = set(), []
    for item in todos:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            final.append(item)

    # Ordenar por fecha descendente
    def _fecha_sort(x):
        try:
            return x.get("fecha_pub", "") or ""
        except Exception:
            return ""

    final.sort(key=_fecha_sort, reverse=True)
    return final[:max_resultados]


def get_google_news_url(variable: str) -> str:
    """Retorna URL de Google News para abrir en el browser con la query de la variable."""
    queries = QUERIES.get(variable, [variable.replace("_", " ")])
    q = urllib.parse.quote_plus(queries[0])
    return f"https://news.google.com/search?q={q}&hl=es&gl=MX&ceid=MX:es"


# ── Funciones de compatibilidad hacia atrás ───────────────────────────────────

def buscar_noticias(variable: str, fecha_desde: str, fecha_hasta: str,
                    max_resultados: int = 5) -> list[dict]:
    """Compatibilidad: redirige a Google News + NewsAPI."""
    resultados = _buscar_google_news(
        QUERIES.get(variable, [variable.replace("_", " ")])[0],
        max_resultados=max_resultados
    )
    if len(resultados) < 3:
        resultados.extend(_buscar_newsapi(
            QUERIES.get(variable, [variable.replace("_", " ")])[0],
            fecha_desde, fecha_hasta, max_resultados
        ))
    seen, final = set(), []
    for item in resultados:
        if item["url"] not in seen:
            seen.add(item["url"])
            final.append(item)
    return final[:max_resultados]


def buscar_noticias_quiebre(variable: str, fecha_corte: str,
                             dias_ventana: int = 14) -> list[dict]:
    """Compatibilidad: usa Google News para noticias sobre el evento."""
    return buscar_noticias_actuales(variable, dias=dias_ventana)


def noticias_a_dataframe(noticias: list[dict], quiebre_id: str,
                          variable: str) -> pd.DataFrame:
    if not noticias:
        return pd.DataFrame()
    ahora = datetime.utcnow().isoformat()
    rows = []
    for n in noticias:
        id_hash = hashlib.md5(f"{quiebre_id}_{n['url']}".encode()).hexdigest()[:16]
        rows.append({
            "id":          id_hash,
            "quiebre_id":  quiebre_id,
            "variable":    variable,
            "titulo":      (n.get("titulo", "") or "")[:500],
            "descripcion": (n.get("descripcion", "") or "")[:1000],
            "fuente":      (n.get("fuente", "") or "")[:200],
            "url":         (n.get("url", "") or "")[:500],
            "fecha_pub":   n.get("fecha_pub", None),
            "fecha_carga": ahora,
        })
    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════════════════
# QUERIES PARA MONITOR DE INDUSTRIA SIDERÚRGICA
# ════════════════════════════════════════════════════════════════════════════

GRUPOS_INDUSTRIA: dict[str, list[str]] = {
    "Urgente": [
        "precios HRC acero laminado caliente mercado",
        "aranceles acero T-MEC reglas origen México",
        "CANACERO noticias acero industria México",
        "China sobrecapacidad acero exportaciones dumping",
        "Sección 232 acero importaciones EE.UU. aranceles",
    ],
    "Tendencias": [
        "Ternium México inversión expansión producción acero",
        "acero verde descarbonización emisiones CO2 siderurgia",
        "nearshoring automotriz acero estampado México",
        "demanda construcción varilla alambrón acero México",
        "galvanizado electrodomésticos línea blanca recubrimientos",
    ],
    "Empresas": [
        "Ternium ArcelorMittal México planta acero producción",
        "AHMSA Altos Hornos México situación producción",
        "Deacero Gerdau Corsa acero México noticias",
        "Nucor Cleveland-Cliffs US Steel acero EE.UU.",
        "POSCO Nippon Steel Baosteel acero global mercado",
        "worldsteel alacero reporte acero industria",
    ],
    "Insumos": [
        "chatarra ferrosa precio EAF horno arco eléctrico",
        "mineral hierro iron ore precio tonelada",
        "carbón coquizable coking coal precio siderurgia",
        "zinc LME precio galvanizado recubrimiento acero",
        "DRI HBI hierro reducción directa precio",
    ],
    "Tecnología": [
        "green steel hidrógeno verde siderurgia descarbonización",
        "EAF horno arco eléctrico eficiencia acero tendencias",
        "IA digitalización acero metalurgia gemelos digitales",
        "DRI reducción directa acero carbono cero",
        "colada continua laminación tecnología optimización",
    ],
}

_GRUPO_COLORS: dict[str, tuple[str, str]] = {
    "Urgente":    ("#DC2626", "#FEE2E2"),
    "Tendencias": ("#059669", "#D1FAE5"),
    "Empresas":   ("#2563EB", "#DBEAFE"),
    "Insumos":    ("#D97706", "#FEF3C7"),
    "Tecnología": ("#7C3AED", "#EDE9FE"),
}


def buscar_noticias_industria(grupo: str = "Urgente", max_resultados: int = 12) -> list[dict]:
    """Noticias especializadas de la industria siderúrgica por grupo temático."""
    queries = GRUPOS_INDUSTRIA.get(grupo, GRUPOS_INDUSTRIA["Urgente"])
    todos: list[dict] = []
    for q in queries[:3]:
        res = _buscar_google_news(q, max_resultados=5)
        for r in res:
            r["grupo"] = grupo
        todos.extend(res)
    seen: set[str] = set()
    final: list[dict] = []
    for item in todos:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            final.append(item)
    final.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return final[:max_resultados]


def buscar_query_libre(query: str, max_resultados: int = 30) -> list[dict]:
    """
    Búsqueda libre por cualquier tema o fuente.
    Busca en español (MX) e inglés (US) simultáneamente,
    complementa con NewsAPI si hay pocos resultados.
    """
    todos = _buscar_google_news(query, max_resultados=max_resultados)
    if len(todos) < 10:
        hasta = datetime.utcnow().strftime("%Y-%m-%d")
        desde = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        todos.extend(_buscar_newsapi(query, desde, hasta, max_resultados=10))
    seen: set[str] = set()
    final: list[dict] = []
    for item in todos:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            final.append(item)
    final.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return final[:max_resultados]


# ════════════════════════════════════════════════════════════════════════════
# NOTICIAS NACIONALES — 5 categorías estratégicas México
# ════════════════════════════════════════════════════════════════════════════

GRUPOS_NACIONAL: dict[str, list[str]] = {
    "T-MEC y Tratados": [
        "T-MEC USMCA revisión 2026 México acuerdo bilateral negociación",
        "Trump Mexico Canada USMCA renegociación comercio",
        "Marcelo Ebrard T-MEC negociación sistémica comercio",
        "Trump insiste EU México sin T-MEC acuerdo",
        "revisión TMEC perfiles acuerdos bilaterales manufactura",
        "aranceles México EE.UU. T-MEC comercio bilateral sector",
        "Trump acero aluminio Mexico aranceles T-MEC",
        "USMCA review Mexico USA Canada trade agreement 2026",
        "acuerdos bilaterales México comercio exterior política",
        "T-MEC acero reglas origen melted poured México",
        "política comercial México EE.UU. acuerdo negociación economía",
        "USMCA Canada Mexico tariff steel trade deal",
    ],
    "Nearshoring": [
        "nearshoring México inversión empresas manufactura parques",
        "empresas chinas México planta manufactura relocalización",
        "desembarco empresas chinas México inversión manufactura",
        "relocalización manufactura México nearshoring industrial",
        "inversión extranjera directa México nearshoring sector",
        "Canada China manufactura autos relocalización rival México",
        "nearshoring automotriz acero estampado México demanda",
        "China empresas México manufactura inversión competencia",
        "nearshoring demanda acero México industrial manufactura",
        "nearshoring infraestructura parques industriales México",
        "relocation manufacturing Mexico China competition USA",
        "IED México nearshoring manufactura crecimiento inversión",
    ],
    "Sustentabilidad": [
        "economía verde residuos sustentabilidad México industria",
        "economía circular acero reciclaje metal México",
        "diagnóstico nacional residuos México gestión ambiental",
        "ESG sostenibilidad manufactura industria México",
        "reciclaje acero chatarra economía circular industria",
        "residuos industriales manejo ambiental manufactura México",
        "sustentabilidad siderurgia México ambiental responsabilidad",
        "green economy México manufacturing sustainability circular",
        "economía circular metal acero reciclado producción",
        "impulsan economía verde manejo residuos México",
    ],
    "Socios Siderúrgicos": [
        "gigantes acero San Luis Potosí siderurgia México industria",
        "gobierno siderurgia priorizar compras acero mexicano",
        "ArcelorMittal México producción planta noticias acero",
        "Grupo Acerero SIMEC acero México CANACERO socios",
        "Ternium México acero producción inversión resultados",
        "TYASA acero SBQ México expansión producción siderurgia",
        "Deacero Gerdau Corsa acero México industria socios",
        "CANACERO socios México industria acero medios noticias",
        "AHMSA Altos Hornos México siderurgia situación",
        "siderurgia México producción acero CANACERO industria",
        "Grupo SIMEC acero largo México producción socios",
        "reporteacero noticias acero siderurgia México industria",
        "Mexinox PEASA Suacero Outokumpu acero México",
        "siderúrgicas acuerdos acero mexicano compras gobierno",
    ],
    "Macroeconomía": [
        "actividad económica México contracción región IGAE 2026",
        "PIB México crecimiento industria manufactura INEGI trimestre",
        "inflación INPC México manufactura costos industria",
        "tipo cambio peso dólar exportaciones industria México",
        "Banxico tasa interés crédito manufactura empresa México",
        "economía México crecimiento industrial contracción trimestre",
        "IGAE México producción industrial mensual manufactura",
        "inversión manufactura México crecimiento INEGI industria",
        "sector industrial México desempeño economía nacional",
        "CFE electricidad tarifas industriales manufactura México",
        "gas natural precio México CENAGAS industria manufactura",
    ],
    "Logística Nacional": [
        "bloqueos carreteras México transporte carga industria",
        "accidentes autopista México tráfico logística carga",
        "obras reparación autopista México cierre carretera",
        "logística cadena suministro México manufactura distribución",
        "transporte carga México autotransporte fletes costos",
        "Ferromex KCSM ferrocarril México carga acero",
        "puertos México Manzanillo Veracruz Lázaro Cárdenas carga",
        "huelga transportistas bloqueo México carretera",
        "infraestructura carreteras México inversión SCT SICT",
        "cadena suministro disrupciones México nearshoring parques",
        "autopistas concesión México obras peaje infraestructura",
        "nearshoring logística parques industriales México norte",
        "robo mercancía transporte México carga seguridad",
        "almacenamiento distribución acero México logística industrial",
    ],
}

# ════════════════════════════════════════════════════════════════════════════
# NOTICIAS INTERNACIONALES — 5 categorías estratégicas globales
# ════════════════════════════════════════════════════════════════════════════

GRUPOS_INTERNACIONAL: dict[str, list[str]] = {
    "Precios y Commodities": [
        "HRC hot rolled coil steel price market 2026",
        "CRC cold rolled coil steel price market global",
        "rebar steel price market demand construction",
        "steel slab planchón precio mercado global",
        "scrap ferroso busheling HMS precio EAF acero",
        "iron ore mineral hierro precio tonelada Vale BHP",
        "coking coal carbón coquizable precio siderurgia",
        "natural gas price industrial EAF steel manufacturing",
        "electricity energy cost steel manufacturing global",
        "fastmarkets HRC CRC steel price report market",
        "CRU MEPS steel price monthly international report",
        "Steel Dynamics Nucor scrap price EAF USA market",
        "acero precio laminado caliente mercado mundial tendencias",
        "platts S&P Global steel price commodity market",
        "Metal Bulletin steel weekly prices commodities",
    ],
    "Geopolítica y Logística": [
        "Strait Hormuz risk shipping disruption tanker",
        "Red Sea Houthi shipping attack disruption freight",
        "Panama Canal drought transit restrictions shipping",
        "Baltic Dry Index BDI freight shipping rates global",
        "container shipping freight rates global 2026",
        "supply chain disruption steel shipping global",
        "flete contenedor marítimo precio índice Asia",
        "geopolitics trade steel shipping routes global",
        "Suez Canal disruption shipping freight rates",
        "maritime freight costs steel imports exports",
        "Estrecho Ormuz bloqueo riesgo transporte marítimo",
        "Mar Rojo Houthi conflicto envíos rutas marítimas",
        "Canal Panamá sequía tránsito restricción barcos",
    ],
    "Defensa Comercial": [
        "Section 232 steel tariffs USA imports 2026",
        "aranceles acero sección 232 Trump México EE.UU.",
        "anti-dumping steel investigation China Korea USA",
        "steel trade war tariffs protectionism global",
        "cuotas compensatorias acero México importaciones dumping",
        "USMCA rules of origin steel melted poured T-MEC",
        "steel safeguards trade protection EU USA import",
        "OCTG tubería acero importaciones aranceles dumping",
        "dumping práctica desleal acero importaciones China",
        "barreras comerciales acero proteccionismo global",
        "China steel overcapacity dumping subsidies exports",
        "acero importaciones México aranceles regulación cuotas",
        "countervailing duty steel subsidy trade remedy",
    ],
    "Descarbonización": [
        "CBAM carbon border adjustment mechanism steel Europe",
        "green steel hydrogen zero carbon production",
        "acero verde descarbonización siderurgia CO2 emisiones",
        "green hydrogen DRI steel production decarbonization",
        "CCUS carbon capture utilization storage steel plant",
        "carbon tax steel manufacturing EU legislation",
        "hidrógeno verde siderurgia reducción directa acero",
        "acero bajo carbono sustentabilidad manufactura",
        "steel decarbonization technology roadmap 2050",
        "electric arc furnace green steel scrap circular",
        "net zero steel industry emissions climate target",
        "CRU green steel hydrogen market analysis",
        "European Green Deal steel industry impact",
    ],
    "Sectores Consumidores": [
        "automotive steel demand production Mexico export",
        "producción exportación vehículos México acero automotriz",
        "construcción vivienda demanda acero México varilla",
        "housing construction steel demand rebar global",
        "infrastructure public investment steel demand Mexico",
        "electrodomésticos línea blanca manufactura acero México",
        "industrial manufacturing steel consumption demand",
        "manufactura pesada metalmecánica acero demanda México",
        "machinery equipment steel demand industrial global",
        "energy sector pipeline OCTG steel demand",
        "automotriz acero estampado laminado demanda México",
        "construcción acero demanda proyecto infraestructura México",
        "appliance white goods steel consumption demand",
    ],
}

# Paletas para los nuevos grupos
GRUPO_STYLE_NACIONAL: dict[str, tuple[str, str]] = {
    "T-MEC y Tratados":    ("#4338CA", "#E0E7FF"),
    "Nearshoring":         ("#0F766E", "#CCFBF1"),
    "Sustentabilidad":     ("#059669", "#D1FAE5"),
    "Socios Siderúrgicos": ("#DC2626", "#FEE2E2"),
    "Macroeconomía":       ("#D97706", "#FEF3C7"),
    "Logística Nacional":  ("#92400E", "#FEF3C7"),
}

GRUPO_STYLE_INTERNACIONAL: dict[str, tuple[str, str]] = {
    "Precios y Commodities":   ("#DC2626", "#FEE2E2"),
    "Geopolítica y Logística": ("#1B3A5C", "#E8EFF6"),
    "Defensa Comercial":       ("#7C3AED", "#EDE9FE"),
    "Descarbonización":        ("#059669", "#D1FAE5"),
    "Sectores Consumidores":   ("#D97706", "#FEF3C7"),
}


def buscar_noticias_sector(grupo: str, max_resultados: int = 40) -> list[dict]:
    """
    Busca noticias para cualquier grupo de GRUPOS_NACIONAL o GRUPOS_INTERNACIONAL.
    Usa todas las queries del grupo (no solo 3) y 10 resultados por query.
    Complementa con NewsAPI si hay pocos resultados.
    """
    all_groups = {**GRUPOS_NACIONAL, **GRUPOS_INTERNACIONAL, **GRUPOS_INDUSTRIA}
    queries = all_groups.get(grupo)
    if not queries:
        queries = [grupo]
    todos: list[dict] = []
    # Todas las queries del grupo, 10 resultados cada una
    for q in queries:
        res = _buscar_google_news(q, max_resultados=10)
        for r in res:
            r["grupo"] = grupo
        todos.extend(res)
    # NewsAPI como complemento si hay pocos resultados
    if len(todos) < 20:
        hasta = datetime.utcnow().strftime("%Y-%m-%d")
        desde = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        for q in queries[:3]:
            newsapi_res = _buscar_newsapi(q, desde, hasta, max_resultados=8)
            for r in newsapi_res:
                r["grupo"] = grupo
            todos.extend(newsapi_res)
    seen: set[str] = set()
    final: list[dict] = []
    for item in todos:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            final.append(item)
    final.sort(key=lambda x: x.get("fecha_pub", "") or "", reverse=True)
    return final[:max_resultados]
