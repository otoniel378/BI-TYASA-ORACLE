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

EVENTOS = [
    dict(
        id="covid_inicio_2020",
        fecha_inicio=date(2020, 3, 1), fecha_fin=date(2020, 6, 30),
        nombre="Inicio pandemia COVID-19",
        descripcion="Colapso de demanda industrial global por confinamientos; caída abrupta "
                     "en producción manufacturera y construcción en México.",
        variables="IMAI_ActividadIndustrial_Indice,IMAI_Construccion_Indice,IMAI_HierroAcero_3311_Indice",
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
        variables="HRC_CME_USD,IMAI_HierroAcero_3311_Indice",
        fuente="Precios HRC CME alcanzan récord histórico en 2021",
    ),
    dict(
        id="invasion_ucrania_2022",
        fecha_inicio=date(2022, 2, 24), fecha_fin=None,
        nombre="Invasión rusa a Ucrania",
        descripcion="Disrupción de cadenas de suministro de energía y materias primas siderúrgicas "
                     "(mineral de hierro, gas natural) a nivel global.",
        variables="Mineral_Hierro,Gas_HenryHub_USD,Gas_TTF_Europa",
        fuente="Inicio de la invasión, 2022-02-24",
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
