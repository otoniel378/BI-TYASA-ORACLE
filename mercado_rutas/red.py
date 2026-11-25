"""
mercado_rutas/red.py — La red: planta, puertos de llegada, pasos marítimos,
orígenes y corredores. Sin datos externos; todo es configuración.

Claves iguales al "Monitor materiales críticos" (artifact de rutas) y a
mercado_noticias/analytics/rutas_alertas.py, para que las noticias se liguen
solas: paso:<clave>, pais:<ISO numérico de 3 dígitos>, puerto:<clave>.

Las rutas se arman como  origen → salida (corredor hasta un "acceso") → llegada
(del acceso al puerto mexicano) → camión a la planta. Los accesos son tres:
  atl  Atlántico, entrada este del Caribe
  pac  Pacífico mexicano, frente a Manzanillo
  gol  Golfo de México (origen ya dentro del Golfo: EE. UU., Canadá por Florida)
Así cada país tiene varias rutas (todas las combinaciones salida × puerto) y un
escenario que cierra un paso deja solo las que no lo cruzan, como en el monitor.

IMPORTANTE: los orígenes por material son los principales productores
(referencia), no los proveedores reales de TYASA. Distancias y días son estimados.
"""

TYASA = {"nombre": "TYASA", "lugar": "Ixtaczoquitlán, Ver.", "lat": 18.857, "lon": -97.060}

# Puertos mexicanos de llegada. km = carretera aproximada a la planta.
# portwatch = nombre en IMF PortWatch.
PUERTOS = {
    "ver": {"nombre": "Veracruz", "lat": 19.20, "lon": -96.13, "km": 140, "costa": "Golfo", "portwatch": "Veracruz"},
    "coa": {"nombre": "Coatzacoalcos", "lat": 18.15, "lon": -94.42, "km": 330, "costa": "Golfo",
            "portwatch": "Coatzacoalcos"},
    "alt": {"nombre": "Altamira", "lat": 22.48, "lon": -97.86, "km": 560, "costa": "Golfo", "portwatch": "Altamira"},
    "laz": {"nombre": "Lázaro Cárdenas", "lat": 17.94, "lon": -102.18, "km": 830, "costa": "Pacífico",
            "portwatch": "Lazaro Cardenas"},
    "man": {"nombre": "Manzanillo", "lat": 19.06, "lon": -104.32, "km": 950, "costa": "Pacífico",
            "portwatch": "Manzanillo"},
}

# Pasos marítimos que monitorea el sistema (todos los del monitor de rutas)
PASOS = {
    "panama": {"nombre": "Canal de Panamá", "corto": "Panamá", "lat": 9.12, "lon": -79.77, "portwatch": "Panama Canal"},
    "yucatan": {"nombre": "Canal de Yucatán", "corto": "Yucatán", "lat": 21.82, "lon": -85.65,
                "portwatch": "Yucatan Channel"},
    "bab": {"nombre": "Bab el-Mandeb (Mar Rojo)", "corto": "Bab el-Mandeb", "lat": 12.79, "lon": 43.35,
            "portwatch": "Bab el-Mandeb Strait"},
    "suez": {"nombre": "Canal de Suez", "corto": "Suez", "lat": 30.59, "lon": 32.44, "portwatch": "Suez Canal"},
    "hormuz": {"nombre": "Estrecho de Ormuz", "corto": "Ormuz", "lat": 26.4, "lon": 56.5, "portwatch": "Strait of Hormuz"},
    "malaca": {"nombre": "Estrecho de Malaca", "corto": "Malaca", "lat": 2.5, "lon": 101.2, "portwatch": "Malacca Strait"},
    "gibraltar": {"nombre": "Estrecho de Gibraltar", "corto": "Gibraltar", "lat": 35.94, "lon": -5.75,
                  "portwatch": "Gibraltar Strait"},
    "mancha": {"nombre": "Canal de la Mancha", "corto": "La Mancha", "lat": 51.03, "lon": 1.51, "portwatch": "Dover Strait"},
    "bos": {"nombre": "Bósforo y Dardanelos", "corto": "Bósforo", "lat": 41.17, "lon": 29.09, "portwatch": "Bosporus Strait"},
    "cabo": {"nombre": "Cabo de Buena Esperanza", "corto": "Cabo", "lat": -35.0, "lon": 19.5,
             "portwatch": "Cape of Good Hope"},
    "luzon": {"nombre": "Estrecho de Luzón", "corto": "Luzón", "lat": 20.5, "lon": 121.0, "portwatch": "Luzon Strait"},
}

