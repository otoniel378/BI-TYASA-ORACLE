"""
chat_ia.py — Motor de chat conversacional con datos de TYASA BI.
Herramientas: SQL · Noticias · Precios de mercado · Ejecución de análisis del sistema.
"""

from __future__ import annotations
import re
from datetime import date
import pandas as pd
from core.db_connector import run_query

_PROJECT = "project-d0cf2519-d089-47d3-930"
_DATASET = "tyasa_bi"

_SCHEMA = """
Tablas en BigQuery (proyecto: project-d0cf2519-d089-47d3-930, dataset: tyasa_bi):

1. silver_ventas_limpias — Ventas detalladas
   PERIODO DATE, CLIENTE STRING, PRODUCTO_LIMPIO STRING, AREA STRING,
   DIVISION STRING, PESO_TON FLOAT64, IMPORTE_MXN FLOAT64
   AREA: 'NEGROS' | 'GALVANIZADOS' | 'FORMADOS'

2. gold_demanda_mensual — Serie mensual de ventas
   PERIODO DATE, AREA STRING, PESO_TON FLOAT64, IMPORTE_MXN FLOAT64,
   N_CLIENTES INT64, N_PRODUCTOS INT64

3. gold_demanda_cliente — Agrupado por cliente
   CLIENTE STRING, AREA STRING, PESO_TON FLOAT64, IMPORTE_MXN FLOAT64,
   N_PEDIDOS INT64, ULTIMA_COMPRA DATE

4. gold_demanda_producto — Agrupado por producto
   PRODUCTO_LIMPIO STRING, AREA STRING, PESO_TON FLOAT64,
   IMPORTE_MXN FLOAT64, N_CLIENTES INT64

5. gold_variables_mercado — Variables de mercado diarias (31 series)
   fecha DATE, ticker STRING, nombre STRING, categoria STRING, valor FLOAT64

6. gold_sentimiento_noticias — Sentimiento IA de noticias
   hash_url STRING, fecha_pub DATE, titulo STRING, fuente STRING,
   sentimiento STRING, score FLOAT64, variable_principal STRING,
   señal STRING, razon STRING, confianza STRING

7. gold_quiebres_detectados — Quiebres estructurales (Chow test)
   ticker STRING, nombre STRING, categoria STRING, fecha_corte DATE,
   fecha_detect DATE, cambio_pct FLOAT64, activo BOOL,
   F_stat FLOAT64, p_value FLOAT64, media_pre FLOAT64, media_post FLOAT64

8. gold_memoria_ia — Insights guardados del asistente IA
   id_memoria STRING, fecha DATE, tipo STRING, tema STRING,
   contenido STRING, relevancia STRING
"""

_SYSTEM = f"""Eres el asistente inteligente de TYASA BI. TYASA es una acería mexicana que produce \
acero plano (HRC, CRC, galvanizado) con horno eléctrico de arco (EAF).

CAPACIDADES:
1. ejecutar_sql — Consultas SELECT a BigQuery (datos históricos de ventas, mercado, etc.)
2. buscar_noticias — Google News en tiempo real (mañaneras, aranceles, precios globales)
3. obtener_precios_mercado — Precios recientes de BigQuery (HRC, chatarra, USD/MXN, etc.)
4. ejecutar_analisis — Corre análisis del sistema TYASA:
   • mananera → transcribe y analiza la conferencia presidencial de hoy con IA
   • quiebres_mercado → detecta cambios estructurales activos en precios
   • kpis_ventas → resumen ejecutivo de ventas por área
   • sentimiento_noticias → índice de sentimiento del sector siderúrgico

REGLAS:
- Solo SELECT en SQL. Nunca INSERT/UPDATE/DELETE/DROP
- Responde siempre en español, con insights accionables para TYASA
- Cuando el usuario pida "corre", "analiza", "ejecuta" o "dame los datos de" → usa ejecutar_analisis
- Cuando pregunten sobre la presidenta, mañanera o conferencia → usa ejecutar_analisis(mananera) Y buscar_noticias
- PESO_TON es el volumen de ventas (métrica principal)
- EAF usa chatarra como insumo principal → SCRAP_HMS impacta directamente los costos
- HRC_FUTURES es el precio de referencia internacional del acero plano

CONTEXTO DEL NEGOCIO:
- Clientes NEGROS: automotriz, construcción, manufactura, electrodomésticos
- Competencia: Ternium MX + importaciones chinas (dumping)
- Riesgo principal: chatarra cara + dumping chino + alza energía eléctrica
- Oportunidad: nearshoring, infraestructura gobierno, T-MEC

Esquema de tablas:
{_SCHEMA}"""

