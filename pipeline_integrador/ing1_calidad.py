"""INGENIERA 1 - Ana Camila Aguayo Cervantes: Calidad, Nulos y Outliers.

Fase 1  perfilar()                      -> completitud, unicidad y tipos de los datos crudos.
Fase 2  clasificar_faltantes()          -> MCAR vs MAR (prueba chi-cuadrada de independencia).
        eliminar_duplicados_exactos()   -> duplicados de POS (misma fila repetida).
        imputar_fisica() / imputar_online()
Fase 3  tratar_outliers_iqr()           -> IQR (factor 1.5) + Capping/Winsorizing.
        reporte_comparativo()           -> reporte de calidad antes/después.
"""
import logging

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

import config

log = logging.getLogger("pipeline")


# ---------------------------------------------------------------- Fase 1: diagnóstico inicial
def perfilar(df, nombre):
    """Perfil cuantitativo por columna + resumen de la tabla. No modifica df."""
    n = len(df)
    perfil = pd.DataFrame({
        "fuente": nombre,
        "columna": df.columns,
        "dtype_inferido": [str(t) for t in df.dtypes],
        "nulos": df.isna().sum().values,
        "pct_nulos": (df.isna().mean() * 100).round(2).values,
        "pct_completitud": (df.notna().mean() * 100).round(2).values,
        "valores_unicos": df.nunique(dropna=True).values,
    })
    resumen = {
        "fuente": nombre, "filas": n, "columnas": df.shape[1],
        "duplicados_exactos": int(df.astype(str).duplicated().sum()),
        "celdas_nulas": int(df.isna().sum().sum()),
        "pct_completitud_global": round(float(df.notna().mean().mean() * 100), 2),
    }
    log.info("[F1] %-8s filas=%d  duplicados=%d  nulos=%d  completitud=%.2f%%", nombre, n,
             resumen["duplicados_exactos"], resumen["celdas_nulas"], resumen["pct_completitud_global"])
    return perfil, resumen


# ---------------------------------------------------------------- Fase 2: faltantes
def clasificar_faltantes(df, columna, explicativas, alfa=0.05):
    """Prueba si la ausencia de `columna` depende de otras variables observadas.

    H0: el indicador de nulo es independiente de la variable explicativa.
    Si alguna p < alfa -> MAR (la ausencia se explica por datos observados); si no -> MCAR.
    """
    nulo = df[columna].isna()
    pruebas = {}
    for col in explicativas:
        tabla = pd.crosstab(nulo, df[col].astype(str))
        if tabla.shape[0] < 2 or tabla.shape[1] < 2:
            continue
        pruebas[col] = round(float(chi2_contingency(tabla)[1]), 4)
    tipo = "MAR" if any(p < alfa for p in pruebas.values()) else "MCAR"
    resultado = {"columna": columna, "nulos": int(nulo.sum()), "pct": round(nulo.mean() * 100, 2),
                 "p_valores": pruebas, "clasificacion": tipo}
    log.info("[F2] %-18s nulos=%-3d -> %s  p=%s", columna, resultado["nulos"], tipo, pruebas)
    return resultado


def eliminar_duplicados_exactos(df, nombre):
    antes = len(df)
    df = df.drop_duplicates(keep="first").reset_index(drop=True)
    log.info("[F2] %-8s duplicados exactos eliminados: %d", nombre, antes - len(df))
    return df, antes - len(df)


def imputar_mediana(df, columnas):
    """Imputación de numéricas sesgadas con la mediana (robusta a colas largas y outliers)."""
    detalle = {}
    for col in columnas:
        faltan = int(df[col].isna().sum())
        if faltan:
            mediana = float(df[col].median())
            df[col] = df[col].fillna(mediana)
            detalle[col] = {"imputados": faltan, "mediana": mediana}
            log.info("[F2] %s: %d nulos imputados con mediana=%.2f", col, faltan, mediana)
    return df, detalle


def recalcular_monto(df, col_cant, col_precio, col_monto):
    """monto = cantidad * precio cuando el dato existe en otras columnas (imputación determinista)."""
    mask = df[col_monto].isna() & df[col_cant].notna() & df[col_precio].notna()
    df.loc[mask, col_monto] = (df.loc[mask, col_cant] * df.loc[mask, col_precio]).round(2)
    log.info("[F2] %s recalculado como %s*%s en %d filas", col_monto, col_cant, col_precio, int(mask.sum()))
    return df, int(mask.sum())


