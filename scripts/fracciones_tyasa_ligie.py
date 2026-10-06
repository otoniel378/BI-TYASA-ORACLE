"""
scripts/fracciones_tyasa_ligie.py — Nombres oficiales (LIGIE) de las fracciones y
subpartidas arancelarias que le importan a TYASA (ver fracciones_tyasa.py para el
conjunto de códigos en sí, capturado a mano por el usuario el 2026-08-24).

Fuente: texto extraído directamente de
https://www.snice.gob.mx/~oracle/SNICE_DOCS/LIGIE-UNIFICADA-LIGIE_20250728-20250728.pdf
(páginas ~752-821, capítulos 72 y 73), verificado línea por línea el 2026-09-23
contra la segunda captura a mano del usuario (Downloads/CÓDIGO ARANCELES.docx).

FRACCIONES_TYASA_DESCRIPCION: descripción oficial (texto legal, tal cual el PDF)
para cada fracción de 8 dígitos en FRACCIONES_TYASA. Es la descripción "hoja" de
esa fracción específica, no un resumen; para el nombre completo de un producto
hay que leerla junto con la partida (tigie_partidas.PARTIDAS[fraccion[:4]]) y, si
aplica, la subpartida de 6 dígitos — igual que en el propio catálogo LIGIE, que es
jerárquico (partida > subpartida > fracción > NICO).

SUBPARTIDAS_TYASA_DESCRIPCION: mismo criterio para las 3 claves de
FRACCIONES_TYASA_PREFIJO (subpartidas de 6 dígitos que cubren TODAS sus fracciones
de 8 dígitos).

Dos correcciones encontradas al verificar contra el PDF (el Word del usuario, que
viene de una segunda captura a mano, tenía errores de dedo en estas dos):
  - 72081003: decía "simplemente en laminados caliente"; el PDF dice "simplemente
    laminados en caliente" (orden de palabras).
  - 72143091: decía "Los demás, de acero de fácil mecanización"; el PDF dice
    "Las demás..." (concordancia de género — se refiere a "barras").
Dos fracciones que estaban en el Word a medio capturar pero SÍ están en
FRACCIONES_TYASA y se confirmaron completas contra el PDF: 72084002 y 72104101.
"""

FRACCIONES_TYASA_DESCRIPCION = {
    "72071291": "Los demás, de sección transversal rectangular.",
    "72071999": "Los demás.",
    "72072002": "Con un contenido de carbono superior o igual al 0.25% en peso.",
    "72081003": "Enrollados, simplemente laminados en caliente, con motivos en relieve.",
    "72082701": "De espesor inferior a 3 mm.",
    "72083901": "De espesor inferior a 3 mm.",
    "72084002": "Sin enrollar, simplemente laminados en caliente, con motivos en relieve.",
    "72089099": "Los demás.",
    "72091601": "De espesor superior a 1 mm pero inferior a 3 mm.",
    "72091701": "De espesor superior o igual a 0.5 mm pero inferior o igual a 1 mm.",
    "72091801": "De espesor inferior a 0.5 mm.",
    "72092701": "De espesor superior o igual a 0.5 mm pero inferior o igual a 1 mm.",
    "72092601": "De espesor superior a 1 mm pero inferior a 3 mm.",
    "72092801": "De espesor inferior a 0.5 mm.",
    "72099099": "Los demás.",
    "72104101": "Láminas cincadas por las dos caras.",
    "72104199": "Los demás.",
    "72104999": "Los demás.",
    "72107002": "Pintados, barnizados o revestidos de plástico.",
    "72109099": "Los demás.",
    "72112999": "Los demás.",
    "72119099": "Los demás.",
    "72123003": "Cincados de otro modo.",
    "72124004": "Pintados, barnizados o revestidos de plástico.",
    "72125001": "Revestidos de otro modo.",
    "72139103": "De sección circular con diámetro inferior a 14 mm.",
    "72139999": "Los demás.",
    "72141001": "Forjadas.",
    "72142001": "Varillas corrugadas o barras para armadura, para cemento u hormigón.",
    "72142099": "Los demás.",
    "72143091": "Las demás, de acero de fácil mecanización.",
    "72149103": "De sección transversal rectangular.",
    "72149999": "Las demás.",
    "72151001": "De acero de fácil mecanización, simplemente obtenidas o acabadas en frío.",
    "72155091": "Las demás, simplemente obtenidas o acabadas en frío.",
    "72159099": "Las demás.",
    "72171002": "Sin revestir, incluso pulido.",
    "72172002": "Cincado.",
    "72179099": "Los demás.",
    "72241006": "Lingotes o demás formas primarias.",
    "72249099": "Los demás.",
    "72279099": "Los demás.",
    "72281002": "Barras de acero rápido.",
    "72283001": "En aceros grado herramienta.",
    "72283099": "Las demás.",
    "72284091": "Las demás barras, simplemente forjadas.",
    "72285091": "Las demás barras, simplemente obtenidas o acabadas en frío.",
    "72286091": "Las demás barras.",
    "72299099": "Los demás.",
    "73012001": "Perfiles.",
    "73130001": (
        "Alambre de púas, de hierro o acero; alambre (simple o doble) y fleje, "
        "torcidos, incluso con púas, de hierro o acero, de los tipos utilizados "
        "para cercar."
    ),
    "73141201": "Telas metálicas continuas o sin fin, de acero inoxidable, para máquinas.",
    "73141903": "Cincadas.",
    "73141999": "Los demás.",
    "73144101": "Cincadas.",
    "73144201": "Revestidas de plástico.",
    "73144999": "Las demás.",
    "73170001": "Clavos para herrar.",
    "73170002": "Púas o dientes para cardar.",
    "73170099": "Los demás.",
    "73261103": "Bolas y artículos similares para molinos.",
}

SUBPARTIDAS_TYASA_DESCRIPCION = {
    "720854": "De espesor inferior a 3 mm.",
    "720916": "De espesor superior a 1 mm pero inferior a 3 mm.",
    "732619": "Las demás.",
}


def descripcion_oficial(fraccion_arancelaria: str) -> str | None:
    """Descripción legal (hoja del catálogo LIGIE) para una fracción de 8 dígitos
    o subpartida de 6 dígitos de TYASA. None si no está en el catálogo."""
    codigo = fraccion_arancelaria.replace(".", "").strip()
    if codigo[:8] in FRACCIONES_TYASA_DESCRIPCION:
        return FRACCIONES_TYASA_DESCRIPCION[codigo[:8]]
    if codigo[:6] in SUBPARTIDAS_TYASA_DESCRIPCION:
        return SUBPARTIDAS_TYASA_DESCRIPCION[codigo[:6]]
    return None