# ── Declaraciones de herramientas ─────────────────────────────────────────────
_TOOLS_DECL = [
    {
        "name": "ejecutar_sql",
        "description": (
            "Ejecuta una consulta SQL SELECT en BigQuery de TYASA BI. "
            "Usa para datos históricos de ventas, clientes, productos y mercado."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql":    {"type": "string", "description": "Consulta SQL SELECT válida para BigQuery."},
                "titulo": {"type": "string", "description": "Título breve de la consulta."},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "buscar_noticias",
        "description": (
            "Busca noticias recientes en Google News. "
            "Úsala para eventos actuales: mañaneras presidenciales, aranceles, "
            "precios de materias primas, política comercial, mercado del acero."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query":          {"type": "string", "description": "Término de búsqueda."},
                "max_resultados": {"type": "integer", "description": "Número de noticias (1-8). Default: 5."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "obtener_precios_mercado",
        "description": (
            "Obtiene precios recientes de variables siderúrgicas desde BigQuery. "
            "Usa para preguntas sobre HRC, chatarra, zinc, USD/MXN y otras commodities."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "variable": {"type": "string", "description": "Nombre de variable. Ej: HRC_FUTURES, SCRAP_HMS. Vacío = todas."},
                "dias":     {"type": "integer", "description": "Días hacia atrás (1-60). Default: 14."},
            },
            "required": [],
        },
    },
    {
        "name": "ejecutar_analisis",
        "description": (
            "Ejecuta análisis del sistema TYASA BI directamente. "
            "Usa cuando el usuario pida 'correr', 'analizar', 'ejecutar' o 'dame resultados de'. "
            "Opciones: mananera (conferencia presidencial con IA), "
            "quiebres_mercado (cambios estructurales en precios activos), "
            "kpis_ventas (resumen ejecutivo de ventas), "
            "sentimiento_noticias (índice de sentimiento siderúrgico)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analisis": {
                    "type": "string",
                    "enum": ["mananera", "quiebres_mercado", "kpis_ventas", "sentimiento_noticias"],
                    "description": "Tipo de análisis a ejecutar.",
                },
                "area":  {"type": "string", "description": "Para kpis_ventas: NEGROS, GALVANIZADOS o FORMADOS."},
                "fecha": {"type": "string", "description": "Para mananera: YYYY-MM-DD. Default: hoy."},
                "dias":  {"type": "integer", "description": "Para sentimiento_noticias: días hacia atrás. Default: 7."},
            },
            "required": ["analisis"],
        },
    },
]

PREGUNTAS_SUGERIDAS = [
    "¿Cuáles son los 10 clientes con mayor volumen en Aceros Negros este año?",
    "¿Cómo ha evolucionado el volumen mensual de ventas en los últimos 12 meses?",
    "Corre el análisis de la mañanera de hoy y dame los puntos clave",
    "Analiza los quiebres de mercado activos y su impacto en TYASA",
    "¿Cómo están los precios del HRC y chatarra esta semana?",
    "¿Qué clientes no han comprado en los últimos 60 días?",
]


# ── Implementaciones de herramientas ──────────────────────────────────────────
def _es_select_seguro(sql: str) -> bool:
    clean = re.sub(r"--[^\n]*", "", sql)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)
    first = clean.strip().split()[0].upper() if clean.strip() else ""
    return first == "SELECT"


def _tool_ejecutar_sql(args: dict) -> dict:
    sql    = args.get("sql", "").strip()
    titulo = args.get("titulo", "Consulta SQL")
    if not sql:
        return {"error": "SQL vacío."}
    if not _es_select_seguro(sql):
        return {"error": "Solo SELECT permitido.", "sql": sql}
    try:
        df = run_query(sql)
        return {
            "titulo":   titulo,
            "sql":      sql,
            "filas":    len(df),
            "columnas": list(df.columns),
            "datos":    df.head(50).to_dict(orient="records"),
            "_df":      df,
        }
    except Exception as e:
        return {"error": str(e), "sql": sql}


