# TYASA BI — Contexto para Claude Code
Última actualización: 2026-11-13

## Proyecto
Plataforma de Inteligencia Comercial de la Dirección Comercial de TYASA.
TYASA tiene **solo tres divisiones / áreas de producto**: Aceros Planos, Aceros Largos y Aceros SBQ.
Mercado Global es una **sección común** a las tres (no es una división).
Stack: Python · Streamlit · Oracle Autonomous Data Warehouse · Plotly · statsmodels · XGBoost · scikit-learn ·
sentence-transformers · Gemini API · GitHub Actions.
Base de datos: **solo Oracle ADW** (región México-Querétaro, Always Free), schema ADMIN. Migrado desde BigQuery en jun 2026;
BigQuery ya no se usa (el asistente IA y su memoria ya están en Oracle desde 2026-11-13). El código obsoleto de BigQuery
se borró el 2026-11-24; solo Aceros Largos (equipo de Largos) sigue usando `get_bq_client` y por eso falla hasta que lo migren.
Autoría: la plataforma común y Aceros Planos los desarrolla Otoniel; Largos y SBQ los adecuarán sus compañeros.

## Estructura del repo
```
app.py                       ← Hub, login, navegación por sección (aceros_planos | aceros_largos | aceros_sbq | mercado)
config.py                    ← Colores, parámetros, AREAS (responsable y estado por división)
core/
  db_connector.py            ← Oracle ADW (wallet; secrets.toml / ORACLE_WALLET_B64 / env). run_query, run_query_params, table_ref
  auth.py                    ← Roles: director, gerente (todas las secciones) · esp_negros, esp_largos, esp_sbq (tablero de su división)
  forecasting.py             ← Motor de pronóstico común (ETS|SARIMA|XGBoost|Naive|Combo|Auto, origen móvil):
                               lo usan Aceros Planos y Mercado Global (importación CANACERO)
  metricas.py                ← Catálogo único de métricas de ventas (definición, unidad, SQL), umbrales de cliente,
                               meses completos; lo usan páginas y el asistente IA (herramienta consultar_metrica)
  seleccion_modelos.py       ← Modelo del modo Automático por serie (GOLD_SELECCION_MODELO)
  alertas.py                 ← Bandeja única de alertas (ventas, clientes, DOF, semáforo, quiebres, noticias, rutas y puertos,
                               datos desactualizados); sin tabla: se calcula con lo vigente. Umbrales al inicio.
  resumen_semanal.py         ← Correo semanal (alertas + ventas del último mes completo + mercado 7 días)
  calidad_datos.py           ← Reglas de calidad y frescura (catálogo FUENTES con umbrales por fuente; cuadre
                               Bronce→Plata→Oro, toneladas válidas, meses vacíos/atípicos, variables que dejan
                               de llegar, INEGI rezagado, cargas que fallan en silencio). Alimenta la página
                               "Estado de los datos", el indicador de la barra lateral y la bandeja.
  validators.py              ← validate_all (columnas requeridas, % nulos) → anomalías en el Centro de alertas
  chat_ia.py, chat_widget.py, memoria_ia.py ← Asistente IA (Gemini)
  components/                ← charts, filters, kpi_cards, tables, aciertos, frescura (DATOS AL DÍA en la barra)
aceros_planos/
  negros/                    ← COMPLETO
    loaders.py               ← @st.cache_data(ttl=600); get_fecha_corte(), validar_datos()
    loaders_contexto.py      ← INEGI y quiebres relevantes para Planos
    analytics/               ← kpis, segmentacion (ABC, Pareto, HHI), series_tiempo, mix_productos,
                               (forecasting.py aquí solo apunta a core/forecasting.py, que es el motor común)
                               escenarios (simulador: sensibilidad de la venta a indicadores INEGI estimada con la historia)
  galvanizados/ formados/    ← EN DESARROLLO
aceros_largos/  aceros_sbq/  ← otros compañeros
mercado/ (inegi, snice [+ vistas.py], canacero [+ vista_participacion.py]) ·
mercado_noticias/ (detector, rupturas, noticias, categorias, dof_monitor, vistas_industria.py…)
  Las páginas grandes delegan sus piezas: 03_industria → mercado_noticias/vistas_industria.py;
  07_comercio_exterior → mercado/snice/vistas.py y mercado/canacero/vista_participacion.py (pestaña Participación TYASA).
mercado_fastmarkets/         ← ferroaleaciones, alerta_alzas (semáforo XGBoost)
mercado_rutas/               ← Rutas y puertos: red (planta, puertos MX, pasos marítimos, cruce de Nuevo Laredo,
                               orígenes, corredores, grupos Ferroaleaciones / Insumos indirectos / Chatarra),
                               riesgo (rutas por barco y por tren, tráfico vs. normal, nivel de cada punto y ruta),
                               fuentes (PortWatch, NOAA, Open-Meteo), datos (cargadores), proveedores (reales, en
                               Oracle), vistas (mapa con acercamiento y recorrido animado, trayecto, comparar, tablas)
ml/categoria_noticias/       ← clasificador de noticias (embeddings + regresión logística)
pages/
  hub.py (con contador de alertas), alertas_bandeja.py (INICIO → Bandeja de alertas),
  estado_datos.py (INICIO → Estado de los datos), login.py,
  especialista/dashboard.py, chat_ia/chat.py
  ap_negros/00_alertas … 08_mercado_contexto  (alertas, resumen, segmentación, series, pronóstico, mix,
                                                inteligencia de clientes, power rank, contexto de mercado)
  ap_galvanizados/ ap_formados/ aceros_sbq/  → coming_soon
  aceros_largos/01–05        ← equipo de Largos
  mercado/01 monitor · 02 variables · 03 industria · 04 indicadores INEGI · 05 sentimiento · 06 competencia ·
          07 comercio exterior (SNICE) · 08 pronóstico de importación (CANACERO) · 09 quiebres ferroaleaciones ·
          10 rutas y puertos
scripts/                     ← cargas y transformaciones (load_bronze_from_csv, transform_to_silver, transform_to_gold,
                               update_*, setup_*_oracle, load_snice_to_oracle, backfill_*, seed_eventos_historicos…)
.github/workflows/           ← update_market (L–V 8:45 MX), update_sentimiento, update_inegi (día 10),
                               update_snice (día 5), update_semaforo_ferros (día 5), update_trafico_maritimo (L–V 10:00 MX),
                               update_seleccion_modelos (día 6), resumen_semanal (lunes 8:00 MX),
                               keep_alive (30 min)
```

