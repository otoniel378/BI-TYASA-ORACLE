"""
rutas_alertas.py — Convierte noticias clasificadas (GOLD_SENTIMIENTO_NOTICIAS) en
avisos por lugar de las rutas de importación de ferroaleaciones, con las claves
del "Monitor materiales críticos" (artifact de rutas):

  paso:<clave>    pasos marítimos (PASO_NAME del monitor: suez, bab, panama...)
  pais:<iso>      país de origen, código ISO numérico de 3 dígitos ('710' = Sudáfrica)
  puerto:<clave>  puerto de llegada en México (LANDING del monitor: ver, alt, coa, man, laz)

El monitor cuelga cada aviso en todas las rutas que pasan por ese lugar, siempre
con nivel "aviso": una noticia no cambia qué ruta sale como mejor opción; subirla
a "penaliza" o "bloquea" es decisión de una persona en las reglas del monitor.

Ligar por palabras del título (no por la razón de Gemini, que menciona riesgos
genéricos). Países y puertos además exigen una palabra de logística o de
suministro: "India" o "Veracruz" solos traen notas de demanda o de seguridad.
"""

import hashlib
import re

import pandas as pd

from mercado_noticias.analytics.rupturas import tipo_impacto_noticias

DIAS_VIGENCIA = 21          # el monitor oculta avisos más viejos
MAX_POR_LUGAR = 4

PASOS = {
    "bab": ("Bab el-Mandeb (Mar Rojo)", r"bab.el.mandeb|mar rojo|red sea|hut[ií]es|houthi|yemen|golfo de ad[eé]n|gulf of aden"),
    "suez": ("Canal de Suez", r"\bsuez\b"),
    "hormuz": ("Estrecho de Ormuz", r"ormuz|hormuz|golfo p[eé]rsico|persian gulf"),
    "panama": ("Canal de Panamá", r"canal de panam|panama canal|canal interoce[aá]nico"),
    "malaca": ("Estrecho de Malaca", r"malaca|malacca|singapore strait|estrecho de singapur"),
    "gibraltar": ("Estrecho de Gibraltar", r"gibraltar"),
    "mancha": ("Canal de la Mancha", r"english channel|canal de la mancha|strait of dover|estrecho de dover"),
    "bos": ("Bósforo y Dardanelos", r"b[oó]sforo|bosp?h?orus|dardanel|black sea|mar negro"),
    "cabo": ("Cabo de Buena Esperanza", r"cape of good hope|cabo de buena esperanza"),
    "yucatan": ("Canal de Yucatán", r"canal de yucat[aá]n|yucatan channel"),
    "luzon": ("Estrecho de Luzón", r"luz[oó]n strait|estrecho de luz[oó]n"),
}
PAISES = {
    "710": ("Sudáfrica", r"sud[aá]frica|south africa|transnet|richards bay|saldanha|durban"),
    "792": ("Turquía", r"turqu[ií]a|turkey|t[uü]rkiye|iskenderun"),
    "398": ("Kazajistán", r"kazaj|kazakh"),
    "356": ("India", r"\bindia\b|\bindian\b"),
    "076": ("Brasil", r"brasil|brazil"),
    "716": ("Zimbabue", r"zimbab"),
    "246": ("Finlandia", r"finland"),
    "156": ("China", r"\bchina\b|\bchinese\b"),
    "643": ("Rusia", r"\brusia\b|\brussia"),
    "804": ("Ucrania", r"ucrania|ukrain"),
    "268": ("Georgia", r"\bgeorgia\b.*(poti|batumi|black sea|mar negro)|\bpoti\b"),
    "578": ("Noruega", r"noruega|norway"),
    "360": ("Indonesia", r"indonesia"),
    "608": ("Filipinas", r"filipinas|philippine"),
    "458": ("Malasia", r"malasia|malaysia"),
    "152": ("Chile", r"\bchile\b"),
    "604": ("Perú", r"\bper[uú]\b"),
    "124": ("Canadá", r"canad[aá]"),
    "036": ("Australia", r"australia"),
    "540": ("Nueva Caledonia", r"nueva caledonia|new caledonia"),
}
PUERTOS = {
    "ver": ("Veracruz", r"veracruz"),
    "alt": ("Altamira", r"altamira"),
    "coa": ("Coatzacoalcos", r"coatzacoalcos"),
    "man": ("Manzanillo", r"manzanillo"),
    "laz": ("Lázaro Cárdenas", r"l[aá]zaro c[aá]rdenas"),
}
# Países y puertos solo cuentan si el título habla de logística o de una
# disrupción del suministro. "export/import" solos no: traen estadísticas de
# comercio ("Kazajistán exportó X millones"), no riesgos.
PATRON_LOGISTICA = (
    r"puerto|\bport|huelga|strike|export ban|ferrocarril|\brail|naviera|shipping|flete|freight|buque|vessel|"
    r"contenedor|container|aduana|customs|sanci[oó]n|sanction|arancel|tariff|\bban\b|prohib|\bminas?\b|"
    r"\bmines?\b|smelter|fundici|electricidad|electricity|apag[oó]n|blackout|power cut|load.?shedding|inundaci|"
    r"flood|cicl[oó]n|cyclone|hurac[aá]n|hurricane|sismo|terremoto|earthquake|guerra|\bwar\b|conflict|bloqueo|"
    r"blockade|congesti|cierre|closure|cuota|quota|output cut|recorte de producci|carga|cargo|transporte|"
    r"transport|log[ií]stic"
)
PATRON_GRAVE = (
    r"cierre|cerrad|closed|closure|ataque|attack|huelga|strike|bloqueo|blockade|suspend|halt|paraliz|explosi|"
    r"sanci[oó]n|sanction|\bban\b|prohib|guerra|\bwar\b|hurac[aá]n|hurricane|cicl[oó]n|cyclone|sismo|terremoto|"
    r"earthquake|inundaci|flood|incendio|wildfire|desv[ií]|divert|reroute|cancel|derrumbe|collapse"
)


