"""
chat_ia.py — Motor de chat conversacional con datos de TYASA BI.
Herramientas: SQL · Noticias · Precios de mercado · Ejecución de análisis del sistema.
"""

from __future__ import annotations
import re
from datetime import date
import pandas as pd
from core.db_connector import run_query, run_query_params, table_ref
from core import metricas

_SCHEMA = """
Tablas en Oracle Autonomous Data Warehouse (schema ADMIN; nombres en MAYÚSCULAS):

1. SILVER_VENTAS_LIMPIAS — Ventas detalladas (un registro por bobina o paquete embarcado)
   FECHAEMB DATE, CLIENTE VARCHAR2, PRODUCTO_ORIGINAL VARCHAR2, PRODUCTO_LIMPIO VARCHAR2,
   PROCESO VARCHAR2, CALIBRE NUMBER, ANCHO NUMBER, PESO_KG NUMBER, PESO_TON NUMBER,
   COLADA VARCHAR2, PIEZAS NUMBER, ANIO NUMBER, MES NUMBER, PERIODO DATE,
   AREA VARCHAR2 ('NEGROS' | 'GALVANIZADOS' | 'FORMADOS'), DIVISION VARCHAR2 ('PLANOS')

2. GOLD_DEMANDA_MENSUAL — Serie mensual de ventas
   PERIODO DATE, ANIO NUMBER, MES NUMBER, PRODUCTO_LIMPIO VARCHAR2, AREA VARCHAR2,
   DIVISION VARCHAR2, PESO_TON NUMBER, N_CLIENTES NUMBER, N_EMBARQUES NUMBER

3. GOLD_DEMANDA_CLIENTE — Agrupado por cliente
   CLIENTE VARCHAR2, AREA VARCHAR2, DIVISION VARCHAR2, PESO_TON NUMBER, N_EMBARQUES NUMBER,
   PRIMERA_COMPRA DATE, ULTIMA_COMPRA DATE

4. GOLD_DEMANDA_PRODUCTO — Agrupado por producto
   PRODUCTO_LIMPIO VARCHAR2, AREA VARCHAR2, DIVISION VARCHAR2, PESO_TON NUMBER, N_CLIENTES NUMBER

5. GOLD_DEMANDA_PROCESO — Agrupado por proceso productivo
   PROCESO VARCHAR2, AREA VARCHAR2, DIVISION VARCHAR2, PESO_TON NUMBER, N_CLIENTES NUMBER, N_EMBARQUES NUMBER

6. GOLD_CLIENTE_PRODUCTO — Matriz cliente × producto
   CLIENTE VARCHAR2, PRODUCTO_LIMPIO VARCHAR2, AREA VARCHAR2, DIVISION VARCHAR2, PESO_TON NUMBER, N_EMBARQUES NUMBER

7. GOLD_VARIABLES_MERCADO — Variables de mercado diarias (35 series)
   FECHA DATE, TICKER VARCHAR2, NOMBRE VARCHAR2, CATEGORIA VARCHAR2, VALOR NUMBER
   Ejemplos de NOMBRE: HRC_CME_USD (bobina laminada en caliente), USD_MXN, Mineral_Hierro, Zinc_USD,
   Ternium_MX, ArcelorMittal, Brent_USD, Gas_HenryHub_USD, VIX, SP500.

8. GOLD_QUIEBRES_DETECTADOS — Quiebres estructurales en variables de mercado
   ID VARCHAR2, VARIABLE VARCHAR2, CATEGORIA VARCHAR2, FECHA_CORTE DATE, FECHA_DETECT DATE,
   F_STAT NUMBER, P_VALUE NUMBER, SIGMA NUMBER, CAMBIO_PCT NUMBER, MEDIA_PRE NUMBER,
   MEDIA_POST NUMBER, SEVERIDAD VARCHAR2, ACTIVO NUMBER (1 = activo)

9. GOLD_SENTIMIENTO_NOTICIAS — Noticias del sector clasificadas
   ID VARCHAR2, TITULO VARCHAR2, FUENTE VARCHAR2, URL VARCHAR2, FECHA_PUB DATE,
   SENTIMIENTO VARCHAR2, SCORE NUMBER, VARIABLE_PRINCIPAL VARCHAR2, CATEGORIA VARCHAR2, RAZON VARCHAR2

10. GOLD_INDICADORES_INEGI — Indicadores económicos del INEGI
    CLAVE VARCHAR2, NOMBRE VARCHAR2, FECHA VARCHAR2, VALOR NUMBER

11. GOLD_SNICE_RESUMEN_MENSUAL — Avisos automáticos de importación siderúrgica (SNICE)
    PERIODO VARCHAR2, VOLUMEN_TOTAL NUMBER, AVISOS_TOTAL NUMBER, EMPRESAS_DISTINTAS NUMBER,
    PAISES_DISTINTOS NUMBER, FRACCIONES_DISTINTAS NUMBER

12. GOLD_PRECIOS_FASTMARKETS — Precios de ferroaleaciones
    SIMBOLO VARCHAR2, DESCRIPCION VARCHAR2, FECHA DATE, VALOR NUMBER, MONEDA VARCHAR2, UNIDAD VARCHAR2

13. GOLD_SEMAFORO_FERROS — Semáforo de alzas de ferroaleaciones
    SERIE VARCHAR2, FECHA DATE, TIPO VARCHAR2 ('actual' | 'backtest'), PROB NUMBER, SEMAFORO VARCHAR2
"""