# Accesos a México y tramo final de cada acceso a cada puerto. Un str en la
# lista es un paso marítimo (se toma su coordenada y se cuenta como cruce).
ACCESOS = {"atl": (16.0, -62.0), "pac": (16.0, -106.0), "gol": (25.5, -93.0)}
_GOLFO = (23.5, -91.5)
_A_PACIFICO_DESDE_CARIBE = [(12.0, -77.5), "panama", (8.0, -84.0), (13.0, -97.0)]
_A_GOLFO_DESDE_PACIFICO = [(9.0, -86.0), "panama", (12.5, -78.5), (18.0, -82.5), "yucatan", _GOLFO]
LLEGADAS = {
    ("atl", "Golfo"): [(18.0, -75.0), "yucatan", _GOLFO],
    ("atl", "Pacífico"): _A_PACIFICO_DESDE_CARIBE,
    ("gol", "Golfo"): [],
    ("gol", "Pacífico"): ["yucatan", (18.0, -82.5)] + _A_PACIFICO_DESDE_CARIBE,
    ("pac", "Pacífico"): [],
    ("pac", "Golfo"): _A_GOLFO_DESDE_PACIFICO,
}

# Corredores de salida: del puerto de carga a un acceso
_ATL_N = [(48.0, -10.0), (35.0, -40.0)]
_MED_A_ATL = [(36.5, 12.0), "gibraltar", (32.0, -30.0)]
_CABO_A_ATL = ["cabo", (-15.0, -5.0), (5.0, -35.0)]
_INDICO_A_SUEZ = [(12.5, 52.0), "bab", (20.0, 38.5), "suez", (33.5, 28.0)]
SALIDAS = {
    "sudafrica_cabo": {"nombre": "por el Atlántico", "acceso": "atl", "puntos": [(-36.0, 25.0)] + _CABO_A_ATL},
    "atl_sur": {"nombre": "por el Atlántico", "acceso": "atl", "puntos": [(-15.0, -34.0), (0.0, -42.0)]},
    "europa_norte": {"nombre": "por el Atlántico Norte", "acceso": "atl", "puntos": _ATL_N},
    "europa_mancha": {"nombre": "por La Mancha", "acceso": "atl", "puntos": [(53.5, 3.0), "mancha"] + _ATL_N},
    "baltico": {"nombre": "por el Báltico y La Mancha", "acceso": "atl",
                "puntos": [(59.6, 22.0), (55.8, 15.5), (57.5, 8.0), "mancha"] + _ATL_N},
    "mediterraneo": {"nombre": "por Gibraltar", "acceso": "atl", "puntos": [(34.5, 28.0)] + _MED_A_ATL},
    "mar_negro": {"nombre": "por el Bósforo y Gibraltar", "acceso": "atl",
                  "puntos": [(43.0, 34.0), "bos", (37.0, 25.0)] + _MED_A_ATL},
    "india_cabo": {"nombre": "por el Cabo", "acceso": "atl",
                   "puntos": [(5.5, 80.5), (-10.0, 70.0), (-30.0, 40.0)] + _CABO_A_ATL},
    "india_suez": {"nombre": "por Suez", "acceso": "atl", "puntos": [(5.5, 80.5)] + _INDICO_A_SUEZ + _MED_A_ATL},
    "india_pacifico": {"nombre": "por Malaca y el Pacífico", "acceso": "pac",
                       "puntos": [(5.5, 88.0), "malaca", (1.3, 104.0), (12.0, 113.0), "luzon", (30.0, 150.0),
                                  (38.0, -170.0), (25.0, -125.0)]},
    "asia_pacifico": {"nombre": "por el Pacífico", "acceso": "pac",
                      "puntos": [(31.0, 128.0), (32.0, 150.0), (38.0, -170.0), (25.0, -125.0)]},
    "asia_cabo": {"nombre": "por Malaca y el Cabo", "acceso": "atl",
                  "puntos": [(22.0, 115.0), (12.0, 110.0), (1.3, 104.0), "malaca", (-5.0, 90.0), (-30.0, 40.0)]
                  + _CABO_A_ATL},
    "asia_suez": {"nombre": "por Malaca y Suez", "acceso": "atl",
                  "puntos": [(22.0, 115.0), (12.0, 110.0), (1.3, 104.0), "malaca", (5.5, 80.5)] + _INDICO_A_SUEZ
                  + _MED_A_ATL},
    "sudeste_asia": {"nombre": "por el Pacífico", "acceso": "pac",
                     "puntos": [(5.0, 128.0), (20.0, 150.0), (30.0, -170.0), (25.0, -125.0)]},
    "oceania": {"nombre": "por el Pacífico", "acceso": "pac",
                "puntos": [(-10.0, -170.0), (5.0, -130.0)]},
    "australia": {"nombre": "por el Pacífico Sur", "acceso": "pac",
                  "puntos": [(-38.0, 125.0), (-42.0, 150.0), (-30.0, 180.0), (-10.0, -140.0), (8.0, -115.0)]},
    "sudamerica_pacifico": {"nombre": "por el Pacífico", "acceso": "pac", "puntos": [(-5.0, -85.0), (8.0, -98.0)]},
    "eeuu_golfo": {"nombre": "por el Golfo", "acceso": "gol", "puntos": [(27.0, -94.5)]},
    "canada_atl": {"nombre": "por el Atlántico y Florida", "acceso": "gol",
                   "puntos": [(45.0, -60.0), (35.0, -72.0), (24.4, -81.5), (24.0, -86.0)]},
}