## Tablas Oracle activas
- Ventas (Medallón): BRONZE_VENTAS_RAW → SILVER_VENTAS_LIMPIAS (dedup por clave física, exclusiones, homologación de espacios)
  → GOLD_DEMANDA_CLIENTE · GOLD_DEMANDA_PRODUCTO · GOLD_DEMANDA_MENSUAL · GOLD_CLIENTE_PRODUCTO · GOLD_DEMANDA_PROCESO
  (columnas DIVISION y AREA para separar divisiones/segmentos; hoy solo DIVISION='PLANOS', AREA='NEGROS').
- Mercado: GOLD_VARIABLES_MERCADO · GOLD_MERCADO_MENSUAL · GOLD_QUIEBRES_DETECTADOS · GOLD_NOTICIAS_VINCULADAS ·
  GOLD_SENTIMIENTO_NOTICIAS · GOLD_EVENTOS_HISTORICOS · GOLD_ALERTAS_DOF
- INEGI: GOLD_INDICADORES_INEGI · GOLD_INDICADORES_INEGI_ESTADO
- Comercio exterior: BRONZE_SNICE_SIDERURGICO (retiene 6 meses; aviso = 123 días de vigencia) · GOLD_SNICE_TOP_FRACCIONES
  (historial completo) · GOLD_SNICE_TOP_EMPRESAS/PAISES/CATEGORIAS · GOLD_SNICE_RESUMEN_MENSUAL · BRONZE_CANACERO_COMEX
