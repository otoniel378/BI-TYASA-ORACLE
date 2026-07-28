"""
scripts/tigie_partidas.py — Catálogo oficial TIGIE (capítulos 72 y 73: Fundición,
hierro y acero / Manufacturas de fundición, hierro o acero), a nivel de partida
(4 dígitos). Fuente: catálogos publicados por SNICE (snice.gob.mx/~oracle/SNICE_DOCS/
CLIGIE72-TIGIE_20200717-20200717.xlsx y CLIGIE73-...), verificados contra el archivo
oficial el 2026-07-28. No se transcribió a mano: se generó parseando esos xlsx.

PARTIDAS: código de 4 dígitos -> descripción legal + subcapítulo (agrupación más
amplia, solo definida en el capítulo 72). Se usa para derivar CATEGORIA_PRODUCTO en
BRONZE_SNICE_SIDERURGICO a partir de FRACCION_ARANCELARIA[:4].

FRACCIONES_NO_KG: fracciones (6 dígitos, capítulo.partida.subpartida sin puntos) cuya
unidad de medida oficial NO es "Kg" (son "Pza"). Ninguna aparece en los avisos
Siderúrgico hasta ahora (son cisternas/barriles grandes y estufas, partidas 7310 y
7321), pero se deja como lista de vigilancia: si una de estas aparece en un aviso,
sumar su VOLUMEN_AVISO junto con el resto (en Kg) daría un total sin sentido.
"""

