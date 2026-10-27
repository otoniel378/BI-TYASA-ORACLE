"""
scripts/seed_eventos_historicos.py — Siembra puntual (uso único) de los
eventos históricos curados a mano en GOLD_EVENTOS_HISTORICOS. Idempotente:
usa MERGE por ID, correrlo de nuevo actualiza en vez de duplicar.

Uso:
    python scripts/seed_eventos_historicos.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

# Nombres de ferroaleaciones tal como los usa mercado_fastmarkets/loaders.py::FERROALEACIONES
FERROS_TODOS = ("FerroManganeso,SilicoManganeso,FerroSilicio,FerroCromo,"
                "FerroVanadio,FerroMolibdeno,FerroTitanio,FerroNiobio,Niquel")

EVENTOS = [
    dict(
        id="covid_inicio_2020",
        fecha_inicio=date(2020, 3, 1), fecha_fin=date(2020, 6, 30),
        nombre="Inicio pandemia COVID-19",
        descripcion="Colapso de demanda industrial global por confinamientos; caída abrupta "
                     "en producción manufacturera y construcción en México.",
        variables="IMAI_ActividadIndustrial_Indice,IMAI_Construccion_Indice,IMAI_HierroAcero_3311_Indice,"
                  + FERROS_TODOS,
        fuente="OMS declara pandemia global, 2020-03-11",
    ),
    dict(
        id="aranceles_232_2018",
        fecha_inicio=date(2018, 6, 1), fecha_fin=None,
        nombre="Aranceles Sección 232 EE.UU. al acero",
        descripcion="Estados Unidos impone 25% de arancel a importaciones de acero (incluido México) "
                     "bajo la Sección 232 de la Trade Expansion Act.",
        variables="HRC_CME_USD,BC_Siderurgia_Importaciones",
        fuente="Proclamation 9705, Federal Register, 2018-03-08 (entrada en vigor 2018-06-01 para México/Canadá)",
    ),
    dict(
        id="tmec_entrada_vigor_2020",
        fecha_inicio=date(2020, 7, 1), fecha_fin=None,
        nombre="Entrada en vigor del T-MEC",
        descripcion="Reemplaza al TLCAN; nuevas reglas de origen para el sector automotriz y acero "
                     "entre México, EE.UU. y Canadá.",
        variables="BC_Siderurgia_Importaciones,USD_MXN",
        fuente="Entrada en vigor oficial, 2020-07-01",
    ),
    dict(
        id="escasez_acero_post_covid_2021",
        fecha_inicio=date(2021, 1, 1), fecha_fin=date(2021, 12, 31),
        nombre="Recuperación post-COVID / escasez global de acero",
        descripcion="Repunte de demanda tras reapertura económica supera la oferta disponible; "
                     "precios del acero laminado en caliente en máximos históricos.",
        variables="HRC_CME_USD,IMAI_HierroAcero_3311_Indice,FerroManganeso,SilicoManganeso,FerroSilicio,FerroCromo",
        fuente="Precios HRC CME alcanzan récord histórico en 2021",
    ),
    dict(
        id="invasion_ucrania_2022",
        fecha_inicio=date(2022, 2, 24), fecha_fin=None,
        nombre="Invasión rusa a Ucrania",
        descripcion="Disrupción de cadenas de suministro de energía y materias primas siderúrgicas "
                     "(mineral de hierro, gas natural) a nivel global.",
        variables="Mineral_Hierro,Gas_HenryHub_USD,Gas_TTF_Europa,"
                  "FerroManganeso,SilicoManganeso,FerroSilicio,FerroCromo,FerroTitanio,Niquel",
        fuente="Inicio de la invasión, 2022-02-24 — SiMn India +13% en días: "
               "https://www.argusmedia.com/es/news-and-insights/latest-market-news/2307316-indian-simn-up-as-ukraine-crisis-fuels-fresh-enquiries",
    ),
    # ── Ferroaleaciones (explican quiebres de pages/mercado/09_quiebres_ferroaleaciones.py) ──
    dict(
        id="eskom_crisis_electrica_2008",
        fecha_inicio=date(2008, 1, 25), fecha_fin=date(2008, 7, 31),
        nombre="Crisis eléctrica de Eskom en Sudáfrica",
        descripcion="Eskom declara escasez de energía a sus 138 mayores clientes industriales y raciona "
                     "electricidad. Sudáfrica es productor clave de ferrocromo y aleaciones de manganeso, "
                     "que dependen de hornos eléctricos.",
        variables="FerroCromo,FerroManganeso,SilicoManganeso,FerroVanadio",
        fuente="LBMA, Keeping the lights on — https://www.lbma.org.uk/alchemist/issue-50/keeping-the-lights-on",
    ),
    dict(
        id="crisis_financiera_2008",
        fecha_inicio=date(2008, 9, 15), fecha_fin=date(2009, 6, 30),
        nombre="Crisis financiera global (quiebra de Lehman Brothers)",
        descripcion="Colapso de la demanda de acero y de materias primas; las ferroaleaciones pasan de "
                     "máximos de 2008 a caídas de 40% a 60%.",
        variables=FERROS_TODOS,
        fuente="Federal Reserve History, The Great Recession — "
               "https://www.federalreservehistory.org/essays/great-recession-of-200709",
    ),
    dict(
        id="rally_mineral_manganeso_2016",
        fecha_inicio=date(2016, 3, 1), fecha_fin=date(2016, 12, 31),
        nombre="Rally del mineral de manganeso",
        descripcion="Tras recortes de minas a fines de 2015, el mineral de manganeso sube más de 5 veces "
                     "en 2016; traders en China acumulan inventario en puerto. FeMn y SiMn en Europa "
                     "+105% y +118% en el año; el alza se acelera en octubre.",
        variables="FerroManganeso,SilicoManganeso",
        fuente="Fastmarkets, 2016 REVIEW, 2016-12-22 — https://fastmarkets.com/?p=31406",
    ),
    dict(
        id="vanadio_china_2018",
        fecha_inicio=date(2017, 12, 31), fecha_fin=date(2018, 11, 30),
        nombre="Disparo del ferrovanadio por escasez en China",
        descripcion="China prohíbe importar escoria de vanadio desde fines de 2017; falta materia prima "
                     "y el FeV 50% llega a 500,000 yuan/t en oct 2018, +339% en un año.",
        variables="FerroVanadio",
        fuente="Mysteel, 2018-11-12 — https://www.mysteel.net/news/5002711-chinas-fev-prices-quadruple-on-year-amid-tight-supply",
    ),
    dict(
        id="china_doble_control_energia_2021",
        fecha_inicio=date(2021, 6, 1), fecha_fin=date(2021, 11, 30),
        nombre="China raciona energía (\"doble control\")",
        descripcion="Ningxia, Shaanxi e Inner Mongolia limitan la producción por metas de consumo de "
                     "energía; ~30% de la producción china de ferrosilicio afectada y FeSi 75% a "
                     "20,000 yuan/t (+45%) en sept 2021.",
        variables="FerroSilicio,SilicoManganeso,FerroManganeso",
        fuente="Bigmint — https://bigmint.co/insights/detail/china-ferro-silicon-prices-surge-on-rigid-demand-reduced-output-246334",
    ),
    dict(
        id="ciclon_megan_gemco_2024",
        fecha_inicio=date(2024, 3, 17), fecha_fin=date(2024, 7, 31),
        nombre="Ciclón Megan cierra la mina GEMCO (Australia)",
        descripcion="La mina de South32, ~10% del mineral de manganeso mundial, suspende operaciones; "
                     "el índice de mineral sube de 4.29 a 9.01 USD/dmtu entre abril y julio.",
        variables="FerroManganeso,SilicoManganeso",
        fuente="Fastmarkets — https://www.fastmarkets.com/insights/gemcos-manganese-ore-suspension-a-volatile-market-driven-by-weak-chinese-steel-demand-panic-buying/",
    ),
    dict(
        id="antidumping_ferrosilicio_eeuu_2024",
        fecha_inicio=date(2024, 3, 28), fecha_fin=date(2025, 5, 12),
        nombre="EE.UU. investiga dumping de ferrosilicio",
        descripcion="CC Metals and Alloys y Ferroglobe piden cuotas antidumping y compensatorias contra "
                     "ferrosilicio de Brasil, Kazajistán, Malasia y Rusia (márgenes alegados de 20% a "
                     "212%); Commerce confirma en sept 2024 (Rusia) y mar 2025 (resto).",
        variables="FerroSilicio",
        fuente="Faegre Drinker, 2024-03 — https://www.faegredrinker.com/en/insights/publications/2024/3/"
               "new-antidumping-duty-and-countervailing-duty-petitions-on-ferrosilicon-from-brazil-malaysia-kazakhstan-and-russia",
    ),
    dict(
        id="indonesia_prohibe_exportar_niquel_2019",
        fecha_inicio=date(2019, 8, 30), fecha_fin=date(2020, 1, 1),
        nombre="Indonesia adelanta la prohibición de exportar mineral de níquel",
        descripcion="El mayor productor de mineral de níquel adelanta dos años el veto (vigente desde "
                     "ene 2020) para procesarlo en casa; el níquel LME pasa de ~12,000 USD/t en julio a "
                     "18,785 USD/t, máximo de cinco años.",
        variables="Niquel",
        fuente="Al Jazeera, 2019-09-02 — https://www.aljazeera.com/economy/2019/9/2/worlds-biggest-nickel-ore-maker-bans-exports-from-january-2020",
    ),
    dict(
        id="lme_suspende_niquel_2022",
        fecha_inicio=date(2022, 3, 7), fecha_fin=date(2022, 3, 25),
        nombre="La LME suspende el níquel tras un short squeeze",
        descripcion="Con la invasión a Ucrania y la posición corta de Tsingshan, el níquel supera "
                     "100,000 USD/t; la LME suspende operaciones el 8 de marzo y cancela operaciones. "
                     "Al reanudar cae a ~35,500 USD/t el 25 de marzo.",
        variables="Niquel",
        fuente="Bloomberg, 2022-03-08 — https://www.bloomberg.com/news/articles/2022-03-08/lme-suspends-nickel-trading-after-unprecedented-price-spike",
    ),
    dict(
        id="caida_ferromanganeso_eeuu_2025",
        fecha_inicio=date(2025, 10, 1), fecha_fin=date(2025, 11, 30),
        nombre="Caída del ferromanganeso en EE.UU. por competencia de importaciones",
        descripcion="Tras meses sin operaciones spot, el FeMn de medio carbono en Pittsburgh cae ~20% a "
                     "fines de octubre; la fortaleza del acero en EE.UU. atrajo importaciones de "
                     "aleaciones más baratas.",
        variables="FerroManganeso,SilicoManganeso",
        fuente="CRU vía Steel Market Update, 2025-11-07 — "
               "https://www.steelmarketupdate.com/2025/11/07/cru-us-bfa-prices-plummet-with-fierce-sales-competition/",
    ),
]

MERGE_SQL = """
MERGE INTO ADMIN.GOLD_EVENTOS_HISTORICOS t
USING (SELECT :id AS ID FROM dual) s
ON (t.ID = s.ID)
WHEN MATCHED THEN UPDATE SET
    FECHA_INICIO = :fecha_inicio, FECHA_FIN = :fecha_fin, NOMBRE = :nombre,
    DESCRIPCION = :descripcion, VARIABLES_RELACIONADAS = :variables, FUENTE = :fuente