# País -> puerto de carga de referencia y salidas posibles. Clave = ISO numérico.
PAISES = {
    "484": {"nombre": "México", "puerto": "Planta nacional", "lat": 22.20, "lon": -97.90, "salidas": [],
            "km_terrestre": 450},
    "840": {"nombre": "Estados Unidos", "puerto": "Houston", "lat": 29.73, "lon": -95.27, "salidas": ["eeuu_golfo"]},
    "124": {"nombre": "Canadá", "puerto": "Montreal", "lat": 45.50, "lon": -73.55, "salidas": ["canada_atl"]},
    "156": {"nombre": "China", "puerto": "Shanghái", "lat": 31.23, "lon": 121.80,
            "salidas": ["asia_pacifico", "asia_cabo", "asia_suez"]},
    "360": {"nombre": "Indonesia", "puerto": "Morowali", "lat": -2.80, "lon": 122.10,
            "salidas": ["sudeste_asia", "asia_cabo"]},
    "608": {"nombre": "Filipinas", "puerto": "Surigao", "lat": 9.80, "lon": 125.50, "salidas": ["sudeste_asia"]},
    "458": {"nombre": "Malasia", "puerto": "Bintulu", "lat": 3.26, "lon": 113.07,
            "salidas": ["sudeste_asia", "asia_cabo", "asia_suez"]},
    "356": {"nombre": "India", "puerto": "Visakhapatnam", "lat": 17.69, "lon": 83.29,
            "salidas": ["india_pacifico", "india_cabo", "india_suez"]},
    "710": {"nombre": "Sudáfrica", "puerto": "Richards Bay", "lat": -28.80, "lon": 32.08, "salidas": ["sudafrica_cabo"]},
    "716": {"nombre": "Zimbabue", "puerto": "vía Beira / Durban", "lat": -29.87, "lon": 31.05,
            "salidas": ["sudafrica_cabo"]},
    "643": {"nombre": "Rusia", "puerto": "San Petersburgo", "lat": 59.90, "lon": 30.20, "salidas": ["baltico"]},
    "398": {"nombre": "Kazajistán", "puerto": "vía Poti / San Petersburgo", "lat": 42.15, "lon": 41.67,
            "salidas": ["mar_negro", "baltico"]},
    "268": {"nombre": "Georgia", "puerto": "Poti", "lat": 42.15, "lon": 41.67, "salidas": ["mar_negro"]},
    "804": {"nombre": "Ucrania", "puerto": "Odesa", "lat": 46.48, "lon": 30.73, "salidas": ["mar_negro"]},
    "792": {"nombre": "Turquía", "puerto": "Iskenderun", "lat": 36.60, "lon": 36.10, "salidas": ["mediterraneo"]},
    "246": {"nombre": "Finlandia", "puerto": "Tornio", "lat": 65.85, "lon": 24.15, "salidas": ["baltico"]},
    "578": {"nombre": "Noruega", "puerto": "Kristiansand", "lat": 58.10, "lon": 8.00, "salidas": ["europa_norte"]},
    "826": {"nombre": "Reino Unido", "puerto": "Liverpool", "lat": 53.40, "lon": -3.00, "salidas": ["europa_norte"]},
    "250": {"nombre": "Francia", "puerto": "Dunkerque", "lat": 51.05, "lon": 2.37, "salidas": ["europa_mancha"]},
    "724": {"nombre": "España", "puerto": "Bilbao", "lat": 43.35, "lon": -3.05, "salidas": ["europa_norte"]},
    "076": {"nombre": "Brasil", "puerto": "Santos", "lat": -23.96, "lon": -46.33, "salidas": ["atl_sur"]},
    "152": {"nombre": "Chile", "puerto": "San Antonio", "lat": -33.59, "lon": -71.60, "salidas": ["sudamerica_pacifico"]},
    "604": {"nombre": "Perú", "puerto": "Callao", "lat": -12.05, "lon": -77.15, "salidas": ["sudamerica_pacifico"]},
    "540": {"nombre": "Nueva Caledonia", "puerto": "Nouméa", "lat": -22.27, "lon": 166.44, "salidas": ["oceania"]},
    "036": {"nombre": "Australia", "puerto": "Port Hedland", "lat": -20.30, "lon": 118.60, "salidas": ["australia"]},
}

