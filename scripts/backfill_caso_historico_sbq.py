"""
scripts/backfill_caso_historico_sbq.py — Carga única del caso histórico que
motivó el monitor de DOF (Regla 8a para bolas de molienda, DOF 30/10/2026,
código 5802604): como ocurrió ANTES de que scripts/monitor_dof.py existiera,
nunca quedó registrado en ADMIN.GOLD_ALERTAS_DOF ni en
ADMIN.GOLD_MEDIDAS_ARANCELARIAS, aunque sí se documentó a mano en
scripts/reporte_historial_aranceles.py (reporte personal, no versionado).

Sin este backfill, la nueva sección de Aranceles del dashboard (y la tabla de
medidas por fracción) arrancarían sin ningún caso real todavía — este es
justo el caso que demostró que hacía falta el monitor.

Uso (una sola vez):
  python scripts/backfill_caso_historico_sbq.py
"""

import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import oracledb
from dotenv import load_dotenv

load_dotenv()

CASO = {
    "codigo": "5802604",
    "fecha_dof": "30/10/2026",
    "dependencia": "PODER EJECUTIVO SECRETARIA DE ECONOMIA",
    "descripcion": "ACUERDO que modifica el diverso por el que la Secretaria de Economia "
                    "emite reglas y criterios de caracter general en materia de comercio exterior.",
    "url": "https://dof.gob.mx/nota_detalle.php?codigo=5802604&fecha=30/10/2026",
    "relevante": 1,
    "impacto": "Alto",
    "direccion": "Negativo",
    "resumen": "Autoriza importar via Regla 8a (exenta o con arancel preferencial) barras de "
               "acero aleado (7228.30.01/99) para fabricar bolas de molienda para mineria.",
    "fracciones_tyasa": "72091601, 72091701, 72091801, 72283001, 72283099, 73261103",
    "correo_enviado": 0,
}

MEDIDAS = [
    {"fraccion": "72283001", "tipo_medida": "Exencion o regimen especial",
     "valor": "Exento (0%) bajo Regla 8a para fabricacion de bolas de molienda"},
    {"fraccion": "72283099", "tipo_medida": "Exencion o regimen especial",
     "valor": "Exento (0%) bajo Regla 8a para fabricacion de bolas de molienda"},
]


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


def run():
    from scripts.fracciones_tyasa import es_fraccion_tyasa

    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER SESSION DISABLE PARALLEL DML")

        cursor.execute(
            """
            MERGE INTO ADMIN.GOLD_ALERTAS_DOF T
            USING (SELECT :codigo AS CODIGO FROM dual) S
            ON (T.CODIGO = S.CODIGO)
            WHEN NOT MATCHED THEN INSERT
                (CODIGO, FECHA_DOF, DEPENDENCIA, DESCRIPCION, URL, RELEVANTE,
                 IMPACTO, DIRECCION, RESUMEN, FRACCIONES_TYASA, CORREO_ENVIADO)
            VALUES
                (:codigo, :fecha_dof, :dependencia, :descripcion, :url, :relevante,
                 :impacto, :direccion, :resumen, :fracciones_tyasa, :correo_enviado)
            """,
            CASO,
        )
        print(f"  GOLD_ALERTAS_DOF: {cursor.rowcount} fila insertada (0 si ya existía)")

        for m in MEDIDAS:
            cursor.execute(
                """
                MERGE INTO ADMIN.GOLD_MEDIDAS_ARANCELARIAS T
                USING (SELECT :codigo_dof AS CODIGO_DOF, :fraccion AS FRACCION FROM dual) S
                ON (T.CODIGO_DOF = S.CODIGO_DOF AND T.FRACCION = S.FRACCION)
                WHEN NOT MATCHED THEN INSERT
                    (CODIGO_DOF, FRACCION, ES_FRACCION_TYASA, TIPO_MEDIDA, VALOR,
                     PAIS_ORIGEN, VIGENCIA_DESDE, VIGENCIA_HASTA, FECHA_DOF, URL)
                VALUES
                    (:codigo_dof, :fraccion, :es_tyasa, :tipo_medida, :valor,
                     NULL, NULL, NULL, :fecha_dof, :url)
                """,
                {
                    "codigo_dof": CASO["codigo"],
                    "fraccion": m["fraccion"],
                    "es_tyasa": 1 if es_fraccion_tyasa(m["fraccion"]) else 0,
                    "tipo_medida": m["tipo_medida"],
                    "valor": m["valor"],
                    "fecha_dof": CASO["fecha_dof"],
                    "url": CASO["url"],
                },
            )
            print(f"  GOLD_MEDIDAS_ARANCELARIAS: fracción {m['fraccion']} — {cursor.rowcount} fila insertada (0 si ya existía)")

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    print("\nLISTO")


if __name__ == "__main__":
    run()