def _buscar_noticias_rss(query: str, max_resultados: int = 5) -> list[dict]:
    import requests
    from urllib.parse import quote_plus
    import xml.etree.ElementTree as ET

    url = (
        f"https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=es-419&gl=MX&ceid=MX:es-419"
    )
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            return []
        root  = ET.fromstring(r.content)
        items = root.findall(".//item")[:max_resultados]
        noticias = []
        for item in items:
            pub = item.findtext("pubDate") or ""
            src = item.find("source")
            noticias.append({
                "titulo":  item.findtext("title") or "",
                "fuente":  (src.text if src is not None else ""),
                "fecha":   pub[:22] if pub else "",
                "url":     item.findtext("link") or "",
                "resumen": (item.findtext("description") or "")[:200],
            })
        return noticias
    except Exception as e:
        return [{"error": str(e)}]


def _tool_buscar_noticias(args: dict) -> dict:
    query = args.get("query", "")
    max_r = min(int(args.get("max_resultados", 5)), 8)
    return {
        "query":    query,
        "noticias": _buscar_noticias_rss(query, max_r),
    }


def _tool_obtener_precios_mercado(args: dict) -> dict:
    variable = (args.get("variable") or "").strip()
    dias     = min(int(args.get("dias", 14)), 60)
    where    = f"AND nombre = '{variable}'" if variable else ""
    sql = f"""
        SELECT nombre, categoria, valor, fecha
        FROM `{_PROJECT}.{_DATASET}.gold_variables_mercado`
        WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL {dias} DAY)
        {where}
        ORDER BY nombre, fecha DESC
        LIMIT 200
    """
    try:
        df = run_query(sql)
        return {
            "variable": variable or "todas",
            "dias":     dias,
            "filas":    len(df),
            "datos":    df.to_dict(orient="records"),
            "_df":      df,
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_ejecutar_analisis(args: dict, gemini_key: str = "") -> dict:
    analisis = args.get("analisis", "")
    resultado_base = {"analisis": analisis, "ejecutado": True}

    # ── Mañanera presidencial ─────────────────────────────────────────────────
    if analisis == "mananera":
        if not gemini_key:
            return {**resultado_base, "error": "GEMINI_API_KEY requerida para analizar la mañanera."}
        fecha = args.get("fecha") or date.today().isoformat()
        try:
            from mercado_noticias.analytics.mananera import analizar_mananera
            data = analizar_mananera(gemini_key, fecha)
            if data.get("_error"):
                return {**resultado_base, "fecha": fecha, "error": data["_error"]}
            if not data.get("tiene_contenido_relevante"):
                return {**resultado_base, "fecha": fecha,
                        "nota": "La conferencia no contiene información relevante para TYASA."}
            return {
                **resultado_base,
                "fecha":              fecha,
                "resumen_ejecutivo":  data.get("resumen_ejecutivo", []),
                "impactos_tyasa":     [i.get("punto", "") for i in data.get("analisis_impacto", [])],
                "insight_estrategico":data.get("insight_estrategico", ""),
                "recomendacion":      data.get("recomendacion", ""),
                "alertas":            [a.get("descripcion", str(a)) for a in data.get("alertas_criticas", [])],
            }
        except Exception as e:
            return {**resultado_base, "error": str(e)}

    # ── Quiebres estructurales de mercado ────────────────────────────────────
    elif analisis == "quiebres_mercado":
        try:
            from mercado_noticias.loaders import load_quiebres_activos
            df = load_quiebres_activos()
            if df.empty:
                return {**resultado_base, "total": 0, "quiebres": [],
                        "nota": "No hay quiebres activos en este momento."}
            records = []
            for _, row in df.head(15).iterrows():
                records.append({
                    "nombre":     str(row.get("nombre", "")),
                    "categoria":  str(row.get("categoria", "")),
                    "cambio_pct": round(float(row.get("cambio_pct", 0)), 2),
                    "fecha_corte":str(row.get("fecha_corte", ""))[:10],
                    "media_pre":  round(float(row.get("media_pre", 0)), 2),
                    "media_post": round(float(row.get("media_post", 0)), 2),
                    "p_value":    round(float(row.get("p_value", 1)), 4),
                })
            return {**resultado_base, "total": len(df), "quiebres": records}
        except Exception as e:
            return {**resultado_base, "error": str(e)}

    # ── KPIs de ventas ────────────────────────────────────────────────────────
    elif analisis == "kpis_ventas":
        area = (args.get("area") or "NEGROS").upper()
        try:
            from aceros_planos.negros.loaders import (
                load_gold_demanda_cliente,
                load_gold_demanda_producto,
                load_gold_demanda_mensual,
            )
            from aceros_planos.negros.analytics.kpis import calcular_kpis_resumen
            df_c = load_gold_demanda_cliente()
            df_p = load_gold_demanda_producto()
            df_m = load_gold_demanda_mensual()
            kpis = calcular_kpis_resumen(df_c, df_p, df_m)
            return {
                **resultado_base,
                "area":              area,
                "toneladas_totales": round(float(kpis.toneladas_totales or 0), 1),
                "clientes_activos":  int(kpis.clientes_activos or 0),
                "productos_activos": int(kpis.productos_activos or 0),
                "ticket_promedio":   round(float(kpis.ticket_promedio or 0), 1),
                "variacion_mom_pct": round(float(kpis.variacion_mom or 0), 1),
                "top_cliente":       kpis.top_cliente or "",
                "top_producto":      kpis.top_producto or "",
            }
        except Exception as e:
            return {**resultado_base, "error": str(e)}

    # ── Sentimiento de noticias ───────────────────────────────────────────────
    elif analisis == "sentimiento_noticias":
        dias = int(args.get("dias", 7))
        try:
            from mercado_noticias.loaders import load_sentimiento_noticias
            df = load_sentimiento_noticias(dias=dias)
            if df.empty:
                return {**resultado_base, "dias": dias, "total": 0,
                        "nota": "Sin datos de sentimiento. Ejecuta update_sentimiento_noticias.py primero."}
            n_pos = int((df["sentimiento"] == "positivo").sum())
            n_neg = int((df["sentimiento"] == "negativo").sum())
            n_neu = int((df["sentimiento"] == "neutro").sum())
            score  = float(df["score"].mean()) if "score" in df.columns else 0.0
            nivel  = "Favorable" if score >= 0.2 else "Adverso" if score <= -0.2 else "Neutro"
            top    = df.head(6)[["titulo", "sentimiento", "score", "variable_principal", "razon"]].to_dict(orient="records")
            return {
                **resultado_base,
                "dias":                dias,
                "total_noticias":      len(df),
                "positivas":           n_pos,
                "negativas":           n_neg,
                "neutras":             n_neu,
                "score_promedio":      round(score, 3),
                "nivel":               nivel,
                "noticias_destacadas": top,
            }
        except Exception as e:
            return {**resultado_base, "error": str(e)}

    return {**resultado_base, "error": f"Análisis no reconocido: {analisis}"}


def ejecutar_herramienta(nombre: str, args: dict, gemini_key: str = "") -> dict:
    if nombre == "ejecutar_sql":
        return _tool_ejecutar_sql(args)
    if nombre == "buscar_noticias":
        return _tool_buscar_noticias(args)
    if nombre == "obtener_precios_mercado":
        return _tool_obtener_precios_mercado(args)
    if nombre == "ejecutar_analisis":
        return _tool_ejecutar_analisis(args, gemini_key=gemini_key)
    return {"error": f"Herramienta desconocida: {nombre}"}


# ── Motor principal ────────────────────────────────────────────────────────────
def chat_turno(
    historial: list[dict],
    gemini_key: str,
    model: str = "gemini-2.5-flash",
    contexto_previo: str = "",
) -> dict:
    try:
        from google import genai
        from google.genai import types as T

        client     = genai.Client(api_key=gemini_key)
        system_txt = _SYSTEM + (f"\n\n{contexto_previo}" if contexto_previo else "")

        tool = T.Tool(function_declarations=_TOOLS_DECL)
        cfg  = T.GenerateContentConfig(
            system_instruction=system_txt,
            tools=[tool],
            tool_config=T.ToolConfig(
                function_calling_config=T.FunctionCallingConfig(mode="AUTO")
            ),
            temperature=0.15,
            max_output_tokens=2048,
            thinking_config=T.ThinkingConfig(thinking_budget=0),
        )

        contents          = _historial_a_contents(historial)
        herramientas_used: list[dict] = []
        max_iter          = 8

        for _ in range(max_iter):
            resp      = client.models.generate_content(model=model, contents=contents, config=cfg)
            parts_out = resp.candidates[0].content.parts

            calls = [p for p in parts_out if hasattr(p, "function_call") and p.function_call]
            if not calls:
                texto = "".join(p.text for p in parts_out if hasattr(p, "text") and p.text)
                return {"respuesta": texto.strip(), "herramientas": herramientas_used, "error": None}

            model_parts_dict = []
            for p in parts_out:
                if hasattr(p, "function_call") and p.function_call:
                    model_parts_dict.append({
                        "function_call": {
                            "name": p.function_call.name,
                            "args": dict(p.function_call.args),
                        }
                    })
                elif hasattr(p, "text") and p.text:
                    model_parts_dict.append({"text": p.text})
            contents.append({"role": "model", "parts": model_parts_dict})

            tool_parts = []
            for p in calls:
                fc        = p.function_call
                resultado = ejecutar_herramienta(fc.name, dict(fc.args), gemini_key=gemini_key)

                h_entry = {
                    "herramienta": fc.name,
                    "titulo":   resultado.get("titulo", fc.name),
                    "sql":      resultado.get("sql", ""),
                    "filas":    resultado.get("filas", 0),
                    "noticias": resultado.get("noticias", []),
                    "analisis": resultado.get("analisis", ""),
                    "error":    resultado.get("error"),
                    "_df":      resultado.get("_df"),
                    "_resultado_completo": {k: v for k, v in resultado.items() if not k.startswith("_")},
                }
                herramientas_used.append(h_entry)

                resp_data = {k: v for k, v in resultado.items() if not k.startswith("_")}
                if "datos" in resp_data and isinstance(resp_data["datos"], list) and len(resp_data["datos"]) > 25:
                    resp_data["datos"] = resp_data["datos"][:25]
                    resp_data["nota"]  = f"Primeras 25 de {resultado.get('filas','?')} filas"

                tool_parts.append({
                    "function_response": {"name": fc.name, "response": resp_data}
                })

            contents.append({"role": "user", "parts": tool_parts})

        return {
            "respuesta":    "No pude completar la respuesta en el límite de iteraciones.",
            "herramientas": herramientas_used,
            "error":        "max_iter",
        }

    except ImportError:
        return _chat_turno_rest(historial, gemini_key, model, contexto_previo)
    except Exception as e:
        return {"respuesta": "", "herramientas": [], "error": str(e)}


def _historial_a_contents(historial: list[dict]) -> list:
    contents = []
    for msg in historial:
        parts = [{"text": p} for p in msg.get("parts", []) if isinstance(p, str)]
        if parts:
            contents.append({"role": msg["role"], "parts": parts})
    return contents


def _chat_turno_rest(historial, gemini_key, model, contexto_previo="") -> dict:
    import requests
    system_txt = _SYSTEM + (f"\n\n{contexto_previo}" if contexto_previo else "")
    url        = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={gemini_key}"
    )
    messages = [
        {"role": m["role"], "parts": [{"text": p}]}
        for m in historial
        for p in m.get("parts", [])
        if isinstance(p, str)
    ]
    body = {
        "system_instruction": {"parts": [{"text": system_txt}]},
        "contents": messages,
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": 2048},
    }
    try:
        r = requests.post(url, json=body, timeout=90)
        if r.status_code == 200:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return {"respuesta": text.strip(), "herramientas": [], "error": None}
        return {"respuesta": "", "herramientas": [], "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"respuesta": "", "herramientas": [], "error": str(e)}
