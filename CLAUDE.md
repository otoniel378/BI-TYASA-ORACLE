# TYASA BI — Contexto para Claude Code

## Proyecto
Plataforma de Inteligencia Comercial multi-área para TYASA.
Stack: Python · Streamlit · BigQuery · Plotly · XGBoost · Statsmodels · Gemini API
GCP Project: project-d0cf2519-d089-47d3-930
Dataset BQ: tyasa_bi

## Estructura del repo
app.py                            ← Hub principal, navegación st.navigation()
config.py                         ← Colores, parámetros, rutas, áreas
core/
  db_connector.py                 ← Cliente BigQuery singleton
  validators.py                   ← Validaciones de DataFrames
  components/
    charts.py                     ← 8 tipos de gráficos Plotly (paleta TYASA)
    filters.py                    ← Filtros sidebar
    kpi_cards.py                  ← Tarjetas KPI ejecutivas
    tables.py                     ← Tablas exportables a Excel
aceros_planos/
  negros/                         ← COMPLETADO (5 módulos)
    loaders.py                    ← 12 funciones con @st.cache_data(ttl=600)
    analytics/
      kpis.py                     ← KPIResumen dataclass
      segmentacion.py             ← ABC, Pareto, HHI, Gini
      series_tiempo.py            ← Variación MoM, volatilidad, heatmap
      forecasting.py              ← ETS | SARIMA | XGBoost | Naive | Auto
      mix_productos.py            ← Co-ocurrencia, cross-sell
  galvanizados/                   ← EN DESARROLLO
  formados/                       ← EN DESARROLLO
aceros_largos/                    ← PRÓXIMO (otro equipo)
aceros_sbq/                       ← PRÓXIMO (otro equipo)
mercado_noticias/                 ← COMPLETADO
  loaders.py                      ← Variables, quiebres, noticias desde BQ
  analytics/
    detector.py                   ← Detección quiebres estructurales (Chow test)
    noticias.py                   ← Google News RSS + NewsAPI (31 variables)
    ai_analysis.py                ← Análisis IA con Gemini 2.0-flash + caché JSON
pages/
  hub.py                          ← Bienvenida con estado del proyecto
  ap_negros/01-05_*.py            ← 5 páginas completas (~62 KB)
  ap_galvanizados/coming_soon.py
  ap_formados/coming_soon.py
  aceros_largos/coming_soon.py
  aceros_sbq/coming_soon.py
  mercado/
    01_monitor.py                 ← Monitor de quiebres + alertas IA (316 líneas)
    02_variables.py               ← 31 series siderúrgicas históricas
    03_industria.py               ← Monitor siderúrgico + noticias IA (316 líneas)
scripts/
  create_market_tables.py         ← Inicialización tablas BQ (one-time)
  update_market_data.py           ← Update diario desde yfinance
cloud_functions/
  update_market/main.py           ← Cloud Function HTTP (trigger 8:45 AM MX = 14:45 UTC)

## Convenciones
- Naming tablas BQ: bronze_ | silver_ | gold_ + descripción
- Columnas clave: PESO_TON, CLIENTE, PRODUCTO_LIMPIO, PERIODO, AREA, DIVISION
- AREA_FILTER por loader: "NEGROS" | "GALVANIZADOS" | "FORMADOS"
- Paleta: primary=#1B3A5C | secondary=#4A7BA7 | success=#2E7D32 | danger=#C62828
- Todos los loaders usan @st.cache_data(ttl=600)
- BQ client usa @st.cache_resource (una sola conexión por sesión)
- Nuevas páginas siguen el patrón de pages/ap_negros/01_resumen.py
- Caché IA en cache/ai_summaries/<hash>.json (no repetir llamadas a Gemini)

## Estado actual
- Aceros Planos Negros:     ✅ COMPLETADO (5 módulos, ~62 KB)
- Mercado Global:           ✅ COMPLETADO (3 páginas, 31 variables, IA)
- Aceros Planos Galvanizados: 🚧 EN DESARROLLO
- Aceros Planos Formados:     🚧 EN DESARROLLO
- Aceros Largos:              🔜 PRÓXIMO (otro equipo)
- Aceros SBQ:                 🔜 PRÓXIMO (otro equipo)

