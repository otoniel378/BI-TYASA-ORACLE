"""
memoria_ia.py — Memoria de contexto persistente entre sesiones del Chat IA.

Guarda en Oracle (ADMIN.GOLD_MEMORIA_IA) los insights clave extraídos de cada
conversación. El chat los inyecta al inicio de cada sesión como contexto previo.
La tabla se crea una sola vez con: python scripts/setup_memoria_ia_oracle.py
Si la tabla no existe, cargar devuelve [] y guardar devuelve 0 (el chat sigue funcionando).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

import pandas as pd

TABLE = "GOLD_MEMORIA_IA"

_MAX_MEMORIAS_CONTEXTO = 8   # cuántas memorias recientes inyectar al chat


# ─────────────────────────────────────────────────────────────────────────────
def guardar_memorias(memorias: list[dict], usuario: str = "sistema") -> int:
    """Guarda una lista de memorias en Oracle (upsert por ID_MEMORIA con MERGE)."""
    if not memorias:
        return 0
    from core.db_connector import run_executemany, table_ref

    rows = []
    for m in memorias:
        contenido = m.get("contenido", "") or ""
        id_mem = hashlib.md5(
            f"{usuario}|{m.get('tema','')}|{contenido[:80]}".encode()
        ).hexdigest()[:20]
        rows.append((
            id_mem,
            datetime.combine(date.today(), datetime.min.time()),
            usuario,
            (m.get("tipo", "insight") or "insight")[:30],
            (m.get("tema", "") or "")[:100],
            contenido[:1000],
            (m.get("relevancia", "Media") or "Media")[:10],
            (m.get("fuente_sesion", "chat") or "chat")[:50],
        ))

    sql = f"""
        MERGE INTO {table_ref(TABLE)} T
        USING (SELECT :1 AS ID_MEMORIA, :2 AS FECHA, :3 AS USUARIO, :4 AS TIPO, :5 AS TEMA,
                      :6 AS CONTENIDO, :7 AS RELEVANCIA, :8 AS FUENTE_SESION FROM DUAL) S
        ON (T.ID_MEMORIA = S.ID_MEMORIA)
        WHEN MATCHED THEN UPDATE SET
            T.FECHA = S.FECHA, T.CONTENIDO = S.CONTENIDO,
            T.RELEVANCIA = S.RELEVANCIA, T.FUENTE_SESION = S.FUENTE_SESION
        WHEN NOT MATCHED THEN INSERT
            (ID_MEMORIA, FECHA, USUARIO, TIPO, TEMA, CONTENIDO, RELEVANCIA, FUENTE_SESION)
            VALUES (S.ID_MEMORIA, S.FECHA, S.USUARIO, S.TIPO, S.TEMA, S.CONTENIDO, S.RELEVANCIA, S.FUENTE_SESION)
    """
    try:
        return run_executemany(sql, rows)
    except Exception:
        return 0


def cargar_memorias_contexto(usuario: str = "sistema", n: int = _MAX_MEMORIAS_CONTEXTO) -> list[dict]:
    """Carga las N memorias más recientes para inyectar como contexto al chat."""
    try:
        from core.db_connector import run_query_params, table_ref
        sql = f"""
            SELECT TEMA, CONTENIDO, TIPO, RELEVANCIA, FECHA
            FROM {table_ref(TABLE)}
            WHERE USUARIO = :usuario
            ORDER BY
                CASE RELEVANCIA WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END,
                FECHA DESC
            FETCH FIRST {int(n)} ROWS ONLY
        """
        df = run_query_params(sql, {"usuario": usuario})
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")
    except Exception:
        return []


def extraer_memorias_de_conversacion(
    mensajes: list[dict],
    gemini_key: str,
    model: str = "gemini-3.5-flash",
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
            base_cfg = {"temperature": 0.1, "maxOutputTokens": 1024}
            body = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {**base_cfg, "thinkingConfig": {"thinkingBudget": 0}},
            }
            r = requests.post(url, json=body, timeout=30)
            if r.status_code == 400:
                body["generationConfig"] = base_cfg
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
        rel = m.get("relevancia", "") or "Baja"
        lineas.append(
            f"[{m.get('tipo','insight').upper()}] ({rel}) {m.get('tema','')}: {m.get('contenido','')}"
        )
    return "\n".join(lineas)
