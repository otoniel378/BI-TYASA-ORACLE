"""
mercado/canacero/parser.py — Parseo del CSV "Base de datos tradicional"
(Grupos Personalizados > Grupo Fracciones, Agrupar por: Fracciones) exportado
desde CANACERO SICEP (sicep.canacero.org.mx).

Formato confirmado sobre un archivo real (general_ImpTot_*.csv): 31 columnas
fijas, sin nombres de columna útiles en las primeras 4 (jerarquía de
categoría interna de CANACERO, casi siempre vacía salvo para materias primas
y algunos productos terminados que CANACERO curó a mano). Parseo por
POSICIÓN, no por nombre de header:

    idx 0     CATEGORIA (jerarquía nivel 1, ej. "MATERIAS PRIMAS") — opcional
    idx 1-3   niveles adicionales de jerarquía — no se usan
    idx 4     DESCRIPCION
    idx 5     FRACCION (8 o 10 dígitos: 10 = fracción TIGIE + NICO)
    idx 6     Periodo (año, ej. "2026")
    idx 7-18  Ene[Ton] .. Dic[Ton]
    idx 19-30 Ene[USD] .. Dic[USD]

Cada archivo cubre UN movimiento (Importación o Exportación) para un año
completo. El movimiento no viene en el CSV como campo estructurado (el
nombre de archivo lo insinúa, ej. "ImpTot", pero es solo una convención) así
que lo decide el usuario en la UI al subirlo.

El archivo trae TODAS las fracciones de la TIGIE (no solo capítulos 72/73),
así que "volumen_ton" no siempre está en toneladas comparables — ej. la
fracción 27112101 (gas natural) reporta en unidades gigantes que no son
tonelaje real. Este parser no filtra nada: guarda todo tal cual viene y el
filtrado a fracciones de TYASA (que sí son todas cap. 72/73, medidas en Ton)
ocurre después, en las consultas de mercado/canacero/loaders.py.
"""

import pandas as pd

N_COLUMNAS = 31
IDX_CATEGORIA = 0
IDX_DESCRIPCION = 4
IDX_FRACCION = 5
IDX_ANIO = 6
IDX_TON_INICIO = 7
IDX_USD_INICIO = 19
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

MOVIMIENTOS_VALIDOS = {"IMPORTACION", "EXPORTACION"}


def _val(x) -> str | None:
    return str(x).strip() if pd.notna(x) and str(x).strip() else None


def _num(x) -> float:
    try:
        return float(x) if pd.notna(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


CSV_ENCODING = "cp1252"  # export de CANACERO viene en Windows-1252 (ej. "ESTAÑADA" con Ñ), no UTF-8


def _validar_encabezado(archivo):
    header = pd.read_csv(archivo, header=None, nrows=1, dtype=str, encoding=CSV_ENCODING)
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    if header.shape[1] != N_COLUMNAS:
        raise ValueError(
            f"El CSV tiene {header.shape[1]} columnas, se esperaban {N_COLUMNAS}. "
            "Verifica que el reporte se generó en CANACERO SICEP > Grupos Personalizados > "
            "Grupo Fracciones > Base de datos tradicional, con 'Agrupar por: Fracciones'."
        )
    col_fraccion = str(header.iloc[0, IDX_FRACCION]).strip().upper()
    if col_fraccion != "FRACCION":
        raise ValueError(
            f"La columna {IDX_FRACCION} del encabezado dice {col_fraccion!r}, se esperaba "
            "'FRACCION'. El formato del reporte de CANACERO pudo haber cambiado."
        )


def parse_csv_canacero(archivo, movimiento: str, nombre_archivo: str = "") -> pd.DataFrame:
    """
    <archivo>: ruta o file-like (lo que entrega st.file_uploader).
    <movimiento>: 'IMPORTACION' | 'EXPORTACION', elegido por el usuario en la UI.

    Devuelve un DataFrame largo: una fila por (fracción, mes) con columnas
    anio, mes, periodo_mes, movimiento, fraccion_arancelaria, descripcion,
    categoria, volumen_ton, valor_usd, archivo_origen.

    Descarta filas con volumen_ton == 0 (mes sin movimiento o todavía no
    ocurrido dentro del año del reporte — indistinguibles en este export).
    """
    movimiento = (movimiento or "").strip().upper()
    if movimiento not in MOVIMIENTOS_VALIDOS:
        raise ValueError(f"movimiento debe ser uno de {MOVIMIENTOS_VALIDOS}, recibido: {movimiento!r}")

    _validar_encabezado(archivo)
    df = pd.read_csv(archivo, header=None, skiprows=1, dtype=str, encoding=CSV_ENCODING)

    filas = []
    for _, r in df.iterrows():
        fraccion = _val(r[IDX_FRACCION])
        if not fraccion:
            continue
        try:
            anio = int(float(r[IDX_ANIO]))
        except (TypeError, ValueError):
            continue

        categoria = _val(r[IDX_CATEGORIA])
        descripcion = _val(r[IDX_DESCRIPCION])

        for mes_num in range(1, 13):
            volumen_ton = _num(r[IDX_TON_INICIO + mes_num - 1])
            if volumen_ton == 0.0:
                continue
            valor_usd = _num(r[IDX_USD_INICIO + mes_num - 1])

            filas.append({
                "anio": anio,
                "mes": mes_num,
                "periodo_mes": f"{anio}-{mes_num:02d}",
                "movimiento": movimiento,
                "fraccion_arancelaria": fraccion[:20],
                "descripcion": descripcion[:500] if descripcion else None,
                "categoria": categoria[:200] if categoria else None,
                "volumen_ton": volumen_ton,
                "valor_usd": valor_usd,
                "archivo_origen": (nombre_archivo or "")[:200] or None,
            })

    return pd.DataFrame(filas, columns=[
        "anio", "mes", "periodo_mes", "movimiento", "fraccion_arancelaria",
        "descripcion", "categoria", "volumen_ton", "valor_usd", "archivo_origen",
    ])
