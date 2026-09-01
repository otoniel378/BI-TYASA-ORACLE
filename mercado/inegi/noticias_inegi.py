"""
noticias_inegi.py — Búsqueda de noticias contextuales por indicador INEGI.

Reutiliza el motor de búsqueda de mercado_noticias (Google News RSS + NewsAPI)
armando una query por indicador: contexto de grupo + especificidad de la clave.
"""

from mercado_noticias.analytics.noticias import buscar_query_libre

# ── Query base por grupo — tema económico que enmarca a todos sus indicadores ──
QUERY_GRUPO: dict[str, str] = {
    "IMAI":        "actividad industrial México manufactura producción INEGI",
    "EMIM":        "manufactura México volumen físico producción industrial",
    "ENEC":        "construcción México valor producción ENEC INEGI obra",
    "ENEC_PESOS":  "construcción México valor producción ENEC INEGI obra",
    "EMEC":        "comercio mayoreo menudeo México ventas INEGI",
    "IGAE":        "actividad económica México IGAE INEGI PIB mensual",
    "Balanza":     "comercio exterior acero México importaciones exportaciones siderurgia",
    "INPP":        "precios productor México INPP inflación industrial",
    "INPC":        "inflación México INPC precios consumidor Banxico",
    "IFB":         "inversión fija bruta México maquinaria equipo construcción",
    "EMOE":        "confianza empresarial México expectativas industria consumidor",
    "ENEC_ANUAL":  "construcción México sector 23 edificación obras ingeniería civil",
}

# ── Refinamiento específico por clave — se combina con la query de grupo ──────
QUERY_CLAVE: dict[str, str] = {
    "736476": "hierro acero producción industrial México",
    "736475": "metálicas básicas industria México acero",
    "736414": "construcción actividad industrial México",
    "720340": "transporte urbanización obra pública carreteras México",
    "720342": "petróleo petroquímica Pemex refinería Dos Bocas construcción",
    "720334": "edificación vivienda construcción México",
    "720336": "agua riego saneamiento obra pública México",
    "720338": "electricidad telecomunicaciones centros de datos construcción México",
    "722092": "transporte urbanización obra pública carreteras México",
    "722099": "petróleo petroquímica Pemex refinería Dos Bocas construcción",
    "722078": "edificación vivienda construcción México",
    "722084": "agua riego saneamiento obra pública México",
    "722088": "electricidad telecomunicaciones centros de datos construcción México",
    "133094": "importaciones acero México dumping arancel",
    "133031": "exportaciones acero México siderurgia",
    "910503": "precios productor manufactura México",
    "910502": "precios productor construcción México costos",
    "910501": "precios productor energía México",
    "910500": "precios productor minería México",
    "910499": "precios productor minería petróleo México",
    "701407": "confianza empresarial construcción México",
    "701401": "confianza empresarial México industria",
    "334497": "confianza consumidor México",
    "741030": "importación maquinaria equipo México inversión",
    "741034": "inversión construcción México",
    "796426": "sector construcción México anual INEGI EAEC",
    "796427": "edificación México construcción anual",
    "796428": "obras ingeniería civil México construcción",
    "796429": "trabajos especializados construcción México",
    "5300000027": "remuneraciones sector construcción México empleo",
}


def query_para_indicador(clave: str, grupo: str) -> str:
    """Arma la query de búsqueda combinando la especificidad de la clave con el contexto del grupo."""
    base = QUERY_GRUPO.get(grupo, "economía México INEGI indicador")
    extra = QUERY_CLAVE.get(clave, "")
    return f"{extra} {base}".strip() if extra else base


def buscar_noticias_indicador(clave: str, grupo: str, max_resultados: int = 12) -> list[dict]:
    """Noticias recientes relacionadas con un indicador INEGI específico."""
    query = query_para_indicador(clave, grupo)
    return buscar_query_libre(query, max_resultados=max_resultados)
