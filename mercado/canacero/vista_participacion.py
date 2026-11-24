"""
vista_participacion.py — Pestaña "Participación TYASA" de Comercio Exterior Siderúrgico
(pages/mercado/07_comercio_exterior.py): comercio exterior nacional de CANACERO
(carga de CSV, importaciones/exportaciones de las fracciones de TYASA, pronóstico
de participación) y detalle por empresa del SNICE.
"""

import os
import sys

import pandas as pd
import streamlit as st

from config import COLORS
from core.components.kpi_cards import render_kpi_row
from core.components.charts import (
    linea_temporal, barras_horizontales, estructura_100, barras_divergentes, barras_con_tendencia,
    espejo_flujos, barras_resaltada, linea_vigencias, cambio_puntos, linea_con_promedio, scatter_cuadrantes,
)
# Los catálogos de fracciones viven en scripts/ (los comparten las cargas y la página).
_scripts = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from fracciones_tyasa import FRACCIONES_TYASA, FRACCIONES_TYASA_PREFIJO, RAZON_SOCIAL_TYASA_SNICE
from fracciones_tyasa_ligie import FRACCIONES_TYASA_DESCRIPCION
from mercado.snice.loaders import (
    load_top_fracciones_tyasa_gold,
    load_serie_tyasa_gold,
    load_serie_empresa_gold,
    load_rango_vigencia_disponible,
    load_resumen_vigentes_en_mes,
    load_fracciones_vigentes_en_mes,
    load_avisos_vigentes_en_mes,
    load_empresas_fracciones,
    load_empresas_fraccion_exacta,
    load_avisos_fraccion_exacta,
    load_paises_fracciones,
)
from mercado.canacero.loaders import (
    cargar_csv_canacero,
    load_periodos_canacero,
    load_resumen_tyasa,
    load_serie_tiempo_tyasa,
    load_series_fracciones_tyasa,
    load_top_fracciones_tyasa,
    load_serie_fraccion,
)
from mercado.snice.vistas import (
    _card_open,
    _CARD_CLOSE,
    _rank_list_html,
    _color_signo,
    _flecha_pct,
    _flecha_pp,
    _top_fracciones_html,
    _pais_corto,
    _empresa_corta,
)


