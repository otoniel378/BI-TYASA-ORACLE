"""
memoria_ia.py — Memoria de contexto persistente entre sesiones del Chat IA.

Guarda en BigQuery (gold_memoria_ia) los insights clave extraídos de cada
conversación. El chat los inyecta al inicio de cada sesión como contexto previo.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

import pandas as pd

PROJECT  = "project-d0cf2519-d089-47d3-930"
DATASET  = "tyasa_bi"
TABLE    = f"{PROJECT}.{DATASET}.gold_memoria_ia"
STAGING  = f"{PROJECT}.{DATASET}._staging_memoria_ia"

_MAX_MEMORIAS_CONTEXTO = 8   # cuántas memorias recientes inyectar al chat


# ─────────────────────────────────────────────────────────────────────────────
def _get_client():
    from google.cloud import bigquery
    return bigquery.Client(project=PROJECT)


def crear_tabla_si_no_existe():
    from google.cloud import bigquery
    client = _get_client()
    schema = [
        bigquery.SchemaField("id_memoria",    "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fecha",          "DATE"),
        bigquery.SchemaField("usuario",        "STRING"),
        bigquery.SchemaField("tipo",           "STRING"),
        bigquery.SchemaField("tema",           "STRING"),
        bigquery.SchemaField("contenido",      "STRING"),
        bigquery.SchemaField("relevancia",     "STRING"),
        bigquery.SchemaField("fuente_sesion",  "STRING"),
    ]
    table = bigquery.Table(TABLE, schema=schema)
    client.create_table(table, exists_ok=True)


def guardar_memorias(memorias: list[dict], usuario: str = "sistema") -> int:
    """Guarda una lista de memorias en BigQuery (upsert por id_memoria)."""
    if not memorias:
        return 0

    from google.cloud import bigquery

    rows = []
    for m in memorias:
        contenido = m.get("contenido", "")
        id_mem = hashlib.md5(
            f"{usuario}|{m.get('tema','')}|{contenido[:80]}".encode()
        ).hexdigest()[:20]
        rows.append({
            "id_memoria":   id_mem,
            "fecha":        date.today().isoformat(),
            "usuario":      usuario,
            "tipo":         m.get("tipo", "insight"),
            "tema":         (m.get("tema", "") or "")[:100],
            "contenido":    (contenido or "")[:1000],
            "relevancia":   m.get("relevancia", "Media"),
            "fuente_sesion": m.get("fuente_sesion", "chat"),
        })

    df = pd.DataFrame(rows)
    client = _get_client()

    job_cfg = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("id_memoria",    "STRING"),
            bigquery.SchemaField("fecha",          "DATE"),
            bigquery.SchemaField("usuario",        "STRING"),
            bigquery.SchemaField("tipo",           "STRING"),
            bigquery.SchemaField("tema",           "STRING"),
            bigquery.SchemaField("contenido",      "STRING"),
            bigquery.SchemaField("relevancia",     "STRING"),
            bigquery.SchemaField("fuente_sesion",  "STRING"),
        ],
    )
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    client.load_table_from_dataframe(df, STAGING, job_config=job_cfg).result()

    merge_sql = f"""
    MERGE `{TABLE}` T
    USING `{STAGING}` S ON T.id_memoria = S.id_memoria
    WHEN NOT MATCHED THEN INSERT ROW
    WHEN MATCHED THEN UPDATE SET
        fecha        = S.fecha,
        contenido    = S.contenido,
        relevancia   = S.relevancia,
        fuente_sesion = S.fuente_sesion
    """
    client.query(merge_sql).result()
    client.delete_table(STAGING, not_found_ok=True)
    return len(rows)


def cargar_memorias_contexto(usuario: str = "sistema", n: int = _MAX_MEMORIAS_CONTEXTO) -> list[dict]:
    """Carga las N memorias más recientes para inyectar como contexto al chat."""
    try:
        from core.db_connector import run_query
        sql = f"""
            SELECT tema, contenido, tipo, relevancia, fecha
            FROM `{TABLE}`
            WHERE usuario = '{usuario}'
            ORDER BY
                CASE relevancia WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END,
                fecha DESC
            LIMIT {n}
        """
        df = run_query(sql)
        if df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception:
        return []


def extraer_memorias_de_conversacion(
    mensajes: list[dict],
    gemini_key: str,
    model: str = "gemini-2.5-flash",
) -> list[dict]:
    """
    Usa Gemini para extraer insights clave de una conversación y convertirlos
    en memorias estructuradas para guardar.
    """
    if not mensajes or not gemini_key:
        return []

    texto_conv = "\n".join(
        f"[{m['role'].upper()}]: {m['content']}"
        for m in mensajes
        if m.get("content", "").strip()
    )
    if len(texto_conv) < 100:
        return []

    prompt = f"""Analiza esta conversación de análisis de datos de TYASA BI y extrae los insights clave.

CONVERSACIÓN:
{texto_conv[:3000]}

Responde ÚNICAMENTE con un JSON array de memorias (máximo 5). Cada memoria:
{{
  "tipo": "insight" | "patron" | "alerta" | "decision" | "hallazgo",
  "tema": "tema específico (máximo 6 palabras)",
  "contenido": "descripción del insight (máximo 80 palabras)",
  "relevancia": "Alta" | "Media" | "Baja"
}}

Si no hay insights valiosos, responde con array vacío: []
Solo incluye información que sería útil recordar en sesiones futuras sobre datos de TYASA."""

    try:
        from google import genai
        from google.genai import types as T

        client = genai.Client(api_key=gemini_key)
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=T.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1024,
                thinking_config=T.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (resp.text or "").strip()
    except Exception:
        try:
            import requests, re as _re
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={gemini_key}"
            )
            body = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
            }
            r = requests.post(url, json=body, timeout=30)
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip() if r.ok else ""
        except Exception:
            return []

    try:
        import re
        clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("`").strip()
        m = re.search(r"\[.*\]", clean, re.DOTALL)
        if m:
            memorias = json.loads(m.group())
            if isinstance(memorias, list):
                return [x for x in memorias if isinstance(x, dict) and x.get("contenido")]
    except Exception:
        pass
    return []


def construir_contexto_previo(memorias: list[dict]) -> str:
    """Formatea las memorias como texto de contexto para inyectar al sistema prompt."""
    if not memorias:
        return ""
    lineas = ["CONTEXTO DE SESIONES ANTERIORES:"]
    for m in memorias:
        rel = m.get("relevancia", "")
        prefix = "🔴" if rel == "Alta" else "🟡" if rel == "Media" else "⚪"
        lineas.append(
            f"{prefix} [{m.get('tipo','insight').upper()}] {m.get('tema','')}: {m.get('contenido','')}"
        )
    return "\n".join(lineas)