def imputar_fisica(df):
    acciones = {}
    df, acciones["monto_recalculado"] = recalcular_monto(df, "cantidad", "precio_unitario", "monto_total_mxn")
    acciones["id_cliente_anonimo"] = int(df["id_cliente"].isna().sum())
    df["id_cliente"] = df["id_cliente"].fillna(config.ETIQUETA_ANONIMO)
    df, acciones["mediana"] = imputar_mediana(df, ["cantidad", "precio_unitario", "monto_total_mxn"])
    return df, acciones


def imputar_online(df):
    acciones = {}
    df, acciones["monto_recalculado"] = recalcular_monto(df, "units", "unit_price", "total_amount")
    acciones["direccion_sin_dato"] = int(df["shipping_address"].isna().sum())
    df["shipping_address"] = df["shipping_address"].fillna(config.ETIQUETA_SIN_DIRECCION)
    # customer_email nulo NO se inventa: se conserva como ausente (campo opcional en el esquema).
    acciones["email_nulo_conservado"] = int(df["customer_email"].isna().sum())
    df, acciones["mediana"] = imputar_mediana(df, ["units", "unit_price", "total_amount"])
    return df, acciones


# ---------------------------------------------------------------- Fase 3: outliers IQR
def limites_iqr(serie, factor=config.FACTOR_IQR):
    q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
    iqr = q3 - q1
    return float(q1), float(q3), float(iqr), float(q1 - factor * iqr), float(q3 + factor * iqr)


def tratar_outliers_iqr(df, columna, nombre, entero=False, grupo=None):
    """Capping/Winsorizing a los umbrales de Tukey.

    - Los valores imposibles (<= 0) NO entran al cálculo de cuartiles ni se recortan: siguen su
      curso y la Fase 6 los desvía a cuarentena con motivo (se 'eliminan' del flujo limpio sin
      perder trazabilidad).
    - Con `grupo` (p. ej. moneda) los cuartiles se calculan por subpoblación homogénea.
    - Variables enteras: los límites se redondean hacia dentro (ceil inferior, floor superior).
    Devuelve (df, lista_de_estadisticos) y marca la columna outlier_capado.
    """
    if "outlier_capado" not in df:
        df["outlier_capado"] = 0
    stats = []
    grupos = [(None, df.index)] if grupo is None else list(df.groupby(grupo).groups.items())
    for etiqueta, idx in grupos:
        validos = df.loc[idx, columna]
        validos = validos[validos > 0]
        if validos.empty:
            continue
        q1, q3, iqr, inf, sup = limites_iqr(validos)
        if entero:
            inf, sup = float(np.ceil(inf)), float(np.floor(sup))
        inf = max(inf, float(validos.min()))  # nunca subir un valor válido por encima de su mínimo real
        mask_alto = df.index.isin(idx) & (df[columna] > sup)
        mask_bajo = df.index.isin(idx) & (df[columna] > 0) & (df[columna] < inf)
        df.loc[mask_alto, columna] = sup
        df.loc[mask_bajo, columna] = inf
        df.loc[mask_alto | mask_bajo, "outlier_capado"] = 1
        stats.append({"fuente": nombre, "variable": columna, "grupo": etiqueta or "todos",
                      "Q1": q1, "Q3": q3, "IQR": iqr, "limite_inferior": inf, "limite_superior": sup,
                      "outliers_altos": int(mask_alto.sum()), "outliers_bajos": int(mask_bajo.sum()),
                      "max_antes": float(validos.max())})
        log.info("[F3] %-8s %-16s %-6s Q1=%.2f Q3=%.2f IQR=%.2f [%.2f, %.2f] -> %d recortados",
                 nombre, columna, etiqueta or "", q1, q3, iqr, inf, sup, int((mask_alto | mask_bajo).sum()))
    if entero:
        df[columna] = df[columna].round().astype("int64")
    return df, stats


def recalcular_tras_capping(df, col_cant, col_precio, col_monto):
    """El monto es variable derivada: si se recortó cantidad o precio, se recalcula para mantener
    la coherencia monto = cantidad * precio (no se recorta el monto de forma independiente)."""
    mask = df["outlier_capado"] == 1
    df.loc[mask, col_monto] = (df.loc[mask, col_cant] * df.loc[mask, col_precio]).round(2)
    return df


def tratar_outliers_fisica(df):
    df, s1 = tratar_outliers_iqr(df, "cantidad", "fisica", entero=True)
    df, s2 = tratar_outliers_iqr(df, "precio_unitario", "fisica")
    df = recalcular_tras_capping(df, "cantidad", "precio_unitario", "monto_total_mxn")
    return df, s1 + s2


