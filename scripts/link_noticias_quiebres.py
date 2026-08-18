"""
scripts/link_noticias_quiebres.py — Cruza quiebres estructurales activos
(GOLD_QUIEBRES_DETECTADOS) con noticias ya clasificadas
(GOLD_SENTIMIENTO_NOTICIAS), para explicar automáticamente qué pasó detrás
de cada quiebre de mercado. No llama a Gemini — reutiliza la clasificación
que update_sentimiento_noticias.py ya hizo.

Requiere correr DESPUÉS de update_market_data.py (quiebres frescos) y
update_sentimiento_noticias.py (noticias frescas).

Solo cruza variables de mercado que tienen una categoría de noticias con
correspondencia semántica real (ver MAPEO_VARIABLE_A_CATEGORIA) — el resto
se deja sin cruzar a propósito, para no inventar relaciones falsas.

Uso:
    python scripts/link_noticias_quiebres.py
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()

VENTANA_DIAS = 14  # noticias +/- N días alrededor de la fecha de corte del quiebre

# Variable de mercado (GOLD_QUIEBRES_DETECTADOS.VARIABLE) -> categorías de
# noticias relacionadas (VARIABLES_ACERO en mercado_noticias/analytics/sentimiento.py)
MAPEO_VARIABLE_A_CATEGORIA = {
    "Mineral_Hierro":   ["mineral_hierro"],
    "HRC_CME_USD":      ["HRC_laminado_caliente"],
    "Zinc_USD":         ["zinc_galvanizado", "galvanizado"],
    "USD_MXN":          ["tipo_cambio"],
    "EUR_MXN":          ["tipo_cambio"],
    "Ternium_MX":       ["competidores_ternium_arcelor"],
    "ArcelorMittal":    ["competidores_ternium_arcelor"],
    "ETF_China":        ["china_sobrecapacidad"],
    "Gas_HenryHub_USD": ["energia_electricidad"],
    "Gas_TTF_Europa":   ["energia_electricidad"],
    "ETF_Acero_Global": ["demanda_general", "HRC_laminado_caliente", "CRC_laminado_frio"],
    "CEMEX":            ["construccion"],
}


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
        # Varias DELETE/INSERT seguidos sobre la misma tabla en una transacción
        # disparan ORA-12838 en ADW si el DML se paraleliza automáticamente.
        cursor.execute("ALTER SESSION DISABLE PARALLEL DML")

        cursor.execute("""
            SELECT ID, VARIABLE, FECHA_CORTE
            FROM ADMIN.GOLD_QUIEBRES_DETECTADOS
            WHERE ACTIVO = 1
        """)
        quiebres = cursor.fetchall()
        print(f"Quiebres activos: {len(quiebres)}")

        total_links = 0
        for quiebre_id, variable, fecha_corte in quiebres:
            categorias = MAPEO_VARIABLE_A_CATEGORIA.get(variable)
            if not categorias:
                continue

            desde = fecha_corte - timedelta(days=VENTANA_DIAS)
            hasta = fecha_corte + timedelta(days=VENTANA_DIAS)

            placeholders = ", ".join(f":cat{i}" for i in range(len(categorias)))
            params = {f"cat{i}": c for i, c in enumerate(categorias)}
            params.update({"desde": desde, "hasta": hasta})

            cursor.execute(f"""
                SELECT ID, TITULO, RAZON, FUENTE, URL, FECHA_PUB
                FROM ADMIN.GOLD_SENTIMIENTO_NOTICIAS
                WHERE VARIABLE_PRINCIPAL IN ({placeholders})
                  AND FECHA_PUB BETWEEN :desde AND :hasta
            """, params)
            noticias = cursor.fetchall()
            if not noticias:
                continue

            cursor.execute(
                "DELETE FROM ADMIN.GOLD_NOTICIAS_VINCULADAS WHERE QUIEBRE_ID = :1",
                [quiebre_id],
            )

            ahora = datetime.utcnow()
            rows = [
                (f"{quiebre_id}_{noticia_id}", quiebre_id, variable,
                 titulo, razon, fuente, url, fecha_pub, ahora)
                for noticia_id, titulo, razon, fuente, url, fecha_pub in noticias
            ]
            cursor.executemany("""
                INSERT INTO ADMIN.GOLD_NOTICIAS_VINCULADAS
                    (ID, QUIEBRE_ID, VARIABLE, TITULO, DESCRIPCION, FUENTE, URL, FECHA_PUB, FECHA_CARGA)
                VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)
            """, rows)
            total_links += len(rows)
            print(f"  {variable} ({quiebre_id}): {len(rows)} noticias vinculadas")

        conn.commit()
        print(f"\nTotal vinculos guardados: {total_links}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