- Ferroaleaciones: BRONZE_FASTMARKETS_PRECIOS · GOLD_PRECIOS_FASTMARKETS · GOLD_SEMAFORO_FERROS · GOLD_SEMAFORO_METRICAS
- Rutas y puertos: GOLD_TRAFICO_PASOS · GOLD_TRAFICO_PUERTOS (IMF PortWatch, 2 años; scripts/setup_rutas_oracle.py +
  update_trafico_maritimo.py). Si no existen, la página descarga PortWatch directo (~45 s, caché 12 h).
  GOLD_PROVEEDORES_MATERIALES (proveedores reales por material; la app escribe al registrar/quitar, baja lógica
  ACTIVO=0; scripts/setup_proveedores_oracle.py). Sin la tabla, los proveedores viven solo en la sesión.
- Pronóstico: GOLD_SELECCION_MODELO (modelo del modo Automático por serie + firma de los datos; core/seleccion_modelos.py)

## Convenciones
- Nombres de tabla: BRONZE_ | SILVER_ | GOLD_ + descripción; siempre referenciarlas con table_ref().
- Columnas clave: PESO_TON, CLIENTE, PRODUCTO_LIMPIO, PERIODO, AREA, DIVISION.
- AREA_FILTER por loader: "NEGROS" | "GALVANIZADOS" | "FORMADOS".
- Paleta: primary=#1B3A5C | secondary=#4A7BA7 | success=#2E7D32 | danger=#C62828.
- Loaders con @st.cache_data(ttl=600); conexión con @st.cache_resource. Consultas con valores de usuario: run_query_params (binds).
- Fechas de referencia: usar get_fecha_corte() (última FECHAEMB cargada), no date.today().
- Métricas de ventas: SIEMPRE desde core/metricas.py (calcular/valor/variacion/clientes_activos y constantes
  DIAS_CLIENTE_ACTIVO=90, DIAS_CLIENTE_EN_RIESGO=180, DIAS_ALERTA_SIN_COMPRA=60). No sumar N_CLIENTES de tablas por
  producto (cuenta doble). Comparaciones entre meses: solo meses completos (metricas.ultimo_mes_completo).
- Pronóstico: excluir mes incompleto, rellenar meses sin embarques con 0, ventana de prueba común de 6 meses. Meta MAPE aceptable ≤ 30 %.
  Las páginas pronostican con core/seleccion_modelos.generar(df, h, modelo, serie_id, ...) — serie_id tipo
  "NEGROS|PROCESO|<x>" o "CANACERO|IMPORTACION|FRACCION|<f>" (mismo formato en scripts/update_seleccion_modelos.py).
- Nuevas páginas siguen el patrón de pages/ap_negros/01_resumen.py. Si una página pasa de ~600 líneas, sus piezas
  (HTML, tarjetas, pestañas completas) van a un módulo vistas*.py junto a sus loaders.
- Antes de subir cambios grandes: `python scripts/probar_paginas.py` (abre cada página con datos reales y mide tiempos).
- Fuente de datos nueva → agregarla a core/calidad_datos.FUENTES (consulta de último dato, cada cuánto se
  actualiza, umbrales de aviso/falla, secciones donde se muestra). Los loaders no deben tragarse errores en
  silencio sin una regla que lo detecte.
- Caché IA en cache/ai_summaries/<hash>.json (no repetir llamadas a Gemini).

## Estado actual
- Aceros Planos Negros: ✅ completo (9 módulos)
- Mercado Global: ✅ completo (monitor, variables, industria, INEGI, sentimiento, competencia, comercio exterior, pronóstico de importación, ferroaleaciones, rutas y puertos)
- Aceros Planos Galvanizados / Formados: 🚧 en desarrollo
- Aceros Largos: equipo de Largos · Aceros SBQ: pendiente (compañero)
- Copiloto de negociación con motor del experto: 🧭 en diseño (ver bitácora de la tesis)

