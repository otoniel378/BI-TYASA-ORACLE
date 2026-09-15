"""
aceros_largos/loaders.py — Loaders de datos para Aceros Largos
Conecta con datos reales de INEGI y comercio acero desde BigQuery
Integra las nuevas tablas INEGI manuales y tyasa_bronce_comercio_acero
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from core.db_connector import get_bq_client, table_ref
from .loaders_new_data import (
    load_inegi_inpc_data,
    load_inegi_construccion_data, 
    load_inegi_construccion_segmented,
    load_inegi_pib_data,
    load_internal_demand_aceros_largos,
    load_macro_market_series,
    load_comercio_acero_summary,
    load_comercio_acero_time_series,
    load_macro_kpis_summary
)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
# Cache TTL más largo para datos externos que se actualizan menos frecuentemente
CACHE_TTL = 3600  # 1 hora en lugar de 10 minutos

# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL)
def load_inegi_data(indicador: str, limit_months: int = 12) -> pd.DataFrame:
    """Cargar datos INEGI desde BigQuery"""
    try:
        client = get_bq_client()
        table_name = f"gold_inegi_{indicador}"
        
        # Query para obtener los últimos N meses
        query = f"""
        SELECT 
            fecha,
            periodo,
            valor,
            indicador_nombre,
            ultima_actualizacion
        FROM {table_ref(table_name)}
        WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL {limit_months} MONTH)
        ORDER BY fecha DESC
        LIMIT 100
        """
        
        df = client.query(query).to_dataframe()
        return df
        
    except Exception as e:
        st.warning(f"No se pudieron cargar datos de {indicador} desde BigQuery. Usando datos por defecto.")
        print(f"Error cargando {indicador}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL)  
def load_mocamx_summary() -> Dict[str, Any]:
    """Cargar resumen de comercio de acero desde MOCAMX/BigQuery"""
    try:
        client = get_bq_client()
        
        # Importaciones recientes
        query_imp = f"""
        SELECT 
            SUM(valor_usd) as total_importaciones_usd,
            SUM(peso_kg) as total_importaciones_kg,
            AVG(precio_unitario_usd_kg) as precio_promedio
        FROM `{table_ref('gold_mocamx_importaciones')}`
        WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH)
        """
        
        # Exportaciones recientes  
        query_exp = f"""
        SELECT 
            SUM(valor_usd) as total_exportaciones_usd,
            SUM(peso_kg) as total_exportaciones_kg,
            AVG(precio_unitario_usd_kg) as precio_promedio
        FROM `{table_ref('gold_mocamx_exportaciones')}`
        WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH)
        """
        
        # Producción nacional
        query_prod = f"""
        SELECT 
            tipo_acero,
            SUM(volumen_ton) as volumen_total,
            AVG(capacidad_utilizada_pct) as capacidad_promedio
        FROM `{table_ref('gold_mocamx_produccion')}`
        WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH)
        GROUP BY tipo_acero
        """
        
        df_imp = client.query(query_imp).to_dataframe()
        df_exp = client.query(query_exp).to_dataframe()
        df_prod = client.query(query_prod).to_dataframe()
        
        return {
            'importaciones': df_imp.iloc[0].to_dict() if not df_imp.empty else {},
            'exportaciones': df_exp.iloc[0].to_dict() if not df_exp.empty else {},
            'produccion': df_prod.to_dict('records') if not df_prod.empty else []
        }
        
    except Exception as e:
        st.warning("No se pudieron cargar datos de MOCAMX desde BigQuery. Usando datos por defecto.")
        print(f"Error cargando MOCAMX: {e}")
        return {'importaciones': {}, 'exportaciones': {}, 'produccion': []}

def calculate_trend(df: pd.DataFrame, value_col: str = 'valor') -> Dict[str, Any]:
    """Calcular tendencia y variación porcentual"""
    if df.empty or len(df) < 2:
        return {'trend': 0, 'trend_type': 'stable', 'latest_value': 0}
    
    # Ordenar por fecha
    df_sorted = df.sort_values('fecha')
    latest = df_sorted.iloc[-1][value_col] if not pd.isna(df_sorted.iloc[-1][value_col]) else 0
    previous = df_sorted.iloc[-2][value_col] if len(df_sorted) > 1 and not pd.isna(df_sorted.iloc[-2][value_col]) else latest
    
    if previous != 0:
        trend = ((latest - previous) / previous) * 100
    else:
        trend = 0
    
    trend_type = 'up' if trend > 0 else 'down' if trend < 0 else 'stable'
    
    return {
        'trend': round(trend, 1),
        'trend_type': trend_type, 
        'latest_value': latest,
        'previous_value': previous
    }

# ---------------------------------------------------------------------------
# LOADERS PRINCIPALES
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL)
def load_ticker_data() -> List[Dict[str, str]]:
    """Carga datos del ticker superior con indicadores reales de nuevas fuentes"""
    
    try:
        # Cargar KPIs consolidados
        kpis = load_macro_kpis_summary()
        
        # Cargar datos de comercio acero
        comercio_summary = load_comercio_acero_summary(3)
        
        ticker_items = []
        
        # INPC desde nuevos datos
        if 'inpc' in kpis and kpis['inpc']['valor']:
            inpc_valor = kpis['inpc']['valor']
            inpc_trend = kpis['inpc']['tendencia_pct']
            ticker_items.append({
                "label": "INPC General",
                "value": f"{inpc_valor:.2f}%",
                "color": "tertiary" if inpc_trend > 0 else "secondary"
            })
        else:
            ticker_items.append({"label": "INPC General", "value": "3.93%", "color": "secondary"})
        
        # Construcción desde nuevos datos
        if 'construccion' in kpis and kpis['construccion']['valor']:
            const_trend = kpis['construccion']['tendencia_pct']
            ticker_items.append({
                "label": "Actividad Construcción",
                "value": f"{const_trend:+.1f}% MoM",
                "color": "tertiary" if const_trend < 0 else "secondary"
            })
        else:
            ticker_items.append({"label": "Actividad Construcción", "value": "-2.1% MoM", "color": "tertiary"})
        
        # Comercio acero desde nuevos datos
        if comercio_summary:
            exp_data = comercio_summary.get('exportacion', {})
            if exp_data.get('volumen_total_ton', 0) > 0:
                exp_volumen_k = exp_data['volumen_total_ton'] / 1000
                ticker_items.append({
                    "label": "Expo Acero (3M)",
                    "value": f"{exp_volumen_k:.0f}K Ton",
                    "color": "secondary"
                })
        
        # Series macro financieras
        if 'usd_mxn' in kpis and kpis['usd_mxn'].get('valor'):
            ticker_items.append({
                "label": "USD/MXN",
                "value": f"${kpis['usd_mxn']['valor']:.2f}",
                "color": "white"
            })

        # Completar con datos estáticos
        ticker_items.extend([
            {"label": "USD/MXN", "value": "$17.82", "color": "white"} if not any(t["label"] == "USD/MXN" for t in ticker_items) else None,
            {"label": "Inv. Pública", "value": "$542 mil mdp", "color": "white"},
            {"label": "Arancel China", "value": "25-50%", "color": "tertiary"},
            {"label": "TYASA Laminador", "value": "$450 MDD inv.", "color": "secondary"},
            {"label": "CMIC 2026-29", "value": "+2.6% prom.", "color": "secondary"}
        ])
        ticker_items = [item for item in ticker_items if item is not None]
        
        return ticker_items[:9]  # Limitar a 9 items para el ticker
        
    except Exception as e:
        st.warning(f"Error cargando ticker (fallback a legacy): {e}")
        # Fallback to legacy data
        inpc_data = load_inegi_data('inpc', 3)
        construccion_data = load_inegi_data('construccion', 3) 
        
        inpc_trend = calculate_trend(inpc_data)
        construccion_trend = calculate_trend(construccion_data)
        
        ticker_items = [
            {
                "label": "INPC General", 
                "value": f"{inpc_trend['latest_value']:.1f}%" if inpc_trend['latest_value'] > 0 else "3.93%",
                "color": "tertiary" if inpc_trend['trend_type'] == 'up' else "secondary"
            },
            {
                "label": "Actividad Construcción",
                "value": f"{construccion_trend['trend']:.1f}% MoM" if construccion_trend['trend'] != 0 else "-2.1% MoM",
                "color": "tertiary" if construccion_trend['trend_type'] == 'down' else "secondary"
            },
            {"label": "USD/MXN", "value": "$17.82", "color": "white"},
            {"label": "Inv. Pública", "value": "$542 mil mdp", "color": "white"},
            {"label": "Arancel China", "value": "25-50%", "color": "tertiary"},
            {"label": "Expo MX-USA", "value": "-49%", "color": "tertiary"},
            {"label": "TYASA Laminador", "value": "$450 MDD inv.", "color": "secondary"},
            {"label": "CMIC 2026-29", "value": "+2.6% prom.", "color": "secondary"}
        ]
        
        return ticker_items

@st.cache_data(ttl=CACHE_TTL)
def load_macroeconomic_indicators() -> Dict[str, Any]:
    """Cargar indicadores macroeconómicos desde nuevas tablas INEGI"""
    
    try:
        # Usar nuevos loaders con datos reales
        kpis = load_macro_kpis_summary()
        
        # Cargar datos detallados
        inpc_data = load_inegi_inpc_data(12)
        construccion_data = load_inegi_construccion_data(12)
        construccion_segmentada = load_inegi_construccion_segmented(12)
        pib_data = load_inegi_pib_data(8)
        demand_data = load_internal_demand_aceros_largos(12)
        market_series = load_macro_market_series(12)
        
        # Procesar datos de inflación
        if 'inpc' in kpis:
            inflacion_info = {
                'valor_actual': kpis['inpc']['valor'],
                'tendencia': kpis['inpc']['tendencia_pct'],
                'tipo_tendencia': 'up' if kpis['inpc']['tendencia_pct'] > 0 else 'down' if kpis['inpc']['tendencia_pct'] < 0 else 'stable',
                'unidad_valor': '%',
                'unidad_tendencia': 'pp',
                'serie_historica': inpc_data.to_dict('records') if not inpc_data.empty else []
            }
        else:
            # Fallback to legacy calculation
            inpc_trend = calculate_trend(inpc_data)
            inflacion_info = {
                'valor_actual': inpc_trend['latest_value'], 
                'tendencia': inpc_trend['trend'],
                'tipo_tendencia': inpc_trend['trend_type'],
                'serie_historica': inpc_data.to_dict('records') if not inpc_data.empty else []
            }
        
        # Procesar datos de construcción
        if 'construccion' in kpis:
            construccion_info = {
                'valor_actual': kpis['construccion']['valor'],
                'tendencia': kpis['construccion']['tendencia_pct'],
                'tipo_tendencia': 'up' if kpis['construccion']['tendencia_pct'] > 0 else 'down' if kpis['construccion']['tendencia_pct'] < 0 else 'stable',
                'unidad_valor': '% YoY',
                'unidad_tendencia': 'pp',
                'serie_historica': construccion_data.to_dict('records') if not construccion_data.empty else []
            }
        else:
            # Fallback to legacy calculation
            construccion_trend = calculate_trend(construccion_data)
            construccion_info = {
                'valor_actual': construccion_trend['latest_value'],
                'tendencia': construccion_trend['trend'],
                'tipo_tendencia': construccion_trend['trend_type'],
                'serie_historica': construccion_data.to_dict('records') if not construccion_data.empty else []
            }
        
        # Procesar datos de PIB
        if 'pib' in kpis:
            pib_info = {
                'valor_actual': kpis['pib']['valor'],
                'tendencia': kpis['pib']['tendencia_pct'],
                'tipo_tendencia': 'up' if kpis['pib']['tendencia_pct'] > 0 else 'down' if kpis['pib']['tendencia_pct'] < 0 else 'stable',
                'unidad_valor': '% YoY',
                'unidad_tendencia': 'pp',
                'serie_historica': pib_data.to_dict('records') if not pib_data.empty else []
            }
        else:
            # Fallback to legacy calculation
            pib_trend = calculate_trend(pib_data)
            pib_info = {
                'valor_actual': pib_trend['latest_value'],
                'tendencia': pib_trend['trend'],
                'tipo_tendencia': pib_trend['trend_type'],
                'serie_historica': pib_data.to_dict('records') if not pib_data.empty else []
            }
        
        # No hay fuente confiable de empleo cargada para Aceros Largos todavía.
        empleo_data = pd.DataFrame()
        empleo_trend = {'latest_value': 0, 'trend': 0, 'trend_type': 'stable'}

        mercado_info = {}
        if not market_series.empty:
            for serie in ['usd_mxn']:
                serie_df = market_series[market_series['serie'] == serie]
                if not serie_df.empty:
                    serie_trend = calculate_trend(serie_df)
                    mercado_info[serie] = {
                        'valor_actual': serie_trend['latest_value'],
                        'tendencia': serie_trend['trend'],
                        'tipo_tendencia': serie_trend['trend_type'],
                        'serie_historica': serie_df.to_dict('records')
                    }

        demanda_info = {}
        if not demand_data.empty:
            demanda_trend = calculate_trend(demand_data, 'peso_ton')
            demanda_info = {
                'valor_actual': demanda_trend['latest_value'],
                'tendencia': demanda_trend['trend'],
                'tipo_tendencia': demanda_trend['trend_type'],
                'serie_historica': demand_data.to_dict('records')
            }
        
        return {
            'pib': pib_info,
            'inflacion': inflacion_info,
            'empleo': {
                'valor_actual': empleo_trend['latest_value'],
                'tendencia': empleo_trend['trend'],
                'tipo_tendencia': empleo_trend['trend_type'],
                'serie_historica': empleo_data.to_dict('records') if not empleo_data.empty else []
            },
            'construccion': construccion_info,
            'construccion_segmentada': construccion_segmentada.to_dict('records') if not construccion_segmentada.empty else [],
            'demanda_interna': demanda_info,
            'usd_mxn': mercado_info.get('usd_mxn', {})
        }
        
    except Exception as e:
        st.warning(f"Error cargando indicadores macro (fallback a legacy): {e}")
        # Fallback to original implementation
        pib_data = load_inegi_data('pib', 8) 
        inpc_data = load_inegi_data('inpc', 12)
        empleo_data = load_inegi_data('empleo', 12)
        construccion_data = load_inegi_data('construccion', 12)
        
        pib_trend = calculate_trend(pib_data)
        inpc_trend = calculate_trend(inpc_data)
        empleo_trend = calculate_trend(empleo_data)
        construccion_trend = calculate_trend(construccion_data)
        
        return {
            'pib': {
                'valor_actual': pib_trend['latest_value'],
                'tendencia': pib_trend['trend'],
                'tipo_tendencia': pib_trend['trend_type'],
                'serie_historica': pib_data.to_dict('records') if not pib_data.empty else []
            },
            'inflacion': {
                'valor_actual': inpc_trend['latest_value'], 
                'tendencia': inpc_trend['trend'],
                'tipo_tendencia': inpc_trend['trend_type'],
                'serie_historica': inpc_data.to_dict('records') if not inpc_data.empty else []
            },
            'empleo': {
                'valor_actual': empleo_trend['latest_value'],
                'tendencia': empleo_trend['trend'],
                'tipo_tendencia': empleo_trend['trend_type'],
                'serie_historica': empleo_data.to_dict('records') if not empleo_data.empty else []
            },
            'construccion': {
                'valor_actual': construccion_trend['latest_value'],
                'tendencia': construccion_trend['trend'],
                'tipo_tendencia': construccion_trend['trend_type'],
                'serie_historica': construccion_data.to_dict('records') if not construccion_data.empty else []
            }
        }

@st.cache_data(ttl=CACHE_TTL)
def load_steel_market_data() -> Dict[str, Any]:
    """Cargar datos del mercado de acero desde nueva tabla comercio acero"""
    
    try:
        # Usar nuevo loader con datos reales de comercio
        comercio_summary = load_comercio_acero_summary(12)
        comercio_time_series = load_comercio_acero_time_series(6)
        
        # Procesar datos
        importaciones = comercio_summary.get('importacion', {})
        exportaciones = comercio_summary.get('exportacion', {})
        
        # Calcular balanza comercial en toneladas
        imp_volumen = importaciones.get('volumen_total_ton', 0)
        exp_volumen = exportaciones.get('volumen_total_ton', 0)
        balanza_volumen = exp_volumen - imp_volumen
        
        return {
            'comercio_exterior': {
                'importaciones_ton': imp_volumen,
                'exportaciones_ton': exp_volumen,
                'balanza_comercial_ton': balanza_volumen,
                'balanza_comercial': balanza_volumen,
                'paises_importacion': importaciones.get('paises_distintos', 0),
                'paises_exportacion': exportaciones.get('paises_distintos', 0),
                'productos_importacion': importaciones.get('productos_distintos', 0),
                'productos_exportacion': exportaciones.get('productos_distintos', 0)
            },
            'tendencias_temporales': {
                'serie_mensual': comercio_time_series.to_dict('records') if not comercio_time_series.empty else []
            },
            'ultima_actualizacion': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'fuente': 'Monitor Comercio Acero México'
        }
        
    except Exception as e:
        st.warning(f"Error cargando datos comercio acero (fallback a legacy): {e}")
        # Fallback to legacy MOCAMX data
        mocamx_data = load_mocamx_summary()
        
        imp_data = mocamx_data['importaciones']
        exp_data = mocamx_data['exportaciones']
        prod_data = mocamx_data['produccion']
        
        return {
            'comercio_exterior': {
                'importaciones_usd': imp_data.get('total_importaciones_usd', 0),
                'exportaciones_usd': exp_data.get('total_exportaciones_usd', 0),
                'balanza_comercial': exp_data.get('total_exportaciones_usd', 0) - imp_data.get('total_importaciones_usd', 0),
                'precio_importacion_promedio': imp_data.get('precio_promedio', 0),
                'precio_exportacion_promedio': exp_data.get('precio_promedio', 0)
            },
            'produccion_nacional': prod_data,
            'ultima_actualizacion': datetime.now().strftime("%Y-%m-%d %H:%M")
        }

@st.cache_data(ttl=CACHE_TTL)
def load_sectoral_analysis() -> Dict[str, Any]:
    """Análisis sectorial detallado con datos INEGI"""
    
    # Cargar datos de múltiples sectores
    construccion_data = load_inegi_data('construccion', 24)  # 2 años
    manufactura_data = load_inegi_data('manufactura', 24)
    mineria_data = load_inegi_data('mineria', 24)
    
    sectores = {
        'construccion': {
            'nombre': 'Construcción',
            'data': construccion_data,
            'impacto_acero': 'Alto'  # Sector clave para aceros largos
        },
        'manufactura': {
            'nombre': 'Manufactura',
            'data': manufactura_data,
            'impacto_acero': 'Medio'
        },
        'mineria': {
            'nombre': 'Minería',
            'data': mineria_data, 
            'impacto_acero': 'Bajo'
        }
    }
    
    # Calcular métricas por sector
    resultado = {}
    for sector_key, sector_info in sectores.items():
        trend = calculate_trend(sector_info['data'])
        resultado[sector_key] = {
            'nombre': sector_info['nombre'],
            'valor_actual': trend['latest_value'],
            'tendencia_pct': trend['trend'],
            'tipo_tendencia': trend['trend_type'],
            'impacto_acero': sector_info['impacto_acero'],
            'serie_reciente': sector_info['data'].tail(12).to_dict('records') if not sector_info['data'].empty else []
        }
    
    return resultado

# ---------------------------------------------------------------------------
# LOADERS LEGACY (compatibilidad con páginas existentes)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL)
def load_executive_summary() -> Dict[str, Any]:
    """Resumen ejecutivo con datos reales integrados"""
    
    # Cargar datos macro
    macro_data = load_macroeconomic_indicators()
    steel_data = load_steel_market_data()
    
    # Construir resumen con datos reales + estimaciones
    return {
        "ebitda": {
            "label": "EBITDA Mensual Est.",
            "value": "$10.8M",
            "trend": f"{macro_data['construccion']['tendencia']:.1f}% vs 2024" if macro_data['construccion']['tendencia'] != 0 else "-12.9% vs 2024",
            "trend_type": macro_data['construccion']['tipo_tendencia'],
            "unit": "USD"
        },
        "margin": {
            "label": "Margen Operativo",
            "value": "14.2%",
            "trend": "-2.8 pp vs 2024",
            "trend_type": "down",
            "unit": "Crisis construcción"
        },
        "sales_trend": [
            {"mes": "Ago", "ventas": 94},
            {"mes": "Sep", "ventas": 87},
            {"mes": "Oct", "ventas": 82},
            {"mes": "Nov", "ventas": 71},
            {"mes": "Dic", "ventas": 76},
            {"mes": "Ene", "ventas": 80},
            {"mes": "Feb", "ventas": 83},
            {"mes": "Mar", "ventas": 88}
        ],
        "production_goals": [
            {"label": "Varilla Corrugada", "pct": 78, "color": "#ffb3ad", "text_color": "tertiary"},
            {"label": "Alambrón", "pct": 72, "color": "#ffb3ad", "text_color": "tertiary"},
            {"label": "Perfiles Estruct.", "pct": 88, "color": "#4edea3", "text_color": "secondary"}
        ],
        "regional_sales": [
            {"label": "Nacional (México)", "pct": 81, "color": "green"},
            {"label": "Exportación (USA)", "pct": 11, "color": "red"},
            {"label": "LATAM", "pct": 8, "color": "blue"}
        ],
        "macro_context": macro_data,
        "steel_market": steel_data
    }

@st.cache_data(ttl=CACHE_TTL)
def load_macro_data() -> Dict[str, Any]:
    """Cargar datos macroeconómicos (wrapper para compatibilidad)"""
    macro_indicators = load_macroeconomic_indicators()
    
    return {
        "interest_rate": {
            "label": "Tasa de Interés (Banxico)",
            "value": "7.00%",
            "trend": "Pausada 2026",
            "trend_type": "down",
            "unit": "Recorte Dic 2025"
        },
        "inflation": {
            "label": "Inflación (INPC)",
            "value": f"{macro_indicators['inflacion']['valor_actual']:.2f}%" if macro_indicators['inflacion']['valor_actual'] > 0 else "3.93%",
            "trend": f"{macro_indicators['inflacion']['tendencia']:+.2f} pp" if macro_indicators['inflacion']['tendencia'] != 0 else "-0.52 pp vs pico",
            "trend_type": macro_indicators['inflacion']['tipo_tendencia'],
            "unit": "Anual"
        },
        "construction_trend": [
            {"mes": item['periodo'], "val": item['valor']} 
            for item in macro_indicators['construccion']['serie_historica'][-12:] 
            if item['valor'] is not None
        ] if macro_indicators['construccion']['serie_historica'] else [
            {"mes": "Ene'25", "val": -4.1},
            {"mes": "Mar'25", "val": -5.8},
            {"mes": "May'25", "val": -6.3},
            {"mes": "Jul'25", "val": -8.5},
            {"mes": "Sep'25", "val": -7.2},
            {"mes": "Nov'25", "val": -15.6},
            {"mes": "Pron'26", "val": 2.6}
        ],
        "market_signals": [
            {"label": "Construcción residencial", "val": f"{macro_indicators['construccion']['tendencia']:.1f}% MoM", "impacto": "Alto"},
            {"label": "Inversión pública 2025", "val": "$542 mil mdp", "impacto": "Alto"},
            {"label": "Recorte inversión pública", "val": "-9.7% interan.", "impacto": "Alto"},
            {"label": "Tasa Banxico (dic 2025)", "val": "7.00%", "impacto": "Medio"},
            {"label": "Arancel China acero", "val": "25–50%", "impacto": "Alto"},
            {"label": "Expo México-USA", "val": "-49%", "impacto": "Alto"},
            {"label": "Nearshoring (oportunidad)", "val": "Activo 2026", "impacto": "Oport."}
        ]
    }

@st.cache_data(ttl=CACHE_TTL)
def load_market_data() -> Dict[str, Any]:
    """Datos de mercado y costos con integración MOCAMX"""
    steel_data = load_steel_market_data()
    return _build_market_data_from_steel(steel_data)


def _build_market_data_from_steel(steel_data: Dict[str, Any]) -> Dict[str, Any]:
    """Construye contrato de mercado robusto desde datos de comercio acero.

    Mantiene compatibilidad entre `balanza_comercial_ton` y el nombre legacy
    `balanza_comercial` para que páginas existentes no fallen.
    """
    comercio = steel_data.get('comercio_exterior', {})
    balanza = comercio.get('balanza_comercial_ton', comercio.get('balanza_comercial', 0))

    return {
        "usd_mxn": {
            "label": "USD / MXN Spot",
            "value": "$17.82",
            "trend": "+1.64%", 
            "trend_type": "up",
            "unit": "Depreciación MXN"
        },
        "scrap_price": {
            "label": "Chatarra / Scrap (Platts)",
            "value": "$3,380",
            "trend": "-2.1% vs mes ant.",
            "trend_type": "down",
            "unit": "MXN / Ton  ·  Dic 2025"
        },
        "trade_balance": {
            "label": "Balanza Comercial Acero Largos",
            "value": f"{balanza/1000:,.0f}K ton" if balanza != 0 else "N/D",
            "trend": "Superávit" if balanza > 0 else "Déficit" if balanza < 0 else "Sin datos",
            "trend_type": "up" if balanza > 0 else "down" if balanza < 0 else "stable",
            "unit": "Toneladas · Últimos 12M"
        }
    }

# ---------------------------------------------------------------------------
# FUNCIONES DE COMPATIBILIDAD (sin cambios para no romper páginas existentes)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL)
def load_operations_data() -> Dict[str, Any]:
    """Datos de operaciones e inventario (sin cambios)"""
    return {
        "production": {
            "label": "Producción Diaria",
            "value": "1,850",
            "trend": "-3.1% vs plan",
            "trend_type": "down",
            "unit": "MT / Día"
        },
        "scrap_stock": {
            "label": "Chatarra en Stock",
            "value": "48,200",
            "trend": "+6.8% acumulación",
            "trend_type": "up",
            "unit": "MT · Presión costo"
        },
        "equipment_status": [
            {"name": "Horno de Arco Eléctrico (EAF)", "status": "Operativo", "color": "secondary"},
            {"name": "Tren de Laminación (existente)", "status": "Operativo", "color": "secondary"},
            {"name": "Nuevo Laminador ($450 MDD)", "status": "En instalación", "color": "primary"},
            {"name": "Planta de Oxígeno", "status": "Mantenimiento", "color": "tertiary"}
        ],
        "inventory": [
            {"name": "Varilla", "mt": 18750, "max": 25000, "color": "#ffb3ad", "pct": 75},
            {"name": "Alambrón", "mt": 10400, "max": 15000, "color": "#ffb3ad", "pct": 69},
            {"name": "Perfiles", "mt": 4150, "max": 12000, "color": "#4edea3", "pct": 35}
        ]
    }

@st.cache_data(ttl=CACHE_TTL)
def load_quality_data() -> Dict[str, Any]:
    """Datos de calidad y certificaciones (sin cambios)"""
    return {
        "quality_index": {
            "label": "Índice de Calidad",
            "value": "99.85%",
            "trend": "+0.05% vs Q3",
            "trend_type": "up",
            "unit": "% Aprobación lotes"
        },
        "certs_count": {
            "label": "Certificaciones Activas",
            "value": "12",
            "trend": "Todas vigentes",
            "trend_type": "up",
            "unit": "Normas sísmicas incl."
        },
        "tests": [
            {"test": "Pruebas de Tensión", "result": "100% Aprobado", "ok": True},
            {"test": "Análisis Químico", "result": "100% Aprobado", "ok": True},
            {"test": "Doblado en Frío", "result": "100% Aprobado", "ok": True},
            {"test": "Resistencia Sísmica", "result": "100% Aprobado", "ok": True},
            {"test": "Geometría y Resalles", "result": "99.7% Aprob.", "ok": True}
        ],
        "certifications": [
            {"name": "ISO 9001:2015", "desc": "Gestión de Calidad", "active": True},
            {"name": "ISO 14001:2015", "desc": "Gestión Ambiental", "active": True},
            {"name": "NMX-B-457-CANACERO", "desc": "Varilla Corrugada Nacional", "active": True},
            {"name": "ASTM A615 Gr.60", "desc": "Exportación USA", "active": True},
            {"name": "NTC-2017 Sísmica (CDMX)", "desc": "Resistencia Antisísmica", "active": True},
            {"name": "ISO 45001:2018", "desc": "Seguridad Ocupacional", "active": True}
        ]
    }

# ---------------------------------------------------------------------------
# UTILS
# ---------------------------------------------------------------------------

def get_last_update() -> str:
    """Retorna timestamp de última actualización"""
    return datetime.now().strftime("%Y-%m-%d · %H:%M CST")

def get_data_sources() -> List[str]:
    """Retorna las fuentes de datos"""
    return ["INEGI API", "MOCAMX", "BigQuery", "Banxico", "Bloomberg & Platts"]