def tratar_outliers_online(df):
    df, s1 = tratar_outliers_iqr(df, "units", "online", entero=True)
    df, s2 = tratar_outliers_iqr(df, "unit_price", "online", grupo="currency")  # USD y MXN por separado
    df = recalcular_tras_capping(df, "units", "unit_price", "total_amount")
    return df, s1 + s2


def resumen_iqr_monto(df, columna, nombre):
    """Solo diagnóstico: outliers del importe total que NO se explican por cantidad/precio."""
    validos = df[columna][df[columna] > 0]
    q1, q3, iqr, inf, sup = limites_iqr(validos)
    return {"fuente": nombre, "variable": columna, "grupo": "diagnostico", "Q1": q1, "Q3": q3, "IQR": iqr,
            "limite_inferior": inf, "limite_superior": sup,
            "outliers_altos": int((validos > sup).sum()), "outliers_bajos": int((validos < inf).sum()),
            "max_antes": float(validos.max())}


# ---------------------------------------------------------------- Reporte antes / después
def reporte_comparativo(resumen_antes, resumen_despues, perfiles_antes, perfiles_despues, extra):
    """Escribe reportes/REPORTE_CALIDAD.md + CSVs de perfil. Devuelve la ruta del Markdown."""
    pa = pd.concat(perfiles_antes, ignore_index=True)
    pd_ = pd.concat(perfiles_despues, ignore_index=True)
    pa.to_csv(config.REPORTES_DIR / "perfil_calidad_ANTES.csv", index=False, encoding="utf-8-sig")
    pd_.to_csv(config.REPORTES_DIR / "perfil_calidad_DESPUES.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(extra["outliers"]).to_csv(config.REPORTES_DIR / "outliers_iqr.csv", index=False,
                                           encoding="utf-8-sig")

    def tabla(df):
        cab = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
        return cab + "".join("| " + " | ".join(str(v) for v in fila) + " |\n" for fila in df.values)

    ra, rd = pd.DataFrame(resumen_antes), pd.DataFrame(resumen_despues)
    nulos_a = pa[pa.nulos > 0][["fuente", "columna", "nulos", "pct_nulos"]]
    nulos_d = pd_[pd_.nulos > 0][["fuente", "columna", "nulos", "pct_nulos"]]
    obligatorias = pd_[pd_.columna != "email_cliente"]
    nota_completitud = (f"\n> Completitud de las {len(obligatorias)} columnas obligatorias: "
                        f"**{obligatorias.pct_completitud.mean():.2f}%**. Los nulos restantes están solo en "
                        "`email_cliente`, que no existe en el canal físico y es opcional por regla de negocio.\n")
    out = pd.DataFrame(extra["outliers"]).round(2)
    fal = pd.DataFrame([{**f, "p_valores": ", ".join(f"{k}={v}" for k, v in f["p_valores"].items())}
                        for f in extra["faltantes"]])
    md = [
        "# Reporte comparativo de calidad: antes vs. después\n",
        "_Generado automáticamente por `main.py`. Responsable: Ana Camila Aguayo Cervantes (Ingeniera 1)._\n",
        "## 1. Resumen por fuente (ANTES: datos crudos)\n", tabla(ra),
        "\n## 2. Resumen del dataset integrado (DESPUÉS: tabla `transacciones_limpias`)\n", tabla(rd),
        nota_completitud,
        "\n## 3. Columnas con nulos ANTES\n", tabla(nulos_a) if len(nulos_a) else "Sin nulos.\n",
        "\n## 4. Columnas con nulos DESPUÉS\n", tabla(nulos_d) if len(nulos_d) else
        "**0 nulos** en las columnas obligatorias de la tabla limpia (`email_cliente` es opcional).\n",
        "\n## 5. Clasificación de faltantes (chi-cuadrada, alfa = 0.05)\n", tabla(fal),
        "\n## 6. Outliers por IQR (factor 1.5) y Capping\n", tabla(out),
        "\n## 7. Balance del lote\n", tabla(pd.DataFrame([extra["balance"]])),
        "\n## 8. Motivos de cuarentena\n", tabla(extra["motivos"]) if len(extra["motivos"]) else "Sin rechazos.\n",
    ]
    ruta = config.REPORTES_DIR / "REPORTE_CALIDAD.md"
    ruta.write_text("\n".join(md), encoding="utf-8")
    return ruta