## Reglas
1. Nunca hardcodear credenciales — secrets.toml / secretos de GitHub y Streamlit.
2. Siempre usar table_ref() para referenciar tablas.
3. Nuevas páginas importan desde core/ y siguen la estructura existente.
4. Al agregar área nueva: actualizar config.py → AREAS y app.py → navegación.
5. Nuevos loaders van en aceros_planos/<subseccion>/loaders.py con AREA_FILTER propio.
6. Cada página nueva tiene sidebar_header() + indicador de carga.
7. Caché de análisis IA en JSON — nunca llamar Gemini si ya existe la respuesta.
8. Claude puede hacer SELECT en Oracle libremente. Las escrituras las corre Otoniel, salvo los 4 comandos de
   regeneración de Plata/Oro, ya permitidos en ~/.claude/settings.json (ver Pendientes).
9. Al subir cambios a loaders/módulos compartidos, Streamlit Cloud necesita "Reboot app".
10. No hacer commit sin que Otoniel lo pida.

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

## Tesis de maestría (alcance: solo Aceros Planos)
- Archivo de trabajo: `C:\Users\OTONIEL\Documents\semestre 2\toma\TECNOLÓGICO NACIONAL DE MÉXICO borrador1.docx`
  (es borrador: los cambios se aplican directo, con respaldo previo en `revision\`). Cap. 4 y Conclusiones se reescribirán.
- Estructura "de lo general a lo particular" (asesor): primero la plataforma común (Hub, Oracle, roles, asistente IA,
  Mercado Global), después Aceros Planos. De Mercado Global NO entran competencia ni sentimiento de noticias.
- Carpeta de apoyo: `...\toma\revision\` (estado_avance.md con "Decisiones del autor", guía de estilo, scripts de cifras,
  capturas y figuras, reportes). Agente revisor: `revisor-tesis`.
- La tesis está "en pausa de redacción": la parte de Planos seguirá cambiando; la corrección final se hace antes de la entrega.

### Regla de bitácora para la tesis (desde 2026-11-13)
Al terminar cualquier cambio funcional al sistema de Aceros Planos o a un componente común que use Planos
(módulo nuevo, modelo, regla de datos, cambio de cifras, tabla nueva en Oracle, flujo nuevo), agregar una entrada en:
C:\Users\OTONIEL\Documents\semestre 2\toma\revision\bitacora_cambios_sistema.md
(sección "Pendientes de redactar", con el formato que indica el archivo: qué cambió, por qué,
archivos, cifras con su fuente y secciones de la tesis afectadas). Avisar al usuario en una línea
que se anotó. No redactar la tesis en ese momento: se integra cuando el usuario lo pida.

## Pendientes (retomar después)
Sistema / datos:
1. **Regenerar Plata y Oro** (permiso ya dado en ~/.claude/settings.json). Desde `proyecto-tyasaBI`, como comandos sueltos:
   `python scripts/transform_to_silver.py --truncate` y luego `python scripts/transform_to_gold.py --truncate`.
   Después: correr `revision\obtener_cifras_tesis.py`, confirmar 703 productos en Plata/Oro, y anotar en la bitácora
   (afecta la Tabla 4.1 de la tesis).
2. Cargar a Bronce la exportación de SAP posterior al 10/03/2026 (cambian casi todas las cifras de la tesis).
3. Desarrollar Galvanizados y Formados (actualizar alcance §1.5 de la tesis).
4. Mejorar el pronóstico: ✅ validación de origen móvil, modelo Combinado ETS+SARIMA y modo Automático por serie
   (default) con selección precalculada en GOLD_SELECCION_MODELO (2026-11-23; ver bitácora).
   **Otoniel debe correr una vez** `python scripts/setup_seleccion_modelos_oracle.py` y luego
   `python scripts/update_seleccion_modelos.py` (o el workflow): sin la tabla, la app calcula la selección al abrir
   cada serie (~10 s c/u; la página 08 tarda ~2 min la primera vez). Falta: ventanas recientes, variables de mercado
   como regresores; comparar el pronóstico mar–ago 2026 contra la venta real.
   Simulador de escenarios (04_forecasting, 2026-11-23): sensibilidades por regresión de variaciones anuales
   (productos metálicos, autos ligeros, importaciones de acero). Al cargar venta nueva se re-estiman solas;
   HRC y tipo de cambio entran cuando tengan ≥ 3 años de historia.
5. Copiloto de negociación con motor del experto: entrevistas (10–20 reglas) → motor de reglas difusas → registro de casos
   en Oracle → casos similares → ML (diseño en la bitácora).
6. ✅ Cambios del 2026-11-13 ya subidos (commit 4ef8b4f).
7. ✅ Archivos `*.tmp.*` borrados (69) y código obsoleto de BigQuery borrado (2026-11-24).
8. Crear la tabla de memoria del asistente: `python scripts/setup_memoria_ia_oracle.py` (escribe en Oracle → lo corre Otoniel).
9. Seguridad: `TYASA-BI - copia\.claude\settings.local.json` tenía un token de GitHub y una API key de Google en texto plano
   → borrar esas líneas y revocar/regenerar las credenciales.
9b. Contraseñas individuales por usuario (hoy `core/auth.py` tiene una sola `_PASS` para los 5): Otoniel lo hará.
    La tesis ya lo documenta así (§3.7 y Recomendaciones); al cambiarlo, anotar en la bitácora y ajustar §3.7.
9c. Vista de especialistas: hoy van a `pages/especialista/dashboard.py` (provisional). Otoniel actualizará esas secciones;
    la tesis dice que "su vista se habilita conforme se liberan los módulos de su división" (§3.5.1, §3.7). Al cambiarlo → bitácora.
9e. Textos de la app que todavía dicen "31 variables" (`pages/mercado/02_variables.py`): son 35.
9f. ✅ El motor de pronóstico ya es común (core/forecasting.py, 2026-11-24).
Tesis:
10. Datos personales (portada, agradecimientos), sesiones de validación con usuarios, tiempo de elaboración de reportes
    (hipótesis), motivos de la migración, referencias incompletas (en amarillo), confirmar con TYASA los nombres de clientes en capturas.
11. Pendientes en amarillo nuevos: cita de la vigencia de 123 días de los avisos del SNICE (§3.6.1.3).
    (Las observaciones del revisor del 2026-11-13 ya se aplicaron en el borrador1.)
12. Reescribir Cap. 4 y Conclusiones con el orden plataforma común → Aceros Planos; integrar la bitácora; pasar el revisor.

## Notas de sesiones
Las notas de cada sesión se guardan en:
C:\Users\OTONIEL\Desktop\obsidian\sesiones\
Plantilla: templates/sesion-claude.md
Última nota en Obsidian: 2026-04-28 — Rediseño Power BI + Fix removeChild definitivo

## Regla de documentación en Obsidian
Cuando el usuario pida "anota esto en Obsidian" o "actualiza Obsidian" al final de una tarea:
1. Crear o actualizar C:\Users\OTONIEL\Desktop\obsidian\sesiones\YYYY-MM-DD-<tema>.md
2. Actualizar la sección correspondiente en C:\Users\OTONIEL\Desktop\obsidian\proyectos\bi-principal.md
   - Módulos completados / en desarrollo
   - Tablas nuevas
   - Decisiones arquitectónicas nuevas
   - Log de sesiones
3. Si hay una nueva tabla, decisión de arquitectura o módulo nuevo → reflejar en este CLAUDE.md también