def render_participacion_tyasa(*, FRACCIONES_TYASA_PREFIJO_T, FRACCIONES_TYASA_T, PRECIO_MINIMO_PLAUSIBLE_USD_TON, UMBRAL_CONCENTRACION_MENSUAL, UMBRAL_VOLATILIDAD_HISTORICA, VOLUMEN_MINIMO_PARA_PRECIO, _periodo_anterior_bronze, en_ventana, periodo_sel, periodos):
    st.caption("Comercio exterior nacional (CANACERO) y detalle por empresa (SNICE).")

    with st.expander("Cargar nuevo periodo de CANACERO (CSV de 'Base de datos tradicional')"):
        c_up1, c_up2 = st.columns([2, 1])
        with c_up1:
            archivo_canacero = st.file_uploader(
                "CSV exportado de CANACERO SICEP (Grupos Personalizados > Grupo Fracciones > "
                "Base de datos tradicional, agrupado por Fracciones)",
                type=["csv"], key="canacero_uploader",
            )
        with c_up2:
            movimiento_up_label = st.selectbox(
                "Movimiento", ["Importación", "Exportación"], key="canacero_movimiento_up"
            )
        if st.button("Cargar a Oracle", disabled=archivo_canacero is None, key="canacero_cargar_btn"):
            movimiento_up = "IMPORTACION" if movimiento_up_label == "Importación" else "EXPORTACION"
            try:
                resultado = cargar_csv_canacero(archivo_canacero, movimiento_up, archivo_canacero.name)
                if resultado["filas_insertadas"] == 0:
                    st.warning("El archivo no tenía filas con volumen distinto de cero.")
                else:
                    st.success(
                        f"Cargado: {resultado['filas_insertadas']:,} filas · "
                        f"periodos {', '.join(resultado['periodos'])} · movimiento {resultado['movimiento']}"
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"No se pudo cargar el archivo: {e}")

    movimiento_dash_label = st.radio(
        "Movimiento a analizar", ["Importación", "Exportación"], horizontal=True, key="canacero_movimiento_dash",
    )
    movimiento_dash = "IMPORTACION" if movimiento_dash_label == "Importación" else "EXPORTACION"

    periodos_canacero = load_periodos_canacero(movimiento_dash)

    if not periodos_canacero:
        st.info(
            "Todavía no hay datos de CANACERO cargados para este movimiento. "
            "Sube un CSV arriba para empezar."
        )
    else:
        periodo_canacero_sel = st.selectbox(
            "Periodo (CANACERO)", periodos_canacero, index=0, key="canacero_periodo_sel"
        )

        opciones_fraccion_todas = sorted(FRACCIONES_TYASA)
        etiquetas_fraccion = {
            f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}" for f in opciones_fraccion_todas
        }
        seleccion_analisis = st.multiselect(
            "Fracciones a incluir en el análisis (todo lo de abajo se filtra con esto)",
            opciones_fraccion_todas, default=opciones_fraccion_todas,
            format_func=lambda f: etiquetas_fraccion[f], key="canacero_fracciones_analisis",
        )
        if not seleccion_analisis:
            st.warning("Selecciona al menos una fracción para ver el análisis.")
            st.stop()

        usa_catalogo_completo = set(seleccion_analisis) == set(opciones_fraccion_todas)
        fracciones_filtro = None if usa_catalogo_completo else tuple(seleccion_analisis)
        fracciones_exactas_snice = tuple(FRACCIONES_TYASA) if usa_catalogo_completo else tuple(seleccion_analisis)
        fracciones_prefijo_snice = tuple(FRACCIONES_TYASA_PREFIJO) if usa_catalogo_completo else ()
        opciones_fraccion = sorted(seleccion_analisis)

        resumen_nac = load_resumen_tyasa(periodo_canacero_sel, movimiento_dash, fracciones=fracciones_filtro)
        vol_nacional_ton = resumen_nac.get("volumen_total") or 0

        es_importacion = movimiento_dash == "IMPORTACION"

        if es_importacion:
            empresas_tyasa = load_empresas_fracciones(
                periodo_sel, fracciones_exactas_snice, fracciones_prefijo_snice,
            )
            vol_snice_ton = (empresas_tyasa["volumen_total"].sum() / 1000) if not empresas_tyasa.empty else 0
            cobertura_pct = (vol_snice_ton / vol_nacional_ton * 100) if vol_nacional_ton else 0
            empresa_top = empresas_tyasa.iloc[0]["razon_social"] if not empresas_tyasa.empty else "—"

            render_kpi_row([
                {"label": f"Volumen nacional CANACERO — Importación ({periodo_canacero_sel})", "value": round(vol_nacional_ton), "suffix": " ton"},
                {"label": f"Reportado en avisos SNICE ({periodo_sel})", "value": round(vol_snice_ton), "suffix": " ton"},
                {"label": "Cobertura SNICE / CANACERO", "value": round(cobertura_pct, 1), "suffix": " %"},
                {"label": "Empresa líder (SNICE)", "value": empresa_top},
            ])
        else:
            # SNICE son avisos automáticos de IMPORTACIÓN únicamente — no existe un
            # equivalente de exportación en esa fuente. Comparar "cobertura" contra
            # un volumen de exportación de CANACERO no tendría sentido (compararía
            # cosas distintas), así que con Exportación seleccionada solo mostramos
            # el dato que sí es válido por sí solo: el total nacional CANACERO.
            empresas_tyasa = pd.DataFrame()
            render_kpi_row([
                {"label": f"Volumen nacional CANACERO — Exportación ({periodo_canacero_sel})", "value": round(vol_nacional_ton), "suffix": " ton"},
            ])
            st.caption("SNICE no tiene datos de exportación.")

        st.divider()
        st.markdown("##### CANACERO vs. SNICE vs. TYASA (siempre Importación)")

        serie_canacero = load_serie_tiempo_tyasa("IMPORTACION", fracciones=fracciones_filtro)[["periodo_mes", "volumen_total"]]
        serie_canacero["serie"] = "CANACERO — nacional, catálogo TYASA (Importación)"

        serie_snice_total = load_serie_tyasa_gold(fracciones_exactas_snice, fracciones_prefijo_snice)
        serie_snice_total = serie_snice_total.rename(columns={"periodo": "periodo_mes"})[["periodo_mes", "volumen_total"]]
        serie_snice_total["volumen_total"] = serie_snice_total["volumen_total"] / 1000
        serie_snice_total["serie"] = "SNICE — nacional, catálogo TYASA"

        serie_tyasa = load_serie_empresa_gold(RAZON_SOCIAL_TYASA_SNICE)
        serie_tyasa = serie_tyasa.rename(columns={"periodo": "periodo_mes"})[["periodo_mes", "volumen_total"]]
        serie_tyasa["volumen_total"] = serie_tyasa["volumen_total"].fillna(0) / 1000
        serie_tyasa["serie"] = f"SNICE — TYASA ({RAZON_SOCIAL_TYASA_SNICE})"

        serie_comparativa = pd.concat([serie_canacero, serie_snice_total], ignore_index=True)

        col_nac, col_part = st.columns(2)
        with col_nac:
            st.plotly_chart(
                linea_temporal(
                    serie_comparativa, x="periodo_mes", y="volumen_total", color="serie",
                    titulo="Importación nacional del catálogo TYASA",
                    y_label="Ton", height=400,
                ),
                width="stretch",
            )
            st.caption("CANACERO: lo que realmente entró. SNICE: lo que se avisó que iba a entrar.")

        with col_part:
            # TYASA pesa ~5-10% de lo importado: en la misma escala que el total
            # nacional su línea quedaba pegada al cero, así que va en su propia
            # gráfica como porcentaje. Siempre contra el catálogo COMPLETO: la serie
            # de TYASA (GOLD_SNICE_TOP_EMPRESAS) no distingue fracción, así que
            # dividirla entre un subconjunto filtrado inflaría la participación.
            if serie_tyasa.empty:
                st.info("Sin avisos SNICE de TYASA todavía.")
            else:
                snice_catalogo = load_serie_tyasa_gold(FRACCIONES_TYASA_T, FRACCIONES_TYASA_PREFIJO_T)
                part = snice_catalogo.rename(columns={"periodo": "periodo_mes", "volumen_total": "snice_ton"})
                part = part[["periodo_mes", "snice_ton"]].copy()
                part["snice_ton"] = part["snice_ton"] / 1000
                part = part.merge(
                    serie_tyasa[["periodo_mes", "volumen_total"]].rename(columns={"volumen_total": "tyasa_ton"}),
                    on="periodo_mes", how="left",
                )
                part = part[part["periodo_mes"] >= serie_tyasa["periodo_mes"].min()].copy()
                part["tyasa_ton"] = part["tyasa_ton"].fillna(0)
                part["participacion"] = (part["tyasa_ton"] / part["snice_ton"] * 100).where(part["snice_ton"] > 0)
                part = part.dropna(subset=["participacion"]).sort_values("periodo_mes")
                # TYASA tramita avisos por lotes (meses en 0 y luego picos), así que
                # el dato mensual brinca mucho; la tendencia se lee en la
                # participación anualizada: 12 meses de TYASA / 12 meses del total.
                part["participacion_12m"] = (
                    part["tyasa_ton"].rolling(12, min_periods=12).sum()
                    / part["snice_ton"].rolling(12, min_periods=12).sum() * 100
                )
                part["detalle"] = part.apply(
                    lambda r: f"· {r['tyasa_ton']:,.0f} t de {r['snice_ton']:,.0f} t", axis=1,
                )
                st.plotly_chart(
                    barras_con_tendencia(
                        part, x="periodo_mes", y_barras="participacion", y_linea="participacion_12m",
                        titulo="Participación de TYASA en lo importado (SNICE)", y_label="",
                        nombre_barras="Mes", nombre_linea="Últimos 12 meses", hover_extra="detalle",
                        sufijo="%", height=400,
                    ),
                    width="stretch",
                )
                ultimo_part = part.iloc[-1]
                st.caption(
                    f"{ultimo_part['periodo_mes']}: TYASA avisó {ultimo_part['tyasa_ton']:,.0f} t de "
                    f"{ultimo_part['snice_ton']:,.0f} t ({ultimo_part['participacion']:.1f}%)."
                    + ("" if usa_catalogo_completo else " Se calcula contra todo el catálogo, no solo las fracciones elegidas.")
                )

        st.markdown("###### Top 5 fracciones del mes")
        c_top5_sel, _ = st.columns([1, 3])
        with c_top5_sel:
            periodo_top5_sel = st.selectbox(
                "Periodo a comparar", periodos_canacero, index=0, key="snice_top5_periodo",
            )

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            idx_can = periodos_canacero.index(periodo_top5_sel)
            prev_can = periodos_canacero[idx_can + 1] if idx_can + 1 < len(periodos_canacero) else None
            top_can = load_top_fracciones_tyasa(
                periodo_top5_sel, "IMPORTACION", limite=500, fracciones=fracciones_filtro,
            ).rename(columns={"volumen_total": "volumen_ton"})
            prev_can_df = (
                load_top_fracciones_tyasa(prev_can, "IMPORTACION", limite=500, fracciones=fracciones_filtro)
                .rename(columns={"volumen_total": "volumen_ton"})
                if prev_can else None
            )
            st.html(
                _card_open(f"CANACERO — {periodo_top5_sel}",
                           f"Importación nacional · variación vs. {prev_can or 'mes anterior'}")
                + _top_fracciones_html(top_can, prev_can_df) + _CARD_CLOSE
            )

        with col_t2:
            def _snice_por_fraccion(periodo: str) -> pd.DataFrame:
                df = load_top_fracciones_tyasa_gold(periodo, fracciones_exactas_snice, fracciones_prefijo_snice)
                if df.empty:
                    return pd.DataFrame(columns=["fraccion", "volumen_ton"])
                df = df.assign(fraccion=df["fraccion_arancelaria"].str[:8], volumen_ton=df["volumen_total"] / 1000)
                return df.groupby("fraccion", as_index=False)["volumen_ton"].sum()

            previos_snice = [p for p in periodos if p < periodo_top5_sel]
            prev_snice = max(previos_snice) if previos_snice else None
            st.html(
                _card_open(f"SNICE (avisos) — {periodo_top5_sel}",
                           f"Lo que se avisó · variación vs. {prev_snice or 'mes anterior'}")
                + _top_fracciones_html(
                    _snice_por_fraccion(periodo_top5_sel),
                    _snice_por_fraccion(prev_snice) if prev_snice else None,
                )
                + _CARD_CLOSE
            )

        # ── Origen de las importaciones (SNICE, por país) ──────────────────
        st.divider()
        st.markdown("##### Origen de las importaciones (SNICE)")
        prev_bronze = _periodo_anterior_bronze(periodo_sel) if en_ventana else None
        if not en_ventana:
            st.info(f"{periodo_sel} ya no tiene detalle por país. Elige un periodo más reciente en el filtro de arriba.")
        else:
            st.caption(
                f"De dónde viene el acero del catálogo TYASA — {periodo_sel}"
                + (f" contra {prev_bronze}." if prev_bronze else ".")
            )
            paises_act = load_paises_fracciones(periodo_sel, fracciones_exactas_snice, fracciones_prefijo_snice)
            paises_ant = (
                load_paises_fracciones(prev_bronze, fracciones_exactas_snice, fracciones_prefijo_snice)
                if prev_bronze else pd.DataFrame()
            )
            if paises_act.empty:
                st.info("Sin avisos con país de origen para este periodo.")
            else:
                def _por_pais(df: pd.DataFrame) -> pd.DataFrame:
                    out = df.assign(pais=df["pais_origen"].map(_pais_corto), volumen_ton=df["volumen_total"] / 1000)
                    out = out.groupby("pais", as_index=False).agg(
                        volumen_ton=("volumen_ton", "sum"), empresas=("empresas_distintas", "sum"),
                    )
                    out["share"] = out["volumen_ton"] / (out["volumen_ton"].sum() or 1) * 100
                    return out.sort_values("volumen_ton", ascending=False)

                pa = _por_pais(paises_act)
                pp = _por_pais(paises_ant) if not paises_ant.empty else pd.DataFrame(columns=pa.columns)

                # El color sigue al país: los 6 principales de ESTE mes, en el
                # mismo orden y color en ambas barras; el resto se junta en "Otros".
                principales = pa["pais"].head(6).tolist()
                filas_estr = []
                for etiqueta, df_p in ((prev_bronze, pp), (periodo_sel, pa)):
                    if etiqueta is None or df_p.empty:
                        continue
                    tmp = df_p.assign(categoria=df_p["pais"].where(df_p["pais"].isin(principales), "Otros"), fila=etiqueta)
                    filas_estr.append(tmp)
                estr = pd.concat(filas_estr, ignore_index=True)
                estr["orden"] = estr["categoria"].map({p: i for i, p in enumerate(principales)}).fillna(99)
                estr = estr.sort_values("orden")

                col_estr, col_china = st.columns([1.6, 1])
                with col_estr:
                    st.plotly_chart(
                        estructura_100(
                            estr, fila="fila", categoria="categoria", valor="volumen_ton",
                            titulo="Estructura por país de origen (% del volumen)",
                            orden_filas=[f for f in (prev_bronze, periodo_sel) if f in set(estr["fila"])],
                            height=260,
                        ),
                        width="stretch",
                    )

                    previo_share = pp.set_index("pais")["share"] if not pp.empty else None
                    filas_html = []
                    for r in pa.head(8).itertuples():
                        ant = float(previo_share.get(r.pais, 0)) if previo_share is not None else None
                        filas_html.append(
                            f"<tr><td style='padding:5px 8px;'>{r.pais}</td>"
                            f"<td style='padding:5px 8px;text-align:right;'>{r.volumen_ton:,.0f} t</td>"
                            f"<td style='padding:5px 8px;text-align:right;font-weight:700;'>{r.share:.1f}%</td>"
                            f"<td style='padding:5px 8px;text-align:right;'>{_flecha_pp(r.share, ant)}</td></tr>"
                        )
                    st.html(
                        f"<table style='width:100%;border-collapse:collapse;font-size:0.8rem;color:{COLORS['text']};'>"
                        f"<tr style='color:{COLORS['text_light']};font-size:0.72rem;text-transform:uppercase;'>"
                        f"<th style='text-align:left;padding:4px 8px;'>País</th><th style='text-align:right;padding:4px 8px;'>Volumen</th>"
                        f"<th style='text-align:right;padding:4px 8px;'>Part.</th>"
                        f"<th style='text-align:right;padding:4px 8px;'>vs. {prev_bronze or '—'}</th></tr>"
                        + "".join(filas_html) + "</table>"
                    )

                with col_china:
                    china = pa[pa["pais"] == "China"]
                    china_ant = pp[pp["pais"] == "China"] if not pp.empty else pd.DataFrame()
                    ton_cn = float(china["volumen_ton"].sum())
                    share_cn = float(china["share"].sum())
                    ton_cn_ant = float(china_ant["volumen_ton"].sum()) if prev_bronze else None
                    share_cn_ant = float(china_ant["share"].sum()) if prev_bronze else None
                    lugar_cn = (pa["pais"].tolist().index("China") + 1) if not china.empty else None
                    st.html(
                        _card_open("Acero chino", f"Catálogo TYASA · {periodo_sel}")
                        + f"<div style='font-size:2rem;font-weight:700;color:{COLORS['primary']};line-height:1.1;'>{ton_cn:,.0f} t</div>"
                        + f"<div style='font-size:0.82rem;margin:4px 0 14px;'>{_flecha_pct(ton_cn, ton_cn_ant)}"
                        + (f" <span style='color:{COLORS['text_light']};'>vs. {prev_bronze}</span>" if prev_bronze else "")
                        + "</div>"
                        + f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;'>"
                        + f"<div style='background:{COLORS['background']};border-radius:10px;padding:10px 12px;'>"
                        + f"<div style='font-size:0.7rem;color:{COLORS['text_light']};text-transform:uppercase;'>Participación</div>"
                        + f"<div style='font-size:1.25rem;font-weight:700;color:{COLORS['text']};'>{share_cn:.1f}%</div>"
                        + f"<div style='font-size:0.75rem;'>{_flecha_pp(share_cn, share_cn_ant)}</div></div>"
                        + f"<div style='background:{COLORS['background']};border-radius:10px;padding:10px 12px;'>"
                        + f"<div style='font-size:0.7rem;color:{COLORS['text_light']};text-transform:uppercase;'>Lugar</div>"
                        + f"<div style='font-size:1.25rem;font-weight:700;color:{COLORS['text']};'>{f'#{lugar_cn}' if lugar_cn else '—'}</div>"
                        + f"<div style='font-size:0.75rem;color:{COLORS['text_light']};'>de {len(pa)} países</div></div>"
                        + "</div>" + _CARD_CLOSE
                    )

        # ── Importadores que más cambiaron (SNICE) ─────────────────────────
        st.divider()
        st.markdown("##### Importadores que más cambiaron (SNICE)")
        if not en_ventana or not prev_bronze:
            st.info("Se necesitan dos meses con detalle por empresa para comparar. Elige el periodo más reciente arriba.")
        else:
            st.caption(f"Cambio en toneladas avisadas: {periodo_sel} contra {prev_bronze}.")
            emp_act = load_empresas_fracciones(periodo_sel, fracciones_exactas_snice, fracciones_prefijo_snice, limite=2000)
            emp_ant = load_empresas_fracciones(prev_bronze, fracciones_exactas_snice, fracciones_prefijo_snice, limite=2000)
            comp_emp = (
                emp_act[["razon_social", "volumen_total"]].rename(columns={"volumen_total": "actual"})
                .merge(emp_ant[["razon_social", "volumen_total"]].rename(columns={"volumen_total": "anterior"}),
                       on="razon_social", how="outer")
                .fillna(0)
            )
            comp_emp[["actual", "anterior"]] = comp_emp[["actual", "anterior"]] / 1000
            comp_emp["delta"] = comp_emp["actual"] - comp_emp["anterior"]
            comp_emp["empresa"] = comp_emp["razon_social"].map(_empresa_corta)

            ganadores = comp_emp[comp_emp["delta"] > 0].nlargest(8, "delta")
            perdedores = comp_emp[comp_emp["delta"] < 0].nsmallest(8, "delta")
            st.plotly_chart(
                barras_divergentes(
                    pd.concat([ganadores, perdedores]), x="delta", y="empresa",
                    titulo="Los 8 que más subieron y los 8 que más bajaron", x_label="Ton (cambio)",
                    resaltar="TYASA",
                ),
                width="stretch",
            )
            fila_tyasa = comp_emp[comp_emp["razon_social"].str.upper() == RAZON_SOCIAL_TYASA_SNICE.upper()]
            if not fila_tyasa.empty:
                ft = fila_tyasa.iloc[0]
                st.caption(
                    f"TYASA: {ft['anterior']:,.0f} t → {ft['actual']:,.0f} t "
                    f"({'+' if ft['delta'] >= 0 else '−'}{abs(ft['delta']):,.0f} t)."
                )
            else:
                st.caption("TYASA no tuvo avisos en ninguno de los dos meses.")

        st.divider()
        st.markdown("##### Consumo aparente en México (Importación − Exportación)")

        serie_imp_neto = load_serie_tiempo_tyasa("IMPORTACION", fracciones=fracciones_filtro)[["periodo_mes", "volumen_total"]]
        serie_exp_neto = load_serie_tiempo_tyasa("EXPORTACION", fracciones=fracciones_filtro)[["periodo_mes", "volumen_total"]]

        if serie_exp_neto.empty:
            st.info(
                "Todavía no hay datos de EXPORTACIÓN de CANACERO cargados — sube un CSV de "
                "exportación arriba ('Cargar nuevo periodo de CANACERO') para activar esta sección."
            )
        else:
            neto_df = serie_imp_neto.rename(columns={"volumen_total": "importacion"}).merge(
                serie_exp_neto.rename(columns={"volumen_total": "exportacion"}), on="periodo_mes", how="inner",
            ).sort_values("periodo_mes")
            periodos_con_ambos = sorted(neto_df["periodo_mes"].unique().tolist())
            st.caption("Importación menos exportación — lo que se queda en México.")
            if neto_df.empty:
                st.info("Sin meses con importación y exportación cargadas a la vez todavía.")
            else:
                neto_df["neto"] = neto_df["importacion"] - neto_df["exportacion"]
                neto_df["pct_reexportado"] = (
                    (neto_df["exportacion"] / neto_df["importacion"] * 100).where(neto_df["importacion"] > 0)
                )

                ultimo = neto_df.iloc[-1]
                render_kpi_row([
                    {"label": f"Importación ({ultimo['periodo_mes']})", "value": round(ultimo["importacion"]), "suffix": " ton"},
                    {"label": f"Exportación ({ultimo['periodo_mes']})", "value": round(ultimo["exportacion"]), "suffix": " ton"},
                    {"label": "Consumo aparente (neto)", "value": round(ultimo["neto"]), "suffix": " ton"},
                    {
                        "label": "% reexportado",
                        "value": round(ultimo["pct_reexportado"], 1) if pd.notna(ultimo["pct_reexportado"]) else "N/D",
                        "suffix": " %",
                    },
                ])

                col_neto, col_top5_ie = st.columns([2, 1])
                with col_neto:
                    st.plotly_chart(
                        espejo_flujos(
                            neto_df, x="periodo_mes", entra="importacion", sale="exportacion", neto="neto",
                            titulo="Lo que entra, lo que sale y lo que se queda — catálogo TYASA",
                            nombre_neto="Consumo aparente (neto)",
                        ),
                        width="stretch",
                    )
                    st.caption("Barras arriba: importación. Barras abajo: exportación. Línea: lo que se queda.")

                with col_top5_ie:
                    st.markdown("###### Top 5 fracciones por movimiento")
                    periodo_ie_sel = st.selectbox(
                        "Periodo", periodos_con_ambos, index=len(periodos_con_ambos) - 1, key="snice_top5_ie_periodo",
                    )
                    idx_ie = periodos_con_ambos.index(periodo_ie_sel)
                    prev_ie = periodos_con_ambos[idx_ie - 1] if idx_ie > 0 else None

                    def _top_mov(periodo: str | None, movimiento: str) -> pd.DataFrame | None:
                        if not periodo:
                            return None
                        return load_top_fracciones_tyasa(
                            periodo, movimiento, limite=500, fracciones=fracciones_filtro,
                        ).rename(columns={"volumen_total": "volumen_ton"})

                    for mov, nombre in (("IMPORTACION", "Importación"), ("EXPORTACION", "Exportación")):
                        st.html(
                            _card_open(f"{nombre} — {periodo_ie_sel}", f"Variación vs. {prev_ie or 'mes anterior'}")
                            + _top_fracciones_html(_top_mov(periodo_ie_sel, mov), _top_mov(prev_ie, mov))
                            + _CARD_CLOSE
                        )

        st.divider()
        st.markdown("##### Intención de importación (por vigencia del permiso)")
        st.caption("Qué avisos siguen vigentes ese mes, aunque se hayan tramitado antes.")

        mes_min, mes_max = load_rango_vigencia_disponible(fracciones_exactas_snice, fracciones_prefijo_snice)
        if not mes_min:
            st.info("Sin datos de vigencia disponibles todavía.")
        else:
            meses_disponibles = pd.period_range(mes_min, mes_max, freq="M").astype(str).tolist()
            mes_hoy = pd.Timestamp.today().strftime("%Y-%m")
            mes_sel = st.selectbox(
                "Mes a proyectar", meses_disponibles,
                index=meses_disponibles.index(mes_hoy) if mes_hoy in meses_disponibles else len(meses_disponibles) - 1,
                key="snice_mes_vigencia",
            )
            resumen_mes = load_resumen_vigentes_en_mes(mes_sel, fracciones_exactas_snice, fracciones_prefijo_snice)
            if not resumen_mes or not resumen_mes.get("avisos"):
                st.info(f"Sin avisos con vigencia en {mes_sel}.")
            else:
                render_kpi_row([
                    {"label": f"Volumen con vigencia en {mes_sel}", "value": round((resumen_mes.get("volumen_total") or 0) / 1000), "suffix": " ton"},
                    {"label": "Avisos vigentes ese mes", "value": int(resumen_mes.get("avisos") or 0)},
                    {"label": "Empresas", "value": int(resumen_mes.get("empresas_distintas") or 0)},
                    {"label": "Países", "value": int(resumen_mes.get("paises_distintos") or 0)},
                ])

                serie_vig = pd.DataFrame({"mes": meses_disponibles})
                serie_vig["volumen_ton"] = serie_vig["mes"].map(
                    lambda m: (load_resumen_vigentes_en_mes(m, fracciones_exactas_snice, fracciones_prefijo_snice) or {})
                    .get("volumen_total") or 0
                ) / 1000
                st.plotly_chart(
                    barras_resaltada(
                        serie_vig, x="mes", y="volumen_ton", resaltar=mes_sel,
                        titulo="Volumen con permiso vigente, mes por mes", height=260,
                    ),
                    width="stretch",
                )

                col_v1, col_v2 = st.columns([1, 1.2])
                with col_v1:
                    fracciones_mes = load_fracciones_vigentes_en_mes(mes_sel, fracciones_exactas_snice, fracciones_prefijo_snice)
                    fracciones_mes = fracciones_mes.copy()
                    fracciones_mes["etiqueta"] = fracciones_mes["fraccion_arancelaria"].map(
                        lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}"
                    )
                    fracciones_mes["volumen_ton"] = fracciones_mes["volumen_total"] / 1000
                    st.plotly_chart(
                        barras_horizontales(
                            fracciones_mes, x="volumen_ton", y="etiqueta",
                            titulo=f"Qué fracciones tienen vigencia en {mes_sel}", x_label="Ton", max_items=12,
                        ),
                        width="stretch",
                    )
                avisos_mes = load_avisos_vigentes_en_mes(
                    mes_sel, fracciones_exactas_snice, fracciones_prefijo_snice, limite=200,
                )
                with col_v2:
                    gantt = avisos_mes.nlargest(12, "volumen_aviso").copy()
                    gantt["volumen_ton"] = gantt["volumen_aviso"] / 1000
                    gantt["etiqueta"] = (
                        gantt["razon_social"].map(_empresa_corta) + " · " + gantt["fraccion_arancelaria"]
                    )
                    # Dos avisos de la misma empresa y fracción tendrían la misma
                    # etiqueta y se encimarían en una sola fila.
                    dup = gantt.groupby("etiqueta").cumcount()
                    gantt.loc[dup > 0, "etiqueta"] += dup[dup > 0].map(lambda k: f" ({k + 1})")
                    st.plotly_chart(
                        linea_vigencias(
                            gantt, inicio="inicio_vigencia", fin="fin_vigencia", etiqueta="etiqueta",
                            valor="volumen_ton", mes=mes_sel,
                            titulo=f"Los avisos más grandes vigentes en {mes_sel} y cuándo vencen",
                        ),
                        width="stretch",
                    )

                tabla_v = avisos_mes.copy()
                tabla_v["volumen_aviso"] = tabla_v["volumen_aviso"] / 1000
                tabla_v = tabla_v.rename(columns={
                    "razon_social": "Razón social", "fraccion_arancelaria": "Fracción",
                    "pais_origen": "País", "volumen_aviso": "Volumen (ton)",
                    "inicio_vigencia": "Inicio vigencia", "fin_vigencia": "Fin vigencia",
                })
                st.dataframe(
                    tabla_v[["Razón social", "Fracción", "País", "Volumen (ton)", "Inicio vigencia", "Fin vigencia"]],
                    hide_index=True, width="stretch", height=300,
                    column_config={
                        "Volumen (ton)": st.column_config.ProgressColumn(
                            format="%.1f", min_value=0, max_value=float(tabla_v["Volumen (ton)"].max() or 1),
                        ),
                        "Inicio vigencia": st.column_config.DateColumn(format="DD/MM/YYYY"),
                        "Fin vigencia": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    },
                )

        st.divider()
        st.markdown(f"##### Comparación por cuatrimestre (CANACERO — {movimiento_dash_label})")
        st.caption("Compara el cuatrimestre elegido contra el anterior, por fracción.")

        series_frac = load_series_fracciones_tyasa(movimiento_dash)
        if fracciones_filtro:
            series_frac = series_frac[series_frac["fraccion"].isin(fracciones_filtro)]

        if series_frac.empty:
            st.info("Sin histórico CANACERO por fracción todavía.")
        else:
            _CUATRI_LABEL = {0: "Ene-Abr", 1: "May-Ago", 2: "Sep-Dic"}
            series_frac = series_frac.copy()
            partes = series_frac["periodo_mes"].str.split("-", expand=True)
            series_frac["anio"] = partes[0].astype(int)
            series_frac["bloque"] = (partes[1].astype(int) - 1) // 4
            series_frac["cuatrimestre"] = series_frac["anio"].astype(str) + " " + series_frac["bloque"].map(_CUATRI_LABEL)

            cuatrimestres = (
                series_frac[["anio", "bloque", "cuatrimestre"]].drop_duplicates().sort_values(["anio", "bloque"])
            )
            opciones_cuatri = cuatrimestres["cuatrimestre"].tolist()
            cuatri_sel = st.selectbox(
                "Cuatrimestre a analizar", opciones_cuatri, index=len(opciones_cuatri) - 1, key="snice_cuatri_sel",
            )
            idx_sel = opciones_cuatri.index(cuatri_sel)
            if idx_sel == 0:
                st.info(f"{cuatri_sel} es el primer cuatrimestre con datos — no hay uno anterior para comparar.")
            else:
                cuatri_anterior = opciones_cuatri[idx_sel - 1]
                anio_sel, bloque_sel = cuatrimestres.iloc[idx_sel][["anio", "bloque"]]
                anio_ant, bloque_ant = cuatrimestres.iloc[idx_sel - 1][["anio", "bloque"]]

                actual = series_frac[(series_frac["anio"] == anio_sel) & (series_frac["bloque"] == bloque_sel)]
                anterior = series_frac[(series_frac["anio"] == anio_ant) & (series_frac["bloque"] == bloque_ant)]

                agg_actual = actual.groupby("fraccion", as_index=False)["volumen_total"].sum().rename(columns={"volumen_total": "actual"})
                agg_anterior = anterior.groupby("fraccion", as_index=False)["volumen_total"].sum().rename(columns={"volumen_total": "anterior"})
                comp = agg_actual.merge(agg_anterior, on="fraccion", how="outer").fillna(0)
                comp["delta_ton"] = comp["actual"] - comp["anterior"]
                comp["delta_pct"] = comp.apply(
                    lambda r: (r["delta_ton"] / r["anterior"] * 100) if r["anterior"] else (100.0 if r["actual"] else 0.0),
                    axis=1,
                )
                comp["direccion"] = comp["delta_ton"].map(lambda d: "▲ Aumentó" if d > 0 else ("▼ Disminuyó" if d < 0 else "= Sin cambio"))
                comp["etiqueta"] = comp["fraccion"].map(lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}")
                comp = comp.reindex(comp["delta_ton"].abs().sort_values(ascending=False).index)

                total_actual = comp["actual"].sum()
                total_anterior = comp["anterior"].sum()
                delta_total_pct = (total_actual - total_anterior) / total_anterior * 100 if total_anterior else 0

                render_kpi_row([
                    {"label": cuatri_anterior, "value": round(total_anterior), "suffix": " ton"},
                    {"label": cuatri_sel, "value": round(total_actual), "suffix": " ton"},
                    {"label": "Variación total", "value": round(delta_total_pct, 1), "suffix": " %"},
                ])

                comp_chart = comp[comp["delta_ton"] != 0].head(15).copy()
                comp_chart["etiqueta_corta"] = comp_chart["etiqueta"].map(lambda e: e if len(e) <= 60 else e[:59] + "…")
                st.plotly_chart(
                    barras_divergentes(
                        comp_chart, x="delta_ton", y="etiqueta_corta",
                        titulo=f"Mayores variaciones ({movimiento_dash_label}): {cuatri_sel} vs. {cuatri_anterior}",
                        x_label="Ton (cambio)",
                    ),
                    width="stretch",
                )
                st.caption("A la derecha las que subieron, a la izquierda las que bajaron.")

                tabla_comp = comp[["etiqueta", "anterior", "actual", "delta_ton", "delta_pct", "direccion"]].copy()
                tabla_comp.columns = [
                    "Fracción", f"{cuatri_anterior} (ton)", f"{cuatri_sel} (ton)",
                    "Variación (ton)", "Variación (%)", "Dirección",
                ]
                st.dataframe(
                    tabla_comp.style
                    .format({
                        f"{cuatri_anterior} (ton)": "{:,.1f}", f"{cuatri_sel} (ton)": "{:,.1f}",
                        "Variación (ton)": "{:+,.1f}", "Variación (%)": "{:+.1f}%",
                    })
                    .map(_color_signo, subset=["Variación (ton)", "Variación (%)"]),
                    hide_index=True, width="stretch", height=360,
                )

                st.markdown(f"###### Precio unitario — mismos cuatrimestres ({movimiento_dash_label})")
                st.caption("Precio promedio por fracción en cada cuatrimestre.")

                def _concentracion_mensual(df_cuatri: pd.DataFrame) -> pd.Series:
                    """Para cada fracción: qué fracción de su volumen del cuatrimestre
                    vino del mes más grande de ese cuatrimestre (1.0 = un solo mes
                    explica el 100%)."""
                    agg = df_cuatri.groupby("fraccion")["volumen_total"].agg(["sum", "max"])
                    return (agg["max"] / agg["sum"]).rename("concentracion")

                concentracion_actual = _concentracion_mensual(actual)
                concentracion_anterior = _concentracion_mensual(anterior)

                # Volatilidad histórica (coeficiente de variación = std/mean del precio
                # mensual) usando TODO el histórico disponible, no solo los dos
                # cuatrimestres comparados — para saber si una fracción es, en general,
                # ruidosa (ej. 72142001: precio entre $423 y $4,762/ton en 66 meses,
                # CV≈0.61) o estable (ej. 72071291: $545-$615/ton, CV≈0.03) ANTES de
                # ver si esta comparación en particular dio una variación grande.
                precio_hist = series_frac[
                    (series_frac["volumen_total"] >= VOLUMEN_MINIMO_PARA_PRECIO)
                ].copy()
                precio_hist["precio_usd_ton"] = precio_hist["valor_total"] / precio_hist["volumen_total"]
                precio_hist = precio_hist[precio_hist["precio_usd_ton"] >= PRECIO_MINIMO_PLAUSIBLE_USD_TON]
                volatilidad_historica = (
                    precio_hist.groupby("fraccion")["precio_usd_ton"].agg(["mean", "std"])
                    .assign(cv=lambda d: d["std"] / d["mean"])["cv"]
                )

                precio_actual_cuatri = actual.groupby("fraccion", as_index=False).agg(
                    volumen=("volumen_total", "sum"), valor=("valor_total", "sum"),
                )
                precio_actual_cuatri = precio_actual_cuatri[precio_actual_cuatri["volumen"] >= VOLUMEN_MINIMO_PARA_PRECIO]
                precio_actual_cuatri["precio_actual"] = precio_actual_cuatri["valor"] / precio_actual_cuatri["volumen"]
                precio_actual_cuatri = precio_actual_cuatri[precio_actual_cuatri["precio_actual"] >= PRECIO_MINIMO_PLAUSIBLE_USD_TON]

                precio_anterior_cuatri = anterior.groupby("fraccion", as_index=False).agg(
                    volumen=("volumen_total", "sum"), valor=("valor_total", "sum"),
                )
                precio_anterior_cuatri = precio_anterior_cuatri[precio_anterior_cuatri["volumen"] >= VOLUMEN_MINIMO_PARA_PRECIO]
                precio_anterior_cuatri["precio_anterior"] = precio_anterior_cuatri["valor"] / precio_anterior_cuatri["volumen"]
                precio_anterior_cuatri = precio_anterior_cuatri[precio_anterior_cuatri["precio_anterior"] >= PRECIO_MINIMO_PLAUSIBLE_USD_TON]

                precio_comp = precio_actual_cuatri[["fraccion", "precio_actual"]].merge(
                    precio_anterior_cuatri[["fraccion", "precio_anterior"]], on="fraccion", how="inner",
                )
                if precio_comp.empty:
                    st.info("Sin fracciones con volumen en ambos cuatrimestres para comparar precio.")
                else:
                    precio_comp["delta_precio_pct"] = (
                        (precio_comp["precio_actual"] - precio_comp["precio_anterior"]) / precio_comp["precio_anterior"] * 100
                    )
                    precio_comp["etiqueta"] = precio_comp["fraccion"].map(
                        lambda f: f"{f} — {FRACCIONES_TYASA_DESCRIPCION.get(f, 'sin descripción')}"
                    )
                    precio_comp["concentracion_max"] = precio_comp["fraccion"].map(
                        lambda f: max(
                            concentracion_actual.get(f, 0.0), concentracion_anterior.get(f, 0.0),
                        )
                    )
                    precio_comp["volatilidad"] = precio_comp["fraccion"].map(
                        lambda f: volatilidad_historica.get(f)
                    )
                    precio_comp["confiable"] = (
                        (precio_comp["concentracion_max"] <= UMBRAL_CONCENTRACION_MENSUAL)
                        & (precio_comp["volatilidad"].fillna(999) <= UMBRAL_VOLATILIDAD_HISTORICA)
                    )
                    # Primero las confiables (ordenadas por variación), luego las no
                    # confiables — para no encabezar la tabla con ruido estadístico.
                    precio_comp = precio_comp.sort_values(
                        by=["confiable", "delta_precio_pct"],
                        key=lambda s: s.abs() if s.name == "delta_precio_pct" else s,
                        ascending=[False, False],
                    )

                    top_precio_chart = precio_comp[precio_comp["confiable"]].head(10).copy()
                    top_precio_chart["etiqueta_corta"] = top_precio_chart["etiqueta"].map(
                        lambda e: e if len(e) <= 55 else e[:54] + "…"
                    )
                    if top_precio_chart.empty:
                        st.info(
                            "Ninguna fracción con variación de precio en este periodo pasó el filtro de "
                            "confiabilidad (concentración en 1 mes y/o volatilidad histórica alta) — ver "
                            "la tabla de abajo, o la gráfica de histórico mensual más abajo en la página."
                        )
                    else:
                        st.plotly_chart(
                            cambio_puntos(
                                top_precio_chart, y="etiqueta_corta", antes="precio_anterior", despues="precio_actual",
                                titulo=f"Mayor variación de precio unitario ({movimiento_dash_label}): {cuatri_sel} vs. {cuatri_anterior}",
                                nombre_antes=cuatri_anterior, nombre_despues=cuatri_sel, sufijo="/t",
                            ),
                            width="stretch",
                        )
                        st.caption("Punto gris: precio antes. Punto de color: precio ahora (azul subió, naranja bajó).")
                    st.caption("Ver histórico completo de una fracción en 'Precio unitario CANACERO' más abajo.")

                    def _motivo_no_confiable(row) -> str:
                        motivos = []
                        if row["concentracion_max"] > UMBRAL_CONCENTRACION_MENSUAL:
                            motivos.append("concentrado en 1 mes")
                        if pd.isna(row["volatilidad"]) or row["volatilidad"] > UMBRAL_VOLATILIDAD_HISTORICA:
                            motivos.append("histórico muy volátil")
                        return "⚠ " + " + ".join(motivos) if motivos else ""

                    tabla_precio = precio_comp[
                        ["etiqueta", "precio_anterior", "precio_actual", "delta_precio_pct", "volatilidad", "confiable"]
                    ].copy()
                    tabla_precio["confiable"] = precio_comp.apply(_motivo_no_confiable, axis=1)
                    tabla_precio.columns = [
                        "Fracción", f"{cuatri_anterior} (USD/ton)", f"{cuatri_sel} (USD/ton)",
                        "Variación precio (%)", "Volatilidad histórica (CV)", "Confiabilidad",
                    ]
                    st.dataframe(
                        tabla_precio.style
                        .format({
                            f"{cuatri_anterior} (USD/ton)": "${:,.0f}", f"{cuatri_sel} (USD/ton)": "${:,.0f}",
                            "Variación precio (%)": "{:+.1f}%", "Volatilidad histórica (CV)": "{:.2f}",
                        }, na_rep="N/D")
                        .map(_color_signo, subset=["Variación precio (%)"])
                        .map(lambda v: "color:#92400E" if v else "", subset=["Confiabilidad"]),
                        hide_index=True, width="stretch", height=320,
                    )

        st.divider()
        st.markdown(f"##### Precio unitario CANACERO (USD/ton) — {movimiento_dash_label}")
        st.caption("Precio por tonelada, mes a mes, por fracción.")

        precio_frac = (
            series_frac[series_frac["volumen_total"] >= VOLUMEN_MINIMO_PARA_PRECIO].copy()
            if not series_frac.empty else series_frac
        )
        if not precio_frac.empty:
            precio_frac["precio_usd_ton"] = precio_frac["valor_total"] / precio_frac["volumen_total"]
            precio_frac = precio_frac[precio_frac["precio_usd_ton"] >= PRECIO_MINIMO_PLAUSIBLE_USD_TON]
        if precio_frac.empty:
            st.info("Sin datos de precio disponibles.")
        else:
            col_p1, col_p2 = st.columns([1.3, 1])
            with col_p1:
                fraccion_precio_sel = st.selectbox(
                    "Fracción", sorted(precio_frac["fraccion"].unique()),
                    format_func=lambda f: etiquetas_fraccion.get(f, f),
                    key="precio_fraccion_sel",
                )
                serie_precio = precio_frac[precio_frac["fraccion"] == fraccion_precio_sel].sort_values("periodo_mes")
                st.plotly_chart(
                    linea_con_promedio(
                        serie_precio, x="periodo_mes", y="precio_usd_ton",
                        titulo=f"Precio unitario mensual ({movimiento_dash_label}) — {etiquetas_fraccion.get(fraccion_precio_sel, fraccion_precio_sel)}",
                        prefijo="$", sufijo="/t",
                    ),
                    width="stretch",
                )
                ult_p = serie_precio.iloc[-1]
                hace_12 = (pd.Period(ult_p["periodo_mes"], freq="M") - 12).strftime("%Y-%m")
                previo_p = serie_precio[serie_precio["periodo_mes"] == hace_12]
                if not previo_p.empty:
                    var_12 = (ult_p["precio_usd_ton"] / previo_p["precio_usd_ton"].iloc[0] - 1) * 100
                    st.caption(
                        f"{ult_p['periodo_mes']}: ${ult_p['precio_usd_ton']:,.0f}/t · "
                        f"{'▲' if var_12 >= 0 else '▼'} {abs(var_12):.1f}% vs. {hace_12}."
                    )
            with col_p2:
                periodo_scatter_sel = st.selectbox(
                    "Periodo (para el scatter)", periodos_canacero, index=0, key="precio_scatter_periodo",
                )
                scatter_df = precio_frac[precio_frac["periodo_mes"] == periodo_scatter_sel].copy()
                if scatter_df.empty:
                    st.info(f"Sin datos de precio para {periodo_scatter_sel}.")
                else:
                    scatter_df["etiqueta"] = scatter_df["fraccion"].map(
                        lambda f: etiquetas_fraccion.get(f, f)
                    )
                    st.plotly_chart(
                        scatter_cuadrantes(
                            scatter_df, x="volumen_total", y="precio_usd_ton", etiqueta="etiqueta",
                            titulo=f"Volumen vs. precio unitario ({movimiento_dash_label}) — {periodo_scatter_sel}",
                            x_label="Ton (escala logarítmica)", y_label="USD/ton",
                        ),
                        width="stretch",
                    )
                    st.caption(
                        "Cada punto es una fracción; las líneas punteadas son la mediana. "
                        "Abajo a la derecha = mucho volumen a precio bajo (posible presión de oferta)."
                    )

        st.divider()
        st.markdown(f"###### Fracciones CANACERO por volumen nacional ({movimiento_dash_label})")
        st.caption("Volumen total nacional, no el de TYASA.")
        fracciones_top_full = load_top_fracciones_tyasa(
            periodo_canacero_sel, movimiento_dash, limite=100, fracciones=fracciones_filtro,
        )
        if fracciones_top_full.empty:
            st.info("Sin fracciones con movimiento en este periodo.")
        else:
            etiquetas_chart = {
                row.fraccion: (
                    f"{row.fraccion} — "
                    f"{FRACCIONES_TYASA_DESCRIPCION.get(row.fraccion, row.descripcion or 'sin descripción')}"
                )
                for row in fracciones_top_full.itertuples()
            }
            default_chart = fracciones_top_full["fraccion"].head(15).tolist()
            seleccion_chart = st.multiselect(
                "Fracciones a mostrar en la gráfica",
                fracciones_top_full["fraccion"].tolist(),
                default=default_chart,
                format_func=lambda f: etiquetas_chart[f],
                key="canacero_fracciones_chart_sel",
            )
            if not seleccion_chart:
                st.info("Selecciona al menos una fracción para graficar.")
            else:
                fracciones_top_chart = fracciones_top_full[
                    fracciones_top_full["fraccion"].isin(seleccion_chart)
                ].copy()
                idx_rank = periodos_canacero.index(periodo_canacero_sel) if periodo_canacero_sel in periodos_canacero else -1
                prev_rank = (
                    periodos_canacero[idx_rank + 1] if 0 <= idx_rank < len(periodos_canacero) - 1 else None
                )
                prev_rank_df = (
                    load_top_fracciones_tyasa(prev_rank, movimiento_dash, limite=100, fracciones=fracciones_filtro)
                    .rename(columns={"volumen_total": "volumen_ton"})
                    if prev_rank else None
                )
                st.html(
                    _card_open(
                        f"Fracciones CANACERO por volumen nacional ({movimiento_dash_label}) — {periodo_canacero_sel}",
                        f"% sobre el total del mes · variación vs. {prev_rank or 'mes anterior'}",
                    )
                    + _top_fracciones_html(
                        fracciones_top_chart.rename(columns={"volumen_total": "volumen_ton"}), prev_rank_df,
                        n=len(seleccion_chart), total=fracciones_top_full["volumen_total"].sum(),
                    )
                    + _CARD_CLOSE
                )

        st.divider()
        st.markdown(f"##### Consulta por fracción específica ({movimiento_dash_label})")
        st.caption(
            "Elige una sola fracción para ver su volumen nacional (CANACERO) y, al lado, "
            "qué empresas la están importando según SNICE."
        )

        fraccion_sel = st.selectbox(
            "Fracción TYASA", opciones_fraccion, format_func=lambda f: etiquetas_fraccion[f],
            key="canacero_fraccion_sel",
        )

        col_f1, col_f2 = st.columns([1.3, 1])
        with col_f1:
            serie_fraccion = load_serie_fraccion(fraccion_sel, movimiento_dash).sort_values("periodo_mes").copy()
            serie_fraccion["promedio_12m"] = serie_fraccion["volumen_total"].rolling(12, min_periods=6).mean()
            st.plotly_chart(
                barras_con_tendencia(
                    serie_fraccion, x="periodo_mes", y_barras="volumen_total", y_linea="promedio_12m",
                    titulo=f"Volumen nacional mensual ({movimiento_dash_label}) — {etiquetas_fraccion[fraccion_sel]}",
                    y_label="Ton", nombre_barras="Mes", nombre_linea="Promedio 12 meses",
                    sufijo=" t", decimales=0,
                ),
                width="stretch",
            )
            if len(serie_fraccion) >= 24:
                ult12 = serie_fraccion["volumen_total"].iloc[-12:].sum()
                ant12 = serie_fraccion["volumen_total"].iloc[-24:-12].sum()
                if ant12:
                    var12 = (ult12 / ant12 - 1) * 100
                    st.caption(
                        f"Últimos 12 meses: {ult12:,.0f} t · "
                        f"{'▲' if var12 >= 0 else '▼'} {abs(var12):.1f}% vs. los 12 anteriores."
                    )

        with col_f2:
            avisos_fraccion = load_avisos_fraccion_exacta(periodo_sel, fraccion_sel)
            st.markdown(f"**Avisos SNICE — {fraccion_sel}** (periodo {periodo_sel})")
            if avisos_fraccion.empty:
                st.info(
                    "Sin avisos SNICE para esta fracción en este periodo "
                    "(el detalle solo cubre los periodos que siguen en BRONZE)."
                )
            else:
                tabla_f = avisos_fraccion.copy()
                tabla_f["volumen_aviso"] = tabla_f["volumen_aviso"] / 1000
                tabla_f = tabla_f.rename(columns={
                    "razon_social": "Razón social", "pais_origen": "País",
                    "volumen_aviso": "Volumen (ton)", "fecha_tramite": "Fecha trámite",
                    "inicio_vigencia": "Inicio vigencia", "fin_vigencia": "Fin vigencia",
                })
                st.dataframe(
                    tabla_f[["Razón social", "País", "Volumen (ton)", "Fecha trámite", "Inicio vigencia", "Fin vigencia"]],
                    hide_index=True, width="stretch", height=360,
                    column_config={
                        "Volumen (ton)": st.column_config.ProgressColumn(
                            format="%.1f", min_value=0, max_value=float(tabla_f["Volumen (ton)"].max() or 1),
                        ),
                        "Fecha trámite": st.column_config.DateColumn(format="DD/MM/YYYY"),
                        "Inicio vigencia": st.column_config.DateColumn(format="DD/MM/YYYY"),
                        "Fin vigencia": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    },
                )

        with st.expander("Ranking de empresas (SNICE, fracciones TYASA)"):
            filtro_ranking = st.selectbox(
                "Filtrar por fracción (opcional)",
                ["Todas las fracciones TYASA"] + opciones_fraccion,
                format_func=lambda f: f if f == "Todas las fracciones TYASA" else etiquetas_fraccion[f],
                key="canacero_ranking_filtro_fraccion",
            )
            ranking_df = (
                empresas_tyasa if filtro_ranking == "Todas las fracciones TYASA"
                else load_empresas_fraccion_exacta(periodo_sel, filtro_ranking)
            )
            if ranking_df.empty:
                st.caption("Sin datos para este filtro.")
            else:
                tabla = ranking_df.head(30).copy()
                tabla["empresa"] = tabla["razon_social"].map(_empresa_corta)
                tabla["tag"] = tabla["razon_social"].map(
                    lambda r: "TYASA" if r.upper() == RAZON_SOCIAL_TYASA_SNICE.upper() else None
                )
                st.html(
                    _card_open("Ranking de empresas", f"Avisos SNICE · periodo {periodo_sel}")
                    + _rank_list_html(tabla, "empresa", "tag") + _CARD_CLOSE
                )
