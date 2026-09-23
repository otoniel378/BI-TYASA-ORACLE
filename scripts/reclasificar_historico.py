"""
reclasificar_historico.py — Corrida ÚNICA para limpiar el backlog de noticias
que quedaron mal clasificadas mientras la cuota gratuita de Gemini estaba
agotada (12 ago - 21 sep 2026): ~1600 noticias con RAZON='No se pudo
clasificar' y SENTIMIENTO='neutro' por default, no por análisis real.

Reclasifica sentimiento (Gemini, ahora con facturación activa) y categoría
(modelo local, gratis) para esas filas y actualiza Oracle directamente por ID
— no vuelve a buscar noticias, solo re-analiza las que ya están guardadas.

Uso:
  python scripts/reclasificar_historico.py
"""

import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


def _get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        import tomllib
        cfg = tomllib.loads((_root / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
        return cfg.get("GEMINI_API_KEY", "")
    except Exception:
        return ""


def run():
    print("=" * 60)
    print(f"TYASA BI — Reclasificación de backlog dañado — {datetime.now()}")
    print("=" * 60)

    gemini_key = _get_gemini_key()
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY no encontrada.")
        sys.exit(1)

    from scripts.setup_market_tables_oracle import get_conn
    from mercado_noticias.analytics.sentimiento import clasificar_noticia
    from ml.categoria_noticias.inferencia import clasificar_categoria_lote_local

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ID, TITULO, DESCRIPCION, FUENTE, URL, FECHA_PUB
        FROM ADMIN.GOLD_SENTIMIENTO_NOTICIAS
        WHERE RAZON = 'No se pudo clasificar'
        ORDER BY FECHA_PUB
    """)
    filas = cur.fetchall()
    print(f"\nNoticias a reclasificar: {len(filas)}")

    if not filas:
        print("Nada que hacer.")
        cur.close(); conn.close()
        return

    noticias = [
        {
            "id": id_, "titulo": titulo, "descripcion": desc, "fuente": fuente,
            "url": url, "fecha_pub": str(fecha_pub)[:10] if fecha_pub else "",
        }
        for id_, titulo, desc, fuente, url, fecha_pub in filas
    ]

    # ── Sentimiento (Gemini, force_refresh para no reusar caché vieja) ─────────
    print("\nReclasificando sentimiento con Gemini...")
    resultados_sent = {}
    for i, n in enumerate(noticias, 1):
        try:
            r = clasificar_noticia(n, gemini_key, force_refresh=True)
            resultados_sent[n["id"]] = r
            time.sleep(0.5)
        except Exception as e:
            print(f"  [WARN] {n['id']}: {e}")
        if i % 100 == 0:
            print(f"  {i}/{len(noticias)}...")

    # ── Categoría (modelo local, sin límite de cuota) ──────────────────────────
    print("\nReclasificando categoría con el modelo local...")
    resultados_cat = clasificar_categoria_lote_local(
        [{"url": n["id"], "titulo": n["titulo"], "descripcion": n["descripcion"]} for n in noticias]
    )
    categoria_por_id = {r["url"]: r["categoria"] for r in resultados_cat}

    # ── Actualizar Oracle ───────────────────────────────────────────────────────
    print("\nActualizando Oracle...")
    ahora = datetime.utcnow()
    updates = []
    for n in noticias:
        r = resultados_sent.get(n["id"])
        if not r:
            continue
        updates.append({
            "id": n["id"],
            "fecha_analisis": ahora,
            "sentimiento": r.get("sentimiento", "neutro"),
            "score": float(r.get("score", 0.0) or 0.0),
            "variable_principal": r.get("variable_principal", "otro"),
            "senal": r.get("señal", "neutro"),
            "alcance": r.get("alcance", "ambos"),
            "razon": (r.get("razon", "") or "")[:300],
            "confianza": r.get("confianza", "Baja"),
            "categoria": categoria_por_id.get(n["id"], "Mercado Global y Precios"),
        })

    update_sql = """
        UPDATE ADMIN.GOLD_SENTIMIENTO_NOTICIAS SET
            FECHA_ANALISIS     = :fecha_analisis,
            SENTIMIENTO        = :sentimiento,
            SCORE              = :score,
            VARIABLE_PRINCIPAL = :variable_principal,
            SENAL              = :senal,
            ALCANCE            = :alcance,
            RAZON              = :razon,
            CONFIANZA          = :confianza,
            CATEGORIA          = :categoria
        WHERE ID = :id
    """
    cur.execute("ALTER SESSION DISABLE PARALLEL DML")
    cur.executemany(update_sql, updates)
    conn.commit()
    print(f"\nActualizadas {len(updates)} noticias.")

    n_pos = sum(1 for u in updates if u["sentimiento"] == "positivo")
    n_neg = sum(1 for u in updates if u["sentimiento"] == "negativo")
    n_neu = sum(1 for u in updates if u["sentimiento"] == "neutro")
    print(f"Nueva distribución: {n_pos} positivas | {n_neu} neutras | {n_neg} negativas")

    cur.close()
    conn.close()
    print("\nLISTO.")


if __name__ == "__main__":
    run()
