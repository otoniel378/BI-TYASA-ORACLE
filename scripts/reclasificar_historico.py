"""
reclasificar_historico.py — Corrida ÚNICA para limpiar el backlog de noticias
que quedaron mal clasificadas mientras la cuota gratuita de Gemini estaba
agotada (12 ago - 21 sep 2026): ~1600 noticias con RAZON='No se pudo
clasificar' y SENTIMIENTO='neutro' por default, no por análisis real.

Reclasifica sentimiento (Gemini, ahora con facturación activa) y categoría
(modelo local, gratis) para esas filas y actualiza Oracle directamente por ID
— no vuelve a buscar noticias, solo re-analiza las que ya están guardadas.

Diseño resistente a fallas (el proceso tarda ~30 min y puede toparse con
timeouts de red de Gemini o de Oracle):
  1. Cada resultado de Gemini se guarda de inmediato en un checkpoint local
     (data/reclasificacion_checkpoint.jsonl) — si el proceso se cae, correrlo
     de nuevo NO vuelve a llamar a Gemini para lo que ya está en el checkpoint.
  2. La escritura a Oracle se hace en lotes chicos, abriendo una conexión
     NUEVA para cada lote (nunca una sola conexión de 30 minutos, que es lo
     que causó el primer fallo: DPY-4011, la conexión se cae por inactividad
     antes de llegar al UPDATE final).

Uso:
  python scripts/reclasificar_historico.py
"""

import json
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

CHECKPOINT_PATH = _root.parent / "data" / "reclasificacion_checkpoint.jsonl"
BATCH_SIZE = 150


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


def _cargar_checkpoint() -> dict:
    """IDs ya reclasificados (checkpoint previo) -> resultado."""
    if not CHECKPOINT_PATH.exists():
        return {}
    resultados = {}
    for linea in CHECKPOINT_PATH.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            d = json.loads(linea)
            resultados[d["id"]] = d
        except Exception:
            pass
    return resultados


def _append_checkpoint(registro: dict):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


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

    # Consulta inicial: una sola conexión corta, se cierra de inmediato.
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ID, TITULO, DESCRIPCION, FUENTE, URL, FECHA_PUB
        FROM ADMIN.GOLD_SENTIMIENTO_NOTICIAS
        WHERE RAZON = 'No se pudo clasificar'
        ORDER BY FECHA_PUB
    """)
    filas = cur.fetchall()
    cur.close()
    conn.close()
    print(f"\nNoticias marcadas para reclasificar: {len(filas)}")

    if not filas:
        print("Nada que hacer.")
        return

    noticias = [
        {
            "id": id_, "titulo": titulo, "descripcion": desc, "fuente": fuente,
            "url": url, "fecha_pub": str(fecha_pub)[:10] if fecha_pub else "",
        }
        for id_, titulo, desc, fuente, url, fecha_pub in filas
    ]

    # ── FASE 1: clasificar (con checkpoint — resume-safe) ───────────────────────
    checkpoint = _cargar_checkpoint()
    print(f"Ya en checkpoint de una corrida previa: {len(checkpoint)}")
    pendientes = [n for n in noticias if n["id"] not in checkpoint]
    print(f"Pendientes de clasificar ahora: {len(pendientes)}")

    if pendientes:
        print("\nReclasificando sentimiento con Gemini (categoría se calcula después, en lote)...")
        for i, n in enumerate(pendientes, 1):
            try:
                r = clasificar_noticia(n, gemini_key, force_refresh=True)
                _append_checkpoint({
                    "id": n["id"],
                    "sentimiento": r.get("sentimiento", "neutro"),
                    "score": float(r.get("score", 0.0) or 0.0),
                    "variable_principal": r.get("variable_principal", "otro"),
                    "senal": r.get("señal", "neutro"),
                    "alcance": r.get("alcance", "ambos"),
                    "razon": (r.get("razon", "") or "")[:300],
                    "confianza": r.get("confianza", "Baja"),
                })
                time.sleep(0.5)
            except Exception as e:
                print(f"  [WARN] {n['id']}: {e}")
            if i % 100 == 0:
                print(f"  {i}/{len(pendientes)}...")

    checkpoint = _cargar_checkpoint()
    print(f"\nTotal en checkpoint tras esta corrida: {len(checkpoint)}")

    # ── Categoría (modelo local, se recalcula siempre — es gratis e instantáneo) ─
    print("\nClasificando categoría con el modelo local...")
    resultados_cat = clasificar_categoria_lote_local(
        [{"url": n["id"], "titulo": n["titulo"], "descripcion": n["descripcion"]} for n in noticias]
    )
    categoria_por_id = {r["url"]: r["categoria"] for r in resultados_cat}

    # ── FASE 2: escribir a Oracle en lotes, conexión nueva por lote ─────────────
    print(f"\nEscribiendo a Oracle en lotes de {BATCH_SIZE} (conexión nueva por lote)...")
    ahora = datetime.now(timezone.utc)

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

    todas_updates = []
    for n in noticias:
        r = checkpoint.get(n["id"])
        if not r:
            continue
        todas_updates.append({
            "id": n["id"],
            "fecha_analisis": ahora,
            "sentimiento": r["sentimiento"],
            "score": r["score"],
            "variable_principal": r["variable_principal"],
            "senal": r["senal"],
            "alcance": r["alcance"],
            "razon": r["razon"],
            "confianza": r["confianza"],
            "categoria": categoria_por_id.get(n["id"], "Mercado Global y Precios"),
        })

    total_guardadas = 0
    for i in range(0, len(todas_updates), BATCH_SIZE):
        lote = todas_updates[i:i + BATCH_SIZE]
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("ALTER SESSION DISABLE PARALLEL DML")
            cur.executemany(update_sql, lote)
            conn.commit()
            total_guardadas += len(lote)
            print(f"  Lote {i // BATCH_SIZE + 1}: {len(lote)} filas guardadas "
                  f"(acumulado {total_guardadas}/{len(todas_updates)})")
        except Exception as e:
            print(f"  [ERROR] lote {i // BATCH_SIZE + 1} no se guardó: {e}")
        finally:
            cur.close()
            conn.close()

    print(f"\nTotal actualizadas en Oracle: {total_guardadas}/{len(todas_updates)}")

    n_pos = sum(1 for u in todas_updates if u["sentimiento"] == "positivo")
    n_neg = sum(1 for u in todas_updates if u["sentimiento"] == "negativo")
    n_neu = sum(1 for u in todas_updates if u["sentimiento"] == "neutro")
    print(f"Nueva distribución: {n_pos} positivas | {n_neu} neutras | {n_neg} negativas")
    print("\nLISTO.")


if __name__ == "__main__":
    run()