# Material -> países productores de referencia (por confirmar con Compras)
MATERIALES = {
    "FeMn": ("Ferromanganeso", ["484", "710", "356", "156"]),
    "SiMn": ("Silicomanganeso", ["484", "268", "710", "356", "458"]),
    "FeSi": ("Ferrosilicio", ["156", "643", "076", "578", "458", "398"]),
    "FeCr": ("Ferrocromo", ["710", "792", "398", "356", "076", "716", "246"]),
    "FeV": ("Ferrovanadio", ["156", "643", "710", "076"]),
    "FeMo": ("Ferromolibdeno", ["152", "156", "840", "604", "484"]),
    "FeTi": ("Ferrotitanio", ["840", "826", "643", "156"]),
    "FeNb": ("Ferroniobio", ["076", "124"]),
    "Ni": ("Níquel", ["360", "608", "643", "540", "124", "036"]),
}

# Código ISO de 3 letras (lo usa el mapa para sombrear países)
ISO3 = {
    "484": "MEX", "840": "USA", "124": "CAN", "156": "CHN", "360": "IDN", "608": "PHL", "458": "MYS", "356": "IND",
    "710": "ZAF", "716": "ZWE", "643": "RUS", "398": "KAZ", "268": "GEO", "804": "UKR", "792": "TUR", "246": "FIN",
    "578": "NOR", "826": "GBR", "250": "FRA", "724": "ESP", "076": "BRA", "152": "CHL", "604": "PER", "540": "NCL",
    "036": "AUS",
}
# Países que bordean cada paso marítimo: se iluminan en el mapa cuando la ruta lo cruza
PASO_PAISES = {
    "panama": ["PAN"], "yucatan": ["CUB"], "bab": ["YEM", "DJI", "ERI"], "suez": ["EGY"], "hormuz": ["IRN", "OMN"],
    "malaca": ["MYS", "IDN", "SGP"], "gibraltar": ["ESP", "MAR"], "mancha": ["GBR", "FRA"], "bos": ["TUR"],
    "cabo": ["ZAF"], "luzon": ["PHL", "TWN"],
}

# Material -> serie de precio (mercado_fastmarkets/loaders.FERROALEACIONES), para
# cruzar la ruta con el semáforo de alza y el quiebre en formación del precio
SERIE_PRECIO = {
    "FeMn": "FerroManganeso", "SiMn": "SilicoManganeso", "FeSi": "FerroSilicio", "FeCr": "FerroCromo",
    "FeV": "FerroVanadio", "FeMo": "FerroMolibdeno", "FeTi": "FerroTitanio", "FeNb": "FerroNiobio", "Ni": "Niquel",
}

# Supuestos de tiempo (estimados)
NUDOS_RAPIDO, NUDOS_LENTO = 14.0, 11.0    # granelero
DIAS_PUERTO = (2, 6)                      # carga, descarga y espera
DIAS_CANAL = 1                            # cruce de Panamá o Suez
KMH_CAMION = 60