## Tablas BigQuery activas
- silver_ventas_limpias         ← Datos completos de ventas (fuente principal)
- gold_demanda_cliente          ← Agrupado por cliente
- gold_demanda_producto         ← Agrupado por producto
- gold_demanda_mensual          ← Serie temporal mensual
- gold_cliente_producto         ← Matriz cliente × producto
- gold_demanda_proceso          ← Agrupado por proceso productivo
- gold_variables_mercado        ← 31 series siderúrgicas diarias (yfinance)
- gold_quiebres_detectados      ← Quiebres estructurales (Chow test)
- gold_noticias_vinculadas      ← Noticias enlazadas a variables

## Reglas
1. Nunca hardcodear credenciales — usar get_bq_client() y secrets.toml
2. Siempre usar table_ref() para referenciar tablas BQ
3. Nuevas páginas importan desde core/ y siguen estructura existente
4. Al agregar área nueva: actualizar config.py → AREAS y app.py → st.navigation()
5. Nuevos loaders van en aceros_planos/<subseccion>/loaders.py con AREA_FILTER propio
6. Cada página nueva tiene sidebar_header() + st.spinner() en carga de datos
7. Caché de análisis IA en JSON — nunca llamar Gemini si ya existe la respuesta

## Patrón obligatorio para HTML dinámico (FIX DEFINITIVO 2026-04-28)

USAR st.html() para cualquier HTML grande o dinámico. NUNCA st.markdown(unsafe_allow_html=True) para contenido que cambia entre renders — React intenta reconciliar los nodos DOM internos y falla con removeChild.

```python
# ✅ CORRECTO — nodo opaco, React no reconcilia
st.html(render_fn(st.session_state.get(key)))

# ❌ INCORRECTO — removeChild si el HTML cambia
st.markdown(render_fn(st.session_state.get(key)), unsafe_allow_html=True)

# ✅ OK — HTML estático que nunca cambia
st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
```

## Patrón obligatorio para llamadas IA con botón (FIX DEFINITIVO 2026-04-28)
Sin spinner, sin rerun, con st.html() para el resultado:
```python
if run and _GEMINI_KEY:
    st.session_state[key] = ai_call(...)   # bloqueante; Streamlit muestra "Running..."
# NO st.rerun(), NO st.spinner()
st.html(render_fn(st.session_state.get(key)))
```
Para chat: st.container() + procesar mensaje ANTES de renderizar, sin st.rerun().
Para controles con date_input: st.form(border=False) + st.form_submit_button().

## CSS para pill tabs en app.py (2026-04-28)
El selector broad .block-container ES el correcto para tabs. NO intentar :has() para height/flex — solo funciona para colores. El removeChild NO era del CSS, era de st.markdown con HTML dinámico.

```css
/* Area tabs 72px */
.block-container [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button {
    height: 72px !important; border-radius: 50px !important;
}
/* Module tabs override 60px */
[data-testid="stVerticalBlock"]:has(#module-tabs-marker) ~ [data-testid="stHorizontalBlock"]
  [data-testid="stButton"] > button {
    height: 60px !important;
}
```

## Notas de sesiones
Las notas de cada sesión se guardan en:
C:\Users\OTONIEL\Desktop\obsidian\sesiones\
Plantilla: templates/sesion-claude.md
Última sesión: 2026-04-28 — Rediseño Power BI + Fix removeChild definitivo

## Regla de documentación en Obsidian
Cuando el usuario pida "anota esto en Obsidian" o "actualiza Obsidian" al final de una tarea:
1. Crear o actualizar C:\Users\OTONIEL\Desktop\obsidian\sesiones\YYYY-MM-DD-<tema>.md
2. Actualizar la sección correspondiente en C:\Users\OTONIEL\Desktop\obsidian\proyectos\bi-principal.md
   - Módulos completados / en desarrollo
   - Tablas BQ nuevas
   - Decisiones arquitectónicas nuevas
   - Log de sesiones
3. Si hay una nueva tabla BQ, decisión de arquitectura o módulo nuevo → reflejar en este CLAUDE.md también
