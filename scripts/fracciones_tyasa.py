"""
scripts/fracciones_tyasa.py — Catálogo de fracciones arancelarias (TIGIE) que
le competen a TYASA, según la Dirección General de Facilitación Comercial y
de Comercio Exterior. Capturado a mano por el usuario el 2026-08-24; no viene
de un catálogo oficial parseado (a diferencia de tigie_partidas.py).

Se usa como filtro común para relacionar fuentes de comercio exterior que
comparten FRACCION_ARANCELARIA como llave (CANACERO SICEP, SNICE avisos
automáticos — ver mercado/snice/loaders.py y setup_snice_tables_oracle.py).

FRACCIONES_TYASA: fracciones completas de 8 dígitos (formato "XXXXXXXX", sin
puntos). Match exacto contra los primeros 8 dígitos de FRACCION_ARANCELARIA
(CANACERO reporta a nivel NICO/10 dígitos; SNICE a nivel de fracción de 8).

FRACCIONES_TYASA_PREFIJO: fracciones dadas solo a nivel subpartida (6 dígitos)
porque cubren TODAS las fracciones de 8 dígitos bajo esa subpartida (confirmado
con el usuario 2026-08-24). Match por prefijo (STARTSWITH / LIKE 'XXXXXX%').
"""

FRACCIONES_TYASA = {
    "72071291",
    "72071999",  # capturado como "2707.19.99"; corregido con el usuario a capítulo 72
    "72072002",
    "72081003",
    "72082701",
    "72083901",
    "72084002",
    "72089099",
    "72091601",
    "72091701",
    "72091801",
    "72092701",
    "72092601",
    "72092801",
    "72099099",
    "72104101",
    "72104199",
    "72104999",
    "72107002",
    "72109099",
    "72112999",
    "72119099",
    "72123003",
    "72124004",
    "72125001",
    "72139103",
    "72139999",
    "72141001",
    "72142001",
    "72142099",
    "72143091",
    "72149103",
    "72149999",
    "72151001",
    "72155091",
    "72159099",
    "72171002",
    "72172002",
    "72179099",
    "72241006",
    "72249099",
    "72279099",
    "72281002",
    "72283001",
    "72283099",
    "72284091",
    "72285091",
    "72286091",
    "72299099",
    "73012001",
    "73130001",
    "73141201",
    "73141903",
    "73141999",
    "73144101",
    "73144201",
    "73144999",
    "73170001",
    "73170002",
    "73170099",
    "73261103",
}

FRACCIONES_TYASA_PREFIJO = {
    "720854",  # 7208.54 — cubre todas las fracciones de 8 dígitos bajo esta subpartida
    "720916",  # 7209.16 — ídem (además hay una fracción específica 72091601 en FRACCIONES_TYASA)
    "732619",  # 7326.19 — ídem
}

# RAZON_SOCIAL con la que TYASA aparece como empresa importadora en los avisos
# SNICE/CANACERO (confirmado con el usuario 2026-09-28). Sirve para aislar,
# dentro del ranking de empresas que importan las fracciones de TYASA, cuál de
# esas filas es la propia TYASA (vs. la competencia/otros importadores).
RAZON_SOCIAL_TYASA_SNICE = "T A 2000 SA DE CV"


def es_fraccion_tyasa(fraccion_arancelaria: str) -> bool:
    """
    True si una FRACCION_ARANCELARIA (de CANACERO/SNICE, con o sin NICO,
    con o sin puntos) corresponde a un producto de TYASA.
    """
    codigo = fraccion_arancelaria.replace(".", "").strip()
    if codigo[:8] in FRACCIONES_TYASA:
        return True
    return any(codigo.startswith(prefijo) for prefijo in FRACCIONES_TYASA_PREFIJO)


# ── División de TYASA por fracción (Aceros Planos | Largos | SBQ) ───────────
#
# Capturado del catálogo interno de TYASA (columna ESTATUS), confirmado por el
# usuario el 2026-11-24. El capítulo arancelario NO basta para inferir la
# división: 7214/7215 (barras sin alear) y 7228 (barras/perfiles de acero
# aleado) tienen fracciones que SÍ pasa por el molino SBQ ("TYASA MOLINO SBQ")
# y otras que son de TYASA pero de otra división ("TYASA" a secas) — por
# ejemplo 72283001 es SBQ pero 72285091 (mismo capítulo 7228) NO lo es.
#
# Las "obsoletas" ya no están vigentes en la TIGIE actual (no van a aparecer en
# datos de importación nuevos) pero se dejan para reconocerlas en noticias o
# decretos viejos que las mencionen.
FRACCIONES_SBQ_CONFIRMADAS = {
    "72141001", "72142099", "72149103", "72149999", "72151001",
    "72281002", "72283001", "72283099", "72284091",
    "72284002",  # obsoleta
}

# Mismo catálogo, status "TYASA" (sin "MOLINO SBQ"): comparten capítulo con
# fracciones SBQ pero NO se procesan en el molino especial — por descarte,
# caen en Aceros Largos (barras/perfiles, no planos).
FRACCIONES_CONFIRMADAS_NO_SBQ = {
    "72155091", "72159099", "72285091", "72286091",
    "72155002", "72285002",  # obsoletas
}

# Capítulos TIGIE por convención de industria, para el resto de FRACCIONES_TYASA
# que no está en ninguna de las dos listas confirmadas arriba (72.08-12 planos,
# 72.13-17/73.01/73.13/73.14/73.17 largos, 72.24-29 acero aleado). Esta parte
# NO está confirmada fracción por fracción como la de arriba — es una inferencia
# razonable, no un hecho verificado con el catálogo interno.
_CAPITULO_A_LINEA = {
    "7208": "Aceros Planos", "7209": "Aceros Planos", "7210": "Aceros Planos",
    "7211": "Aceros Planos", "7212": "Aceros Planos",
    "7213": "Aceros Largos", "7214": "Aceros Largos", "7215": "Aceros Largos",
    "7216": "Aceros Largos", "7217": "Aceros Largos", "7301": "Aceros Largos",
    "7313": "Aceros Largos", "7314": "Aceros Largos", "7317": "Aceros Largos",
    "7224": "Aceros SBQ", "7225": "Aceros SBQ", "7226": "Aceros SBQ",
    "7227": "Aceros SBQ", "7228": "Aceros SBQ", "7229": "Aceros SBQ",
}


def linea_tyasa(fraccion_arancelaria: str) -> str:
    """
    División de TYASA (Aceros Planos | Aceros Largos | Aceros SBQ) para una
    fracción arancelaria. Usa primero el catálogo confirmado a mano arriba;
    si la fracción no está ahí, cae al capítulo TIGIE (menos confiable, ver
    comentario de _CAPITULO_A_LINEA). Retorna "" si no se reconoce nada.
    """
    codigo = fraccion_arancelaria.replace(".", "").strip()[:8]
    if codigo in FRACCIONES_SBQ_CONFIRMADAS:
        return "Aceros SBQ"
    if codigo in FRACCIONES_CONFIRMADAS_NO_SBQ:
        return "Aceros Largos"
    capitulo = codigo[:4]
    if capitulo in ("7207",):
        return "Semiterminados (insumo)"
    if capitulo == "7326":
        return "Derivados (ej. bolas de molienda)"
    return _CAPITULO_A_LINEA.get(capitulo, "")
