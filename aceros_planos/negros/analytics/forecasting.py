"""
forecasting.py — Pronosticos de demanda mensual para Aceros Planos Negros.
Modelos: ETS | SARIMA | XGBoost | Naive Estacional | Auto
"""

import pandas as pd
import numpy as np
import warnings
from dataclasses import dataclass
from config import MIN_PERIODS_FORECAST


@dataclass
class ForecastResult:
    modelo: str
    historico: pd.DataFrame
    forecast: pd.DataFrame
    metricas: dict
    backtest: pd.DataFrame
    error_msg: str | None = None
    contribuciones: pd.DataFrame | None = None
    error_origen_movil: float | None = None  # WAPE (%) del modelo en la validación de origen móvil (modo auto)


def _metricas(y_real: np.ndarray, y_pred: np.ndarray) -> dict:
    y_real = np.array(y_real, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    mae  = float(np.mean(np.abs(y_real - y_pred)))
    rmse = float(np.sqrt(np.mean((y_real - y_pred) ** 2)))
    mask = y_real > 0
    mape = float(np.mean(np.abs((y_real[mask] - y_pred[mask]) / y_real[mask])) * 100) if mask.sum() > 0 else float("nan")
    return {"MAE": round(mae, 2), "MAPE (%)": round(mape, 1), "RMSE": round(rmse, 2)}


def _preparar_serie(df, col_periodo="PERIODO", col_val="PESO_TON",
                    fecha_corte=None, rellenar_huecos: bool = False) -> pd.DataFrame:
    """<fecha_corte>: última fecha con datos (p. ej. MAX(FECHAEMB)). Si no es el
    último día de su mes, ese mes está incompleto y se excluye, igual que el mes
    calendario en curso. <rellenar_huecos>: completa con 0 los meses sin
    registros dentro del rango (en ventas, sin embarques = 0 toneladas)."""
    s = df[[col_periodo, col_val]].copy()
    s.columns = ["ds", "y"]
    s["ds"] = pd.to_datetime(s["ds"])
    s["y"]  = pd.to_numeric(s["y"], errors="coerce").fillna(0).clip(lower=0)
    s = s.dropna(subset=["ds"]).sort_values("ds").reset_index(drop=True)
    if not s.empty:
        today = pd.Timestamp.now()
        current_month_start = today.to_period("M").to_timestamp()
        if s["ds"].max() >= current_month_start:
            s = s[s["ds"] < current_month_start].reset_index(drop=True)
    if not s.empty and fecha_corte is not None and not pd.isna(fecha_corte):
        corte = pd.Timestamp(fecha_corte).normalize()
        if corte < corte + pd.offsets.MonthEnd(0):  # el mes de corte no está cerrado
            s = s[s["ds"] < corte.to_period("M").to_timestamp()].reset_index(drop=True)
    if rellenar_huecos and not s.empty:
        s = s.groupby("ds", as_index=False)["y"].sum()
        rango = pd.date_range(s["ds"].min(), s["ds"].max(), freq="MS")
        s = s.set_index("ds").reindex(rango, fill_value=0).rename_axis("ds").reset_index()
    return s


def _build_hist_fc(serie, fc_values, lower, upper) -> pd.DataFrame:
    last_date = serie["ds"].max()
    h = len(fc_values)
    future_dates = pd.date_range(start=last_date + pd.offsets.MonthBegin(1), periods=h, freq="MS")
    hist_part = serie[["ds", "y"]].rename(columns={"y": "yhat"}).copy()
    hist_part["yhat_lower"] = np.nan
    hist_part["yhat_upper"] = np.nan
    fc_part = pd.DataFrame({
        "ds":         future_dates,
        "yhat":       np.clip(np.asarray(fc_values).ravel(), 0, None),
        "yhat_lower": np.clip(np.asarray(lower).ravel(), 0, None),
        "yhat_upper": np.asarray(upper).ravel(),
    })
    return pd.concat([hist_part, fc_part], ignore_index=True)


def _forecast_ets(serie: pd.DataFrame, horizonte: int, n_test: int | None = None) -> ForecastResult:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    serie = serie[serie["ds"] >= ETS_FECHA_INICIO].reset_index(drop=True)

    y = serie["y"].values
    n = len(y)
    n_test  = min(6, n // 5) if n_test is None else min(n_test, max(0, n - 12))
    y_train = y[:-n_test] if n_test > 0 else y
    y_test  = y[-n_test:]  if n_test > 0 else np.array([])

    seasonal = "add" if n >= 24 else None
    sp       = 12   if seasonal else None

    def _fit(arr):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                return ExponentialSmoothing(
                    arr, trend="add", seasonal=seasonal,
                    seasonal_periods=sp, initialization_method="estimated",
                    use_boxcox=False,
                ).fit(optimized=True, remove_bias=False)
            except Exception:
                return ExponentialSmoothing(arr, trend="add").fit(optimized=True)

    try:
        backtest_df, metricas = pd.DataFrame(), {}
        if n_test > 0:
            m_bt = _fit(y_train)
            p_bt = np.clip(m_bt.forecast(n_test), 0, None)
            backtest_df = pd.DataFrame({"ds": serie["ds"].iloc[-n_test:].values, "y_real": y_test, "y_pred": p_bt})
            metricas = _metricas(y_test, p_bt)

        m_full  = _fit(y)
        fc_vals = m_full.forecast(horizonte)
        residuals = np.asarray(m_full.resid)
        sigma = float(np.std(residuals)) * np.sqrt(np.arange(1, horizonte + 1))
        z90   = 1.645
        lower = fc_vals - z90 * sigma
        upper = fc_vals + z90 * sigma

        return ForecastResult(
            modelo="Holt-Winters (ETS)",
            historico=serie, forecast=_build_hist_fc(serie, fc_vals, lower, upper),
            metricas=metricas, backtest=backtest_df,
        )
    except Exception as e:
        return ForecastResult(modelo="ETS", historico=serie, forecast=pd.DataFrame(),
                              metricas={}, backtest=pd.DataFrame(), error_msg=str(e))


ETS_FECHA_INICIO    = "2023-01-01"
SARIMA_FECHA_INICIO = "2023-01-01"


def _forecast_sarima(serie: pd.DataFrame, horizonte: int, n_test: int | None = None) -> ForecastResult:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    serie = serie[serie["ds"] >= SARIMA_FECHA_INICIO].reset_index(drop=True)
    y = serie["y"].values
    n = len(y)
    n_test  = min(4, n // 6) if n_test is None else min(n_test, max(0, n - 12))
    y_train = y[:-n_test] if n_test > 0 else y
    y_test  = y[-n_test:]  if n_test > 0 else np.array([])

    if n >= 36:
        s_order = (1, 0, 1, 12)
        nombre  = "SARIMA(1,1,1)(1,0,1)12"
    elif n >= 24:
        s_order = (0, 0, 1, 12)
        nombre  = "SARIMA(1,1,1)(0,0,1)12"
    else:
        s_order = (0, 0, 0, 0)
        nombre  = "ARIMA(1,1,1)"

    def _fit(arr):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                return SARIMAX(arr, order=(1, 1, 1), seasonal_order=s_order,
                               enforce_stationarity=False, enforce_invertibility=False,
                               ).fit(disp=False, maxiter=300)
            except Exception:
                from statsmodels.tsa.arima.model import ARIMA as _A
                return _A(arr, order=(1, 1, 1)).fit()

    try:
        backtest_df, metricas = pd.DataFrame(), {}
        if n_test > 0:
            m_bt = _fit(y_train)
            p_bt = np.clip(np.asarray(m_bt.forecast(n_test)).ravel(), 0, None)
            backtest_df = pd.DataFrame({"ds": serie["ds"].iloc[-n_test:].values, "y_real": y_test, "y_pred": p_bt})
            metricas = _metricas(y_test, p_bt)

        m_full = _fit(y)
        fc_obj = m_full.get_forecast(steps=horizonte)
        try:
            fc_frame = fc_obj.summary_frame(alpha=0.10)
            fc_vals  = np.clip(fc_frame["mean"].values, 0, None)
            lower    = np.clip(fc_frame["mean_ci_lower"].values, 0, None)
            upper    = fc_frame["mean_ci_upper"].values
        except Exception:
            fc_vals = np.clip(np.asarray(fc_obj.predicted_mean).ravel(), 0, None)
            lower   = fc_vals * 0.80
            upper   = fc_vals * 1.20

        return ForecastResult(
            modelo=nombre,
            historico=serie, forecast=_build_hist_fc(serie, fc_vals, lower, upper),
            metricas=metricas, backtest=backtest_df,
        )
    except Exception as e:
        return ForecastResult(modelo="SARIMA", historico=serie, forecast=pd.DataFrame(),
                              metricas={}, backtest=pd.DataFrame(), error_msg=str(e))


def _tabla_exog_rezagada(df_exog: pd.DataFrame | None, lags_exog: tuple) -> tuple[pd.DataFrame, list]:
    """Convierte <df_exog> (columnas: fecha + una por variable, en ancho) en
    una tabla indexada por fecha con columnas <var>_lag<N> por cada lag
    pedido. Rezagado para no depender de valores futuros de la exógena al
    pronosticar. <df_exog> debe traer la fecha en su primera columna."""
    if df_exog is None or df_exog.empty:
        return pd.DataFrame(), []
    e = df_exog.copy()
    col_fecha = e.columns[0]
    e = e.rename(columns={col_fecha: "ds"})
    e["ds"] = pd.to_datetime(e["ds"])
    base_cols = [c for c in e.columns if c != "ds"]
    e = e.sort_values("ds").reset_index(drop=True)
    for c in base_cols:
        for lag in lags_exog:
            e[f"{c}_lag{lag}"] = e[c].shift(lag)
    exog_lag_cols = [f"{c}_lag{lag}" for c in base_cols for lag in lags_exog]
    return e.set_index("ds")[exog_lag_cols], exog_lag_cols


def _forecast_xgboost(serie: pd.DataFrame, horizonte: int, df_exog: pd.DataFrame | None = None,
                       lags_exog: tuple = (1, 2, 3), n_test: int | None = None) -> ForecastResult:
    try:
        import xgboost as xgb
    except ImportError:
        return ForecastResult(modelo="XGBoost", historico=serie, forecast=pd.DataFrame(),
                              metricas={}, backtest=pd.DataFrame(),
                              error_msg="xgboost no instalado. Ejecuta: pip install xgboost")

    y  = serie["y"].values.astype(float)
    ds = pd.to_datetime(serie["ds"].values)
    n  = len(y)
    MAX_LAG = min(12, n // 3)

    if MAX_LAG < 2:
        return ForecastResult(modelo="XGBoost", historico=serie, forecast=pd.DataFrame(),
                              metricas={}, backtest=pd.DataFrame(),
                              error_msg=f"Serie demasiado corta para XGBoost (n={n}).")

    exog_by_date, exog_lag_cols = _tabla_exog_rezagada(df_exog, lags_exog)

    def _exog_row(fecha: pd.Timestamp) -> dict:
        if exog_by_date.empty:
            return {}
        if fecha in exog_by_date.index:
            return exog_by_date.loc[fecha].to_dict()
        anteriores = exog_by_date.index[exog_by_date.index <= fecha]
        if len(anteriores) == 0:
            return {c: np.nan for c in exog_lag_cols}
        return exog_by_date.loc[anteriores.max()].to_dict()

    def make_X(y_arr, ds_arr):
        rows = []
        for i in range(MAX_LAG, len(y_arr)):
            row = {}
            for lag in range(1, MAX_LAG + 1):
                row[f"lag_{lag}"] = y_arr[i - lag]
            row["roll_mean_3"]  = float(np.mean(y_arr[max(0, i-3):i]))
            row["roll_mean_6"]  = float(np.mean(y_arr[max(0, i-6):i]))
            row["roll_mean_12"] = float(np.mean(y_arr[max(0, i-12):i]))
            row["roll_std_6"]   = float(np.std(y_arr[max(0, i-6):i]) + 1e-9)
            dt = pd.Timestamp(ds_arr[i])
            row["month"]   = dt.month
            row["quarter"] = dt.quarter
            row["trend_t"] = i
            row.update(_exog_row(dt))
            rows.append(row)
        return pd.DataFrame(rows)

    X_all = make_X(y, ds)
    y_all = y[MAX_LAG:]
    n_test = min(6, len(X_all) // 4) if n_test is None else min(n_test, max(0, len(X_all) - 12))
    backtest_df, metricas, model = pd.DataFrame(), {}, None

    try:
        if n_test > 0:
            X_tr, X_te = X_all.iloc[:-n_test], X_all.iloc[-n_test:]
            y_tr, y_te = y_all[:-n_test], y_all[-n_test:]
            m_bt = xgb.XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                                     subsample=0.8, colsample_bytree=0.8,
                                     objective="reg:squarederror", random_state=42, verbosity=0)
            m_bt.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
            p_bt = np.clip(m_bt.predict(X_te), 0, None)
            backtest_df = pd.DataFrame({"ds": serie["ds"].iloc[-n_test:].values, "y_real": y_te, "y_pred": p_bt})
            metricas = _metricas(y_te, p_bt)

        model = xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                                  subsample=0.8, colsample_bytree=0.8,
                                  objective="reg:squarederror", random_state=42, verbosity=0)
        model.fit(X_all, y_all, verbose=False)

        y_ext  = list(y.copy())
        ds_ext = list(ds.copy())
        fc_vals, fc_lower, fc_upper = [], [], []
        filas_horizonte = []
        last_trend = len(y_ext) - 1

        for h in range(horizonte):
            next_ds = ds_ext[-1] + pd.offsets.MonthBegin(1)
            next_t  = last_trend + h + 1
            y_arr_ext = np.array(y_ext)

            row = {}
            for lag in range(1, MAX_LAG + 1):
                idx = len(y_ext) - lag
                row[f"lag_{lag}"] = float(y_arr_ext[idx]) if idx >= 0 else 0.0
            row["roll_mean_3"]  = float(np.mean(y_arr_ext[-3:]))
            row["roll_mean_6"]  = float(np.mean(y_arr_ext[-6:]))
            row["roll_mean_12"] = float(np.mean(y_arr_ext[-12:]) if len(y_arr_ext) >= 12 else np.mean(y_arr_ext))
            row["roll_std_6"]   = float(np.std(y_arr_ext[-6:]) + 1e-9)
            row["month"]   = next_ds.month
            row["quarter"] = next_ds.quarter
            row["trend_t"] = next_t
            row.update(_exog_row(next_ds))

            X_pred = pd.DataFrame([row])[X_all.columns]
            yhat   = float(np.clip(model.predict(X_pred)[0], 0, None))
            sigma_model = float(np.std(model.predict(X_all) - y_all) + 1e-9)
            margin = 1.645 * sigma_model * np.sqrt(h + 1)

            fc_vals.append(yhat)
            fc_lower.append(max(0.0, yhat - margin))
            fc_upper.append(yhat + margin)
            y_ext.append(yhat)
            ds_ext.append(next_ds)
            filas_horizonte.append(X_pred.iloc[0])

        contribuciones = None
        if filas_horizonte:
            X_horizonte = pd.DataFrame(filas_horizonte).reset_index(drop=True)
            contribs = model.get_booster().predict(xgb.DMatrix(X_horizonte), pred_contribs=True)
            promedio = np.abs(contribs[:, :-1]).mean(axis=0)  # última columna es el valor base
            contribuciones = (
                pd.DataFrame({"variable": X_horizonte.columns, "contribucion": promedio})
                .sort_values("contribucion", ascending=False)
                .reset_index(drop=True)
            )

        return ForecastResult(
            modelo="XGBoost (Lag Features)",
            historico=serie, forecast=_build_hist_fc(serie, fc_vals, fc_lower, fc_upper),
            metricas=metricas, backtest=backtest_df, contribuciones=contribuciones,
        )
    except Exception as e:
        return ForecastResult(modelo="XGBoost", historico=serie, forecast=pd.DataFrame(),
                              metricas={}, backtest=pd.DataFrame(), error_msg=str(e))


def _forecast_naive(serie: pd.DataFrame, horizonte: int, n_test: int | None = None) -> ForecastResult:
    y  = serie["y"].values.astype(float)
    ds = pd.to_datetime(serie["ds"].values)
    n  = len(y)
    s  = 12
    n_test = min(6, n // 4) if n_test is None else min(n_test, max(0, n - 12))
    backtest_df, metricas = pd.DataFrame(), {}

    if n_test > 0 and n >= s + n_test:
        p_bt = np.array([y[n - n_test - s + i] for i in range(n_test)])
        p_bt = np.clip(p_bt, 0, None)
        backtest_df = pd.DataFrame({"ds": ds[-n_test:], "y_real": y[-n_test:], "y_pred": p_bt})
        metricas = _metricas(y[-n_test:], p_bt)

    fc_vals = []
    for h in range(1, horizonte + 1):
        idx = n - s + ((h - 1) % s)
        fc_vals.append(max(0.0, float(y[idx])) if idx >= 0 else 0.0)

    sigma = float(np.std(y))
    z     = 1.645
    lower = [max(0.0, v - z * sigma * np.sqrt(i + 1)) for i, v in enumerate(fc_vals)]
    upper = [v + z * sigma * np.sqrt(i + 1)            for i, v in enumerate(fc_vals)]

    return ForecastResult(
        modelo="Naive Estacional (s=12)",
        historico=serie, forecast=_build_hist_fc(serie, fc_vals, lower, upper),
        metricas=metricas, backtest=backtest_df,
    )


def _forecast_combo(serie: pd.DataFrame, horizonte: int, n_test: int | None = None) -> ForecastResult:
    """Promedio simple de ETS y SARIMA (pronóstico, bandas y backtest). En la
    validación de origen móvil de Negros (corte mar-2026) bajó el WAPE de los
    6 horizontes a 27.9 % contra 34.1 % de SARIMA y 38.2 % de ETS solos."""
    r_e = _forecast_ets(serie, horizonte, n_test=n_test)
    r_s = _forecast_sarima(serie, horizonte, n_test=n_test)
    if r_e.error_msg or r_e.forecast.empty:
        return r_s
    if r_s.error_msg or r_s.forecast.empty:
        return r_e
    hist = serie[["ds", "y"]].rename(columns={"y": "yhat"}).assign(yhat_lower=np.nan, yhat_upper=np.nan)
    fut_e = r_e.forecast[r_e.forecast["ds"] > serie["ds"].max()].set_index("ds")
    fut_s = r_s.forecast[r_s.forecast["ds"] > serie["ds"].max()].set_index("ds")
    fut = ((fut_e[["yhat", "yhat_lower", "yhat_upper"]] + fut_s[["yhat", "yhat_lower", "yhat_upper"]]) / 2).reset_index()

    backtest_df, metricas = pd.DataFrame(), {}
    if not r_e.backtest.empty and not r_s.backtest.empty:
        bt = r_e.backtest.merge(r_s.backtest[["ds", "y_pred"]], on="ds", suffixes=("_e", "_s"))
        if not bt.empty:
            bt["y_pred"] = (bt["y_pred_e"] + bt["y_pred_s"]) / 2
            backtest_df = bt[["ds", "y_real", "y_pred"]]
            metricas = _metricas(backtest_df["y_real"].values, backtest_df["y_pred"].values)

    return ForecastResult(
        modelo="Combinado (ETS + SARIMA)",
        historico=serie, forecast=pd.concat([hist, fut], ignore_index=True),
        metricas=metricas, backtest=backtest_df,
    )


MODELOS_DISPONIBLES = {
    "auto":   "Automático (el que mejor acierta en esta serie)",
    "combo":  "Combinado ETS + SARIMA",
    "ets":    "Holt-Winters ETS",
    "sarima": "SARIMA",
    "xgb":    "XGBoost (ML)",
    "naive":  "Naive Estacional",
}


def generar_forecast(
    df: pd.DataFrame,
    horizonte: int,
    col_periodo: str = "PERIODO",
    col_val: str = "PESO_TON",
    modelo: str = "auto",
    df_exog: pd.DataFrame | None = None,
    fecha_corte=None,
    ventana_prueba: int | None = None,
    rellenar_huecos: bool = False,
    seleccion: str | None = None,
) -> ForecastResult:
    """<fecha_corte>, <rellenar_huecos>: ver _preparar_serie.
    <modelo>="auto": usa el modelo con menor error en la validación de origen
    móvil (seleccionar_modelo). <seleccion>: esa clave ya precalculada
    (core/seleccion_modelos.py) para no repetir la validación (~15 s por serie).
    <ventana_prueba>: si se indica, los cuatro modelos se validan con los mismos
    últimos N meses, para que el modo automático compare métricas equivalentes.
    <df_exog>: opcional, solo lo usa el modelo XGBoost (columnas: fecha +
    una por variable, en ancho, ver _tabla_exog_rezagada). ETS/SARIMA/Naive
    lo ignoran — necesitarían valores FUTUROS de la exógena para pronosticar,
    que no tenemos."""
    serie = _preparar_serie(df, col_periodo, col_val, fecha_corte=fecha_corte, rellenar_huecos=rellenar_huecos)

    if len(serie) < MIN_PERIODS_FORECAST:
        return ForecastResult(
            modelo="N/A", historico=serie,
            forecast=pd.DataFrame(), metricas={}, backtest=pd.DataFrame(),
            error_msg=f"Serie insuficiente: {len(serie)} periodos. Se requieren al menos {MIN_PERIODS_FORECAST}.",
        )

    _fns = {"ets": _forecast_ets, "sarima": _forecast_sarima, "xgb": _forecast_xgboost, "naive": _forecast_naive,
            "combo": _forecast_combo}

    def _correr(key: str) -> ForecastResult:
        if key == "xgb":
            return _forecast_xgboost(serie, horizonte, df_exog=df_exog, n_test=ventana_prueba)
        return _fns[key](serie, horizonte, n_test=ventana_prueba)

    if modelo in _fns:
        return _correr(modelo)

    wape = None
    if seleccion not in _fns:
        seleccion, wape = seleccionar_modelo(df, col_periodo, col_val, df_exog=df_exog,
                                             fecha_corte=fecha_corte, rellenar_huecos=rellenar_huecos)
    if seleccion in _fns:
        r = _correr(seleccion)
        if not r.error_msg and not r.forecast.empty:
            detalle = (" | ".join(f"{k}: {v:.0f}%" for k, v in wape.items())
                       if wape is not None and len(wape) else "precalculado")
            r.modelo = f"{r.modelo}  [auto, origen móvil: {detalle}]"
            if wape is not None and len(wape):
                r.error_origen_movil = float(wape.iloc[0])
            return r

    # Respaldo (serie muy corta para el origen móvil): mejor MAPE en el corte único
    candidatos = ["ets", "xgb", "sarima", "naive"]
    resultados = []

    for key in candidatos:
        r = _correr(key)
        if r.error_msg or r.forecast.empty:
            continue
        mape = r.metricas.get("MAPE (%)", float("inf"))
        if mape is None or np.isnan(mape):
            mape = float("inf")
        resultados.append((mape, key, r))

    if not resultados:
        return _forecast_naive(serie, horizonte, n_test=ventana_prueba)

    resultados.sort(key=lambda x: x[0])
    mejor_mape, mejor_key, mejor_res = resultados[0]
    ranking = " | ".join(f"{k}: {m:.0f}%" if m < float("inf") else f"{k}: N/A" for m, k, _ in resultados)
    mejor_res.modelo = f"{mejor_res.modelo}  [auto: {ranking}]"
    return mejor_res


def backtest_origen_movil(
    df: pd.DataFrame,
    horizonte: int = 6,
    n_origenes: int = 6,
    modelos: tuple = ("ets", "sarima", "xgb", "naive"),
    col_periodo: str = "PERIODO",
    col_val: str = "PESO_TON",
    df_exog: pd.DataFrame | None = None,
    fecha_corte=None,
    rellenar_huecos: bool = False,
) -> pd.DataFrame:
    """Validación de origen móvil: corta la serie en varios meses pasados, ajusta
    cada modelo solo con lo anterior al corte y compara contra lo que pasó.
    Cada horizonte h (1..<horizonte>) se evalúa con al menos <n_origenes> cortes.
    Regresa formato largo: modelo, origen (último mes de entrenamiento), h, ds,
    y_real, y_pred. Resumir con resumen_origen_movil."""
    serie = _preparar_serie(df, col_periodo, col_val, fecha_corte=fecha_corte, rellenar_huecos=rellenar_huecos)
    fns = {"ets": _forecast_ets, "sarima": _forecast_sarima, "naive": _forecast_naive,
           "xgb": lambda s, h, n_test: _forecast_xgboost(s, h, df_exog=df_exog, n_test=n_test)}
    # El combinado se arma con las predicciones de ETS y SARIMA del mismo corte
    # (igual que _forecast_combo, sin volver a ajustarlos).
    base = [k for k in fns if k in modelos or (k in ("ets", "sarima") and "combo" in modelos)]
    n = len(serie)
    filas = []
    for i in range(1, n_origenes + horizonte):
        train = serie.iloc[:n - i].reset_index(drop=True)
        if len(train) < MIN_PERIODS_FORECAST:
            break
        reales = serie.iloc[n - i:n - i + horizonte]
        preds = {}
        for key in base:
            r = fns[key](train, horizonte, n_test=0)
            if r.error_msg or r.forecast.empty:
                continue
            preds[key] = r.forecast[r.forecast["ds"] > train["ds"].max()]["yhat"].to_numpy()
        if "combo" in modelos and ("ets" in preds or "sarima" in preds):
            preds["combo"] = ((preds["ets"] + preds["sarima"]) / 2 if "ets" in preds and "sarima" in preds
                              else preds.get("ets", preds.get("sarima")))
        for key in modelos:
            if key not in preds:
                continue
            for h, (ds, y_real) in enumerate(zip(reales["ds"], reales["y"]), start=1):
                filas.append({"modelo": key, "origen": train["ds"].max(), "h": h, "ds": ds,
                              "y_real": float(y_real), "y_pred": float(preds[key][h - 1])})
    return pd.DataFrame(filas, columns=["modelo", "origen", "h", "ds", "y_real", "y_pred"])


def error_global(bt: pd.DataFrame) -> pd.Series:
    """WAPE por modelo con todos los horizontes juntos: error total / volumen total (%)."""
    err = (bt["y_real"] - bt["y_pred"]).abs()
    return err.groupby(bt["modelo"]).sum() / bt.groupby("modelo")["y_real"].sum() * 100


CANDIDATOS_AUTO = ("combo", "ets", "sarima", "xgb", "naive")


def seleccionar_modelo(
    df: pd.DataFrame,
    col_periodo: str = "PERIODO",
    col_val: str = "PESO_TON",
    df_exog: pd.DataFrame | None = None,
    fecha_corte=None,
    rellenar_huecos: bool = False,
) -> tuple[str | None, pd.Series]:
    """Modelo con menor WAPE en la validación de origen móvil (6 horizontes,
    6 cortes por horizonte). Regresa (clave, WAPE por modelo); clave None si la
    serie es muy corta para validar."""
    bt = backtest_origen_movil(df, horizonte=6, n_origenes=6, modelos=CANDIDATOS_AUTO,
                               col_periodo=col_periodo, col_val=col_val, df_exog=df_exog,
                               fecha_corte=fecha_corte, rellenar_huecos=rellenar_huecos)
    if bt.empty:
        return None, pd.Series(dtype=float)
    wape = error_global(bt).sort_values()
    return wape.index[0], wape


def firma_serie(df: pd.DataFrame, col_periodo: str = "PERIODO", col_val: str = "PESO_TON",
                fecha_corte=None, rellenar_huecos: bool = False) -> str:
    """Identifica los datos con que se eligió el modelo (último mes | meses | total).
    Si la serie cambia, la selección precalculada deja de aplicar."""
    s = _preparar_serie(df, col_periodo, col_val, fecha_corte=fecha_corte, rellenar_huecos=rellenar_huecos)
    if s.empty:
        return ""
    return f"{s['ds'].max():%Y-%m}|{len(s)}|{s['y'].sum():.0f}"


def resumen_origen_movil(bt: pd.DataFrame) -> pd.DataFrame:
    """Por modelo y horizonte: MAPE, WAPE (error total / volumen total, estable
    con meses de 0 t), número de cortes y mejora contra el Naive estacional
    (1 − MAE modelo / MAE naive; positivo = le gana al naive)."""
    if bt.empty:
        return pd.DataFrame()
    filas = []
    for (modelo, h), g in bt.groupby(["modelo", "h"]):
        m = _metricas(g["y_real"].values, g["y_pred"].values)
        tot = g["y_real"].sum()
        wape = float((g["y_real"] - g["y_pred"]).abs().sum() / tot * 100) if tot > 0 else float("nan")
        filas.append({"modelo": modelo, "h": h, "cortes": len(g), "MAE": m["MAE"],
                      "MAPE (%)": m["MAPE (%)"], "WAPE (%)": round(wape, 1)})
    res = pd.DataFrame(filas)
    naive = res[res["modelo"] == "naive"].set_index("h")["MAE"]
    res["mejora_vs_naive (%)"] = [
        round((1 - mae / naive[h]) * 100, 1) if h in naive.index and naive[h] > 0 else float("nan")
        for mae, h in zip(res["MAE"], res["h"])
    ]
    return res.sort_values(["h", "modelo"]).reset_index(drop=True)


def filtrar_por_dimension(
    df: pd.DataFrame,
    col_dim: str,
    valor: str,
    col_periodo: str = "PERIODO",
    col_val: str = "PESO_TON",
) -> pd.DataFrame:
    if df.empty or col_dim not in df.columns:
        return pd.DataFrame()
    filtrado = df[df[col_dim] == valor]
    if filtrado.empty:
        return pd.DataFrame()
    return (
        filtrado.groupby(col_periodo, as_index=False)[col_val]
        .sum().sort_values(col_periodo).reset_index(drop=True)
    )


def generar_forecast_multiple(
    df: pd.DataFrame,
    col_dim: str,
    horizonte: int,
    col_periodo: str = "PERIODO",
    col_val: str = "PESO_TON",
    top_n: int | None = None,
    modelo: str = "auto",
) -> dict:
    if df.empty or col_dim not in df.columns:
        return {}
    dims = df[col_dim].dropna().unique().tolist()
    if top_n:
        vol = df.groupby(col_dim)[col_val].sum().nlargest(top_n).index.tolist()
        dims = [d for d in dims if d in vol]
    resultados = {}
    for dim in dims:
        sub = (
            df[df[col_dim] == dim]
            .groupby(col_periodo, as_index=False)[col_val]
            .sum().sort_values(col_periodo).reset_index(drop=True)
        )
        if len(sub) >= MIN_PERIODS_FORECAST:
            resultados[dim] = generar_forecast(sub, horizonte, col_periodo, col_val, modelo)
    return resultados