_GLOSARIO = "\n".join(f"- {r['Métrica']} ({r['Clave']}): {r['Qué significa']}"
                      for _, r in metricas.glosario().iterrows())

_SYSTEM = f"""Eres el asistente inteligente de TYASA BI, la plataforma de inteligencia comercial de \
TYASA, siderúrgica mexicana con tres divisiones: Aceros Planos (Negros, Galvanizados y Formados), \
Aceros Largos y Aceros SBQ. Hoy la base de ventas contiene solo Aceros Planos Negros.

CAPACIDADES:
0. consultar_metrica — Cifras oficiales de ventas (toneladas, clientes, productos…) con las
   definiciones del catálogo. Úsala primero para cualquier cifra de ventas.
1. ejecutar_sql — Consultas SELECT a Oracle (lo que no cubra consultar_metrica: mercado, SNICE, noticias…)
2. buscar_noticias — Google News en tiempo real (mañaneras, aranceles, precios globales)
3. obtener_precios_mercado — Precios recientes de las variables de mercado (HRC, USD/MXN, metales, energía…)
4. ejecutar_analisis — Corre análisis del sistema TYASA:
   • mananera: transcribe y analiza la conferencia presidencial de hoy con IA
   • quiebres_mercado: detecta cambios estructurales activos en precios
   • kpis_ventas: resumen ejecutivo de ventas por área
   • sentimiento_noticias: índice de sentimiento del sector siderúrgico

REGLAS:
- Solo SELECT en SQL. Nunca INSERT/UPDATE/DELETE/DROP
- SQL de Oracle: sin comillas invertidas ni punto y coma final; límites con FETCH FIRST n ROWS ONLY;
  fechas con TRUNC(SYSDATE), ADD_MONTHS(fecha, n), fecha - n (días); TO_CHAR para formatear
- La última fecha de ventas cargada es MAX(FECHAEMB) de SILVER_VENTAS_LIMPIAS: úsala como "hoy"
  para recencia de clientes (los datos de SAP pueden tener desfase)
- Responde siempre en español, con insights accionables para TYASA
- Responde solo con los datos que devuelven las herramientas; no inventes cifras
- Cuando el usuario pida "corre", "analiza", "ejecuta" o "dame los datos de", usa ejecutar_analisis
- Cuando pregunten sobre la presidenta, mañanera o conferencia, usa ejecutar_analisis(mananera) Y buscar_noticias
- PESO_TON es el volumen de ventas (métrica principal)
- Para cifras de ventas usa consultar_metrica; usa ejecutar_sql con ventas solo si la pregunta no cabe
  en una métrica y, si lo haces, respeta las definiciones de abajo
- Al comparar meses usa solo meses completos (el último mes cargado puede estar a medias)
- HRC_CME_USD es el precio de referencia internacional del acero plano (bobina laminada en caliente)

CONTEXTO DEL NEGOCIO:
- Clientes de Aceros Planos Negros: automotriz, construcción, manufactura, electrodomésticos
- Competencia: Ternium MX + importaciones (ver avisos del SNICE)
- Riesgos: precio internacional del acero, importaciones, alza de energía e insumos (ferroaleaciones)
- Oportunidad: nearshoring, infraestructura gobierno, T-MEC

MÉTRICAS OFICIALES (catálogo; dilo así al usuario):
{_GLOSARIO}

Esquema de tablas:
{_SCHEMA}"""