WHEN NOT MATCHED THEN INSERT
    (ID, FECHA_INICIO, FECHA_FIN, NOMBRE, DESCRIPCION, VARIABLES_RELACIONADAS, FUENTE)
    VALUES (:id, :fecha_inicio, :fecha_fin, :nombre, :descripcion, :variables, :fuente)
"""


def get_conn() -> oracledb.Connection:
    wallet_dir = os.environ.get("ORACLE_WALLET_DIR", "")
    params = {
        "user":     os.environ.get("ORACLE_USER", "ADMIN"),
        "password": os.environ.get("ORACLE_PASSWORD", ""),
        "dsn":      os.environ.get("ORACLE_DSN", ""),
    }
    if wallet_dir:
        params["config_dir"]      = wallet_dir
        params["wallet_location"] = wallet_dir
        wallet_pw = os.environ.get("ORACLE_WALLET_PASSWORD", "")
        if wallet_pw:
            params["wallet_password"] = wallet_pw
    return oracledb.connect(**params)


def main():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        for ev in EVENTOS:
            cursor.execute(MERGE_SQL, {
                "id": ev["id"], "fecha_inicio": ev["fecha_inicio"], "fecha_fin": ev["fecha_fin"],
                "nombre": ev["nombre"], "descripcion": ev["descripcion"],
                "variables": ev["variables"], "fuente": ev["fuente"],
            })
            conn.commit()
            print(f"  OK {ev['id']}")
    finally:
        cursor.close()
        conn.close()
    print(f"\n{len(EVENTOS)} eventos sembrados/actualizados en GOLD_EVENTOS_HISTORICOS.")


if __name__ == "__main__":
    main()