PARTIDAS = {
    "7201": {"descripcion": "Fundición en bruto y fundición especular, en lingotes, bloques o demás formas primarias.", "subcapitulo": "PRODUCTOS BÁSICOS; GRANALLAS Y POLVO", "capitulo": "72"},
    "7202": {"descripcion": "Ferroaleaciones.", "subcapitulo": "PRODUCTOS BÁSICOS; GRANALLAS Y POLVO", "capitulo": "72"},
    "7203": {"descripcion": "Productos férreos obtenidos por reducción directa de minerales de hierro y demás productos férreos esponjosos, en trozos, \"pellets\" o formas similares; hierro con una pureza superior o igual al 99.94% en peso, en trozos, \"pellets\" o formas similares.", "subcapitulo": "PRODUCTOS BÁSICOS; GRANALLAS Y POLVO", "capitulo": "72"},
    "7204": {"descripcion": "Desperdicios y desechos (chatarra), de fundición, hierro o acero; lingotes de chatarra de hierro o acero.", "subcapitulo": "PRODUCTOS BÁSICOS; GRANALLAS Y POLVO", "capitulo": "72"},
    "7205": {"descripcion": "Granallas y polvo, de fundición en bruto, de fundición especular, de hierro o acero.", "subcapitulo": "PRODUCTOS BÁSICOS; GRANALLAS Y POLVO", "capitulo": "72"},
    "7206": {"descripcion": "Hierro y acero sin alear, en lingotes o demás formas primarias, excepto el hierro de la partida 72.03.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7207": {"descripcion": "Productos intermedios de hierro o acero sin alear.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7208": {"descripcion": "Productos laminados planos de hierro o acero sin alear, de anchura superior o igual a 600 mm, laminados en caliente, sin chapar ni revestir.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7209": {"descripcion": "Productos laminados planos de hierro o acero sin alear, de anchura superior o igual a 600 mm, laminados en frío, sin chapar ni revestir.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7210": {"descripcion": "Productos laminados planos de hierro o acero sin alear, de anchura superior o igual a 600 mm, chapados o revestidos.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7211": {"descripcion": "Productos laminados planos de hierro o acero sin alear, de anchura inferior a 600 mm, sin chapar ni revestir.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7212": {"descripcion": "Productos laminados planos de hierro o acero sin alear, de anchura inferior a 600 mm, chapados o revestidos.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7213": {"descripcion": "Alambrón de hierro o acero sin alear.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7214": {"descripcion": "Barras de hierro o acero sin alear, simplemente forjadas, laminadas o extrudidas, en caliente, así como las sometidas a torsión después del laminado.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7215": {"descripcion": "Las demás barras de hierro o acero sin alear.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7216": {"descripcion": "Perfiles de hierro o acero sin alear.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7217": {"descripcion": "Alambre de hierro o acero sin alear.", "subcapitulo": "HIERRO Y ACERO SIN ALEAR", "capitulo": "72"},
    "7218": {"descripcion": "Acero inoxidable en lingotes o demás formas primarias; productos intermedios de acero inoxidable.", "subcapitulo": "ACERO INOXIDABLE", "capitulo": "72"},
    "7219": {"descripcion": "Productos laminados planos de acero inoxidable, de anchura superior o igual a 600 mm.", "subcapitulo": "ACERO INOXIDABLE", "capitulo": "72"},
    "7220": {"descripcion": "Productos laminados planos de acero inoxidable, de anchura inferior a 600 mm.", "subcapitulo": "ACERO INOXIDABLE", "capitulo": "72"},
    "7221": {"descripcion": "Alambrón de acero inoxidable.", "subcapitulo": "ACERO INOXIDABLE", "capitulo": "72"},
    "7222": {"descripcion": "Barras y perfiles, de acero inoxidable.", "subcapitulo": "ACERO INOXIDABLE", "capitulo": "72"},
    "7223": {"descripcion": "Alambre de acero inoxidable.", "subcapitulo": "ACERO INOXIDABLE", "capitulo": "72"},
    "7224": {"descripcion": "Los demás aceros aleados en lingotes o demás formas primarias; productos intermedios de los demás aceros aleados.", "subcapitulo": "LOS DEMÁS ACEROS ALEADOS; BARRAS HUECAS PARA PERFORACIÓN, DE ACERO ALEADO O SIN ALEAR", "capitulo": "72"},
    "7225": {"descripcion": "Productos laminados planos de los demás aceros aleados, de anchura superior o igual a 600 mm.", "subcapitulo": "LOS DEMÁS ACEROS ALEADOS; BARRAS HUECAS PARA PERFORACIÓN, DE ACERO ALEADO O SIN ALEAR", "capitulo": "72"},
    "7226": {"descripcion": "Productos laminados planos de los demás aceros aleados, de anchura inferior a 600 mm.", "subcapitulo": "LOS DEMÁS ACEROS ALEADOS; BARRAS HUECAS PARA PERFORACIÓN, DE ACERO ALEADO O SIN ALEAR", "capitulo": "72"},
    "7227": {"descripcion": "Alambrón de los demás aceros aleados.", "subcapitulo": "LOS DEMÁS ACEROS ALEADOS; BARRAS HUECAS PARA PERFORACIÓN, DE ACERO ALEADO O SIN ALEAR", "capitulo": "72"},
    "7228": {"descripcion": "Barras y perfiles, de los demás aceros aleados; barras huecas para perforación, de aceros aleados o sin alear.", "subcapitulo": "LOS DEMÁS ACEROS ALEADOS; BARRAS HUECAS PARA PERFORACIÓN, DE ACERO ALEADO O SIN ALEAR", "capitulo": "72"},
    "7229": {"descripcion": "Alambre de los demás aceros aleados.", "subcapitulo": "LOS DEMÁS ACEROS ALEADOS; BARRAS HUECAS PARA PERFORACIÓN, DE ACERO ALEADO O SIN ALEAR", "capitulo": "72"},
    "7301": {"descripcion": "Tablestacas de hierro o acero, incluso perforadas o hechas con elementos ensamblados; perfiles de hierro o acero obtenidos por soldadura.", "subcapitulo": None, "capitulo": "73"},
    "7302": {"descripcion": "Elementos para vías férreas, de fundición, hierro o acero: carriles (rieles), contracarriles (contrarrieles) y cremalleras, agujas, puntas de corazón, varillas para mando de agujas y otros elementos para cruce o cambio de vías, traviesas (durmientes), bridas, cojinetes, cuñas, placas de asiento, placas de unión, placas y tirantes de separación y demás piezas concebidas especialmente para la colocación, unión o fijación de carriles (rieles).", "subcapitulo": None, "capitulo": "73"},
    "7303": {"descripcion": "Tubos y perfiles huecos, de fundición.", "subcapitulo": None, "capitulo": "73"},
    "7304": {"descripcion": "Tubos y perfiles huecos, sin costura (sin soldadura), de hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7305": {"descripcion": "Los demás tubos (por ejemplo: soldados o remachados) de sección circular con diámetro exterior superior a 406.4 mm, de hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7306": {"descripcion": "Los demás tubos y perfiles huecos (por ejemplo: soldados, remachados, grapados o con los bordes simplemente aproximados), de hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7307": {"descripcion": "Accesorios de tubería (por ejemplo: empalmes (racores), codos, manguitos), de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7308": {"descripcion": "Construcciones y sus partes (por ejemplo: puentes y sus partes, compuertas de esclusas, torres, castilletes, pilares, columnas, armazones para techumbre, techados, puertas y ventanas y sus marcos, contramarcos y umbrales, cortinas de cierre, barandillas), de fundición, hierro o acero, excepto las construcciones prefabricadas de la partida 94.06; chapas, barras, perfiles, tubos y similares, de fundición, hierro o acero, preparados para la construcción.", "subcapitulo": None, "capitulo": "73"},
    "7309": {"descripcion": "Depósitos, cisternas, cubas y recipientes similares para cualquier materia (excepto gas comprimido o licuado), de fundición, hierro o acero, de capacidad superior a 300 l, sin dispositivos mecánicos ni térmicos, incluso con revestimiento interior o calorífugo.", "subcapitulo": None, "capitulo": "73"},
    "7310": {"descripcion": "Depósitos, barriles, tambores, bidones, latas o botes, cajas y recipientes similares, para cualquier materia (excepto gas comprimido o licuado), de fundición, hierro o acero, de capacidad inferior o igual a 300 l, sin dispositivos mecánicos ni térmicos, incluso con revestimiento interior o calorífugo.", "subcapitulo": None, "capitulo": "73"},
    "7311": {"descripcion": "Recipientes para gas comprimido o licuado, de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7312": {"descripcion": "Cables, trenzas, eslingas y artículos similares, de hierro o acero, sin aislar para electricidad.", "subcapitulo": None, "capitulo": "73"},
    "7313": {"descripcion": "Alambre de púas, de hierro o acero; alambre (simple o doble) y fleje, torcidos, incluso con púas, de hierro o acero, de los tipos utilizados para cercar.", "subcapitulo": None, "capitulo": "73"},
    "7314": {"descripcion": "Telas metálicas (incluidas las continuas o sin fin), redes y rejas, de alambre de hierro o acero; chapas y tiras, extendidas (desplegadas), de hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7315": {"descripcion": "Cadenas y sus partes, de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7316": {"descripcion": "Anclas, rezones y sus partes, de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7317": {"descripcion": "Puntas, clavos, chinchetas (chinches), grapas apuntadas, onduladas o biseladas, y artículos similares, de fundición, hierro o acero, incluso con cabeza de otras materias, excepto de cabeza de cobre.", "subcapitulo": None, "capitulo": "73"},
    "7318": {"descripcion": "Tornillos, pernos, tuercas, tirafondos, escarpias roscadas, remaches, pasadores, clavijas, chavetas, arandelas (incluidas las arandelas de muelle (resorte) y artículos similares, de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7319": {"descripcion": "Agujas de coser, de tejer, pasacintas, agujas de ganchillo (croché), punzones para bordar y artículos similares, de uso manual, de hierro o acero; alfileres de gancho (imperdibles) y demás alfileres de hierro o acero, no expresados ni comprendidos en otra parte.", "subcapitulo": None, "capitulo": "73"},
    "7320": {"descripcion": "Muelles (resortes), ballestas y sus hojas, de hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7321": {"descripcion": "Estufas, calderas con hogar, cocinas (incluidas las que puedan utilizarse accesoriamente para calefacción central), parrillas (barbacoas), braseros, hornillos de gas, calientaplatos y aparatos no eléctricos similares, de uso doméstico, y sus partes, de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7322": {"descripcion": "Radiadores para calefacción central, de calentamiento no eléctrico, y sus partes, de fundición, hierro o acero; generadores y distribuidores de aire caliente (incluidos los distribuidores que puedan funcionar también como distribuidores de aire fresco o acondicionado), de calentamiento no eléctrico, que lleven un ventilador o un soplador con motor, y sus partes, de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7323": {"descripcion": "Artículos de uso doméstico y sus partes, de fundición, hierro o acero; lana de hierro o acero; esponjas, estropajos, guantes y artículos similares para fregar, lustrar o usos análogos, de hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7324": {"descripcion": "Artículos de higiene o tocador, y sus partes, de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7325": {"descripcion": "Las demás manufacturas moldeadas de fundición, hierro o acero.", "subcapitulo": None, "capitulo": "73"},
    "7326": {"descripcion": "Las demás manufacturas de hierro o acero.", "subcapitulo": None, "capitulo": "73"},
}

FRACCIONES_NO_KG = {
    "73101005",
    "73102905",
    "73211101",
    "73211102",
    "73211199",
    "73211201",
    "73211901",
    "73218102",
    "73218202",
    "73218901",
}


def categoria_de(fraccion_arancelaria: str):
    """Devuelve (descripcion_categoria, subcapitulo) a partir de la fracción completa,
    usando los primeros 4 dígitos (partida). None si la partida no está en el catálogo."""
    if not fraccion_arancelaria or len(fraccion_arancelaria) < 4:
        return None, None
    partida = fraccion_arancelaria[:4]
    info = PARTIDAS.get(partida)
    if not info:
        return None, None
    return info["descripcion"], info["subcapitulo"]
