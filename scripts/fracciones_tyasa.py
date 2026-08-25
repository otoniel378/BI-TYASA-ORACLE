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


def es_fraccion_tyasa(fraccion_arancelaria: str) -> bool:
    """
    True si una FRACCION_ARANCELARIA (de CANACERO/SNICE, con o sin NICO,
    con o sin puntos) corresponde a un producto de TYASA.
    """
    codigo = fraccion_arancelaria.replace(".", "").strip()
    if codigo[:8] in FRACCIONES_TYASA:
        return True
    return any(codigo.startswith(prefijo) for prefijo in FRACCIONES_TYASA_PREFIJO)