def _lugares(titulo: str) -> list[tuple[str, str]]:
    """[(nodo, nombre)] del título; países y puertos solo con palabra de logística."""
    t = titulo.lower()
    out = [(f"paso:{k}", n) for k, (n, p) in PASOS.items() if re.search(p, t)]
    if re.search(PATRON_LOGISTICA, t):
        out += [(f"pais:{k}", n) for k, (n, p) in PAISES.items() if re.search(p, t)]
        out += [(f"puerto:{k}", n) for k, (n, p) in PUERTOS.items() if re.search(p, t)]
    return out


def alertas_rutas(noticias: pd.DataFrame, hoy=None, dias: int = DIAS_VIGENCIA,
                  max_por_lugar: int = MAX_POR_LUGAR) -> pd.DataFrame:
    """noticias: salida de load_noticias_periodo (fecha_pub, titulo, fuente, url,
    variable_principal, grupo_tematico, razon). Una fila por (noticia, lugar)
    publicada en los últimos <dias>, las graves primero, a lo más <max_por_lugar>
    por lugar. Columnas: id, nodo, lugar, titulo, url, fuente, fecha, severidad,
    tipo_impacto, razon."""
    cols = ["id", "nodo", "lugar", "titulo", "url", "fuente", "fecha", "severidad", "tipo_impacto", "razon"]
    if noticias.empty:
        return pd.DataFrame(columns=cols)
    hoy = pd.Timestamp(hoy or pd.Timestamp.now()).normalize()
    n = noticias[noticias["fecha_pub"] >= hoy - pd.Timedelta(days=dias)]
    n = tipo_impacto_noticias(n) if not n.empty else n.assign(tipo_impacto=None)
    filas = []
    for r in n.itertuples():
        # Google News agrega " - Medio" al final: se quita antes de buscar lugares
        # (si no, "The New Voice of Ukraine" liga la nota a Ucrania)
        titulo = re.sub(r"\s+-\s+[^-]{2,60}$", "", str(r.titulo or ""))
        for nodo, lugar in _lugares(titulo):
            filas.append({
                "id": hashlib.sha1(f"{nodo}|{r.url}".encode()).hexdigest()[:20],
                "nodo": nodo, "lugar": lugar,
                "titulo": titulo[:300],
                "url": r.url, "fuente": r.fuente or "",
                "fecha": pd.Timestamp(r.fecha_pub).strftime("%Y-%m-%d"),
                "severidad": "alta" if re.search(PATRON_GRAVE, titulo.lower()) else "media",
                "tipo_impacto": r.tipo_impacto or "Logística",
                "razon": (r.razon or "")[:400],
            })
    if not filas:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(filas)
    out = out.drop_duplicates(subset=["nodo", "titulo"])
    out["_orden"] = out["severidad"].map({"alta": 0, "media": 1})
    out = (out.sort_values(["nodo", "_orden", "fecha"], ascending=[True, True, False])
           .groupby("nodo").head(max_por_lugar))
    return out[cols].reset_index(drop=True)