# ── Declaraciones de herramientas ─────────────────────────────────────────────
_TOOLS_DECL = [
    {
        "name": "consultar_metrica",
        "description": (
            "Cifras oficiales de ventas de TYASA BI con las definiciones del catálogo. Úsala antes que "
            "ejecutar_sql para toneladas, clientes, productos, piezas o toneladas por cliente, en total o "
            "desglosadas por cliente, producto, proceso, mes o año. clientes_activos = compra en los "
            "últimos 90 días a la fecha de corte (ignora desde/hasta/por)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metrica":  {"type": "string", "enum": list(metricas.METRICAS) + ["clientes_activos"]},
                "desde":    {"type": "string", "description": "Fecha inicial YYYY-MM-DD (incluida). Vacío = desde el inicio."},
                "hasta":    {"type": "string", "description": "Fecha final YYYY-MM-DD (incluida). Vacío = fecha de corte."},
                "por":      {"type": "string", "enum": list(metricas.DIMENSIONES), "description": "Desglose opcional."},
                "filtro_dimension": {"type": "string", "enum": list(metricas.DIMENSIONES)},
                "filtro_valor":     {"type": "string", "description": "Valor exacto para filtro_dimension (p. ej. un cliente)."},
                "top":      {"type": "integer", "description": "Máximo de filas al desglosar (default 20)."},
                "area":     {"type": "string", "description": "NEGROS (default), GALVANIZADOS o FORMADOS."},
            },
            "required": ["metrica"],
        },
    },
    {
        "name": "ejecutar_sql",
        "description": (
            "Ejecuta una consulta SQL SELECT en Oracle (TYASA BI). "
            "Usa para datos históricos de ventas, clientes, productos y mercado."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql":    {"type": "string", "description": "Consulta SQL SELECT válida para Oracle (sin punto y coma)."},
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
            "Obtiene precios recientes de las variables de mercado (tabla GOLD_VARIABLES_MERCADO). "
            "Usa para preguntas sobre HRC, mineral de hierro, zinc, USD/MXN, energía y otras commodities."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "variable": {"type": "string", "description": "Nombre (o parte del nombre) de la variable. Ej: HRC_CME_USD, USD_MXN, Zinc. Vacío = todas."},
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
    sql    = args.get("sql", "").strip().rstrip(";").strip()   # Oracle rechaza el ';' final
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


def _tool_consultar_metrica(args: dict) -> dict:
    metrica = args.get("metrica", "")
    area = (args.get("area") or "NEGROS").upper()
    try:
        corte = metricas.fecha_corte(area)
        if metrica == "clientes_activos":
            return {"metrica": "Clientes activos", "fecha_corte": str(corte.date()),
                    "valor": metricas.clientes_activos(area),
                    "definicion": f"Compra en los últimos {metricas.DIAS_CLIENTE_ACTIVO} días a la fecha de corte."}
        if metrica not in metricas.METRICAS:
            return {"error": f"Métrica desconocida: {metrica}. Opciones: {list(metricas.METRICAS)}"}
        por = args.get("por") or None
        if por is not None and por not in metricas.DIMENSIONES:
            return {"error": f"Dimensión desconocida: {por}"}
        filtros = ({args["filtro_dimension"]: args["filtro_valor"]}
                   if args.get("filtro_dimension") in metricas.DIMENSIONES and args.get("filtro_valor") else None)
        df = metricas.calcular(metrica, args.get("desde") or None, args.get("hasta") or None, por=por, area=area,
                               filtros=filtros, top=min(int(args.get("top") or 20), 100) if por else None)
        m = metricas.METRICAS[metrica]
        datos = df.round(2)
        for c in datos.columns:
            if c != "VALOR":
                datos[c] = datos[c].astype(str)
        return {
            "metrica": m.nombre, "definicion": m.descripcion, "unidad": m.unidad,
            "fecha_corte": str(corte.date()),
            "ultimo_mes_completo": f"{metricas.ultimo_mes_completo(corte):%Y-%m}",
            "filas": len(df), "datos": datos.to_dict(orient="records"),
            "_df": df,
        }
    except Exception as e:
        return {"error": str(e)}


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
    dias     = max(1, min(int(args.get("dias", 14) or 14), 60))
    params: dict = {"dias": dias}
    where = ""
    if variable:
        where = "AND (UPPER(NOMBRE) LIKE :var OR UPPER(TICKER) LIKE :var)"
        params["var"] = f"%{variable.upper()}%"
    sql = f"""
        SELECT NOMBRE, CATEGORIA, VALOR, FECHA
        FROM {table_ref('GOLD_VARIABLES_MERCADO')}
        WHERE FECHA >= TRUNC(SYSDATE) - :dias
        {where}
        ORDER BY NOMBRE, FECHA DESC
        FETCH FIRST 200 ROWS ONLY
    """
    try:
        df = run_query_params(sql, params)
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
            corte = metricas.fecha_corte(area)
            inicio_anio = corte.replace(month=1, day=1)
            var_m = metricas.variacion("toneladas", "mes_anterior", area=area)
            var_a = metricas.variacion("toneladas", "anio_anterior", area=area)
            top = metricas.calcular("toneladas", inicio_anio, corte, por="cliente", area=area, top=5)
            _pct = lambda v: round(v, 1) if v is not None else None  # noqa: E731
            return {
                **resultado_base,
                "area":                         area,
                "fecha_corte":                  str(corte.date()),
                "toneladas_anio_en_curso":      round(metricas.valor("toneladas", inicio_anio, corte, area), 1),
                "toneladas_historico":          round(metricas.valor("toneladas", area=area), 1),
                "clientes_activos_90d":         metricas.clientes_activos(area),
                "clientes_con_compra_anio":     int(metricas.valor("clientes_con_compra", inicio_anio, corte, area)),
                "ultimo_mes_completo":          f"{var_m['mes']:%Y-%m}",
                "toneladas_ultimo_mes":         round(var_m["actual"], 1),
                "variacion_vs_mes_anterior_pct": _pct(var_m["pct"]),
                "variacion_vs_mismo_mes_anio_anterior_pct": _pct(var_a["pct"]),
                "top_clientes_anio":            top.round(1).to_dict(orient="records"),
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
    if nombre == "consultar_metrica":
        return _tool_consultar_metrica(args)
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
    model: str = "gemini-3.5-flash",
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
    base_cfg = {"temperature": 0.15, "maxOutputTokens": 2048}
    body = {
        "system_instruction": {"parts": [{"text": system_txt}]},
        "contents": messages,
        # Sin thinkingBudget:0 el modelo gasta maxOutputTokens "pensando" antes
        # de responder y el texto visible sale vacío o truncado (ver sentimiento.py).
        "generationConfig": {**base_cfg, "thinkingConfig": {"thinkingBudget": 0}},
    }
    try:
        r = requests.post(url, json=body, timeout=90)
        if r.status_code == 400:
            body["generationConfig"] = base_cfg
            r = requests.post(url, json=body, timeout=90)
        if r.status_code == 200:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return {"respuesta": text.strip(), "herramientas": [], "error": None}
        return {"respuesta": "", "herramientas": [], "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"respuesta": "", "herramientas": [], "error": str(e)}
