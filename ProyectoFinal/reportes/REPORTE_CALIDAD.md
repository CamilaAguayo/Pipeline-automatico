# Reporte comparativo de calidad: antes vs. después

_Generado automáticamente por `main.py`. Responsable: Ana Camila Aguayo Cervantes (Ingeniera 1)._

## 1. Resumen por fuente (ANTES: datos crudos)

| fuente | filas | columnas | duplicados_exactos | celdas_nulas | pct_completitud_global |
|---|---|---|---|---|---|
| catalogo | 50 | 6 | 0 | 0 | 100.0 |
| fisica | 620 | 9 | 20 | 159 | 97.15 |
| online | 600 | 11 | 0 | 92 | 98.61 |


## 2. Resumen del dataset integrado (DESPUÉS: tabla `transacciones_limpias`)

| fuente | filas | columnas | duplicados_exactos | celdas_nulas | pct_completitud_global |
|---|---|---|---|---|---|
| limpias | 1095 | 17 | 0 | 581 | 96.88 |


> Completitud de las 16 columnas obligatorias: **100.00%**. Los nulos restantes están solo en `email_cliente`, que no existe en el canal físico y es opcional por regla de negocio.


## 3. Columnas con nulos ANTES

| fuente | columna | nulos | pct_nulos |
|---|---|---|---|
| fisica | monto_total_mxn | 32 | 5.16 |
| fisica | id_cliente | 127 | 20.48 |
| online | customer_email | 15 | 2.5 |
| online | shipping_address | 77 | 12.83 |


## 4. Columnas con nulos DESPUÉS

| fuente | columna | nulos | pct_nulos |
|---|---|---|---|
| limpias | email_cliente | 581 | 53.06 |


## 5. Clasificación de faltantes (chi-cuadrada, alfa = 0.05)

| columna | nulos | pct | p_valores | clasificacion |
|---|---|---|---|---|
| monto_total_mxn | 32 | 5.16 | sucursal=0.4786, metodo_pago=0.6911, cantidad=0.9096 | MCAR |
| id_cliente | 127 | 20.48 | sucursal=0.7143, metodo_pago=0.6516, cantidad=0.2925 | MCAR |
| shipping_address | 77 | 12.83 | order_status=0.3737, payment_gateway=0.5321, currency=0.9441 | MCAR |
| customer_email | 15 | 2.5 | order_status=0.9177, payment_gateway=0.4392, currency=0.3484 | MCAR |


## 6. Outliers por IQR (factor 1.5) y Capping

| fuente | variable | grupo | Q1 | Q3 | IQR | limite_inferior | limite_superior | outliers_altos | outliers_bajos | max_antes |
|---|---|---|---|---|---|---|---|---|---|---|
| fisica | cantidad | todos | 1.0 | 4.0 | 3.0 | 1.0 | 8.0 | 13 | 0 | 500.0 |
| fisica | precio_unitario | todos | 1025.98 | 2985.89 | 1959.91 | 332.7 | 5925.75 | 0 | 0 | 4218.11 |
| online | units | todos | 1.0 | 2.0 | 1.0 | 1.0 | 3.0 | 0 | 0 | 3.0 |
| online | unit_price | MXN | 1008.15 | 2966.7 | 1958.55 | 332.7 | 5904.52 | 0 | 0 | 4218.11 |
| online | unit_price | USD | 51.7 | 153.12 | 101.42 | 17.06 | 305.25 | 0 | 0 | 216.31 |
| fisica | monto_total_mxn | diagnostico | 2012.82 | 7710.2 | 5697.38 | -6533.25 | 16256.27 | 34 | 0 | 33744.88 |
| online | total_amount | diagnostico | 214.55 | 3192.45 | 2977.9 | -4252.3 | 7659.3 | 37 | 0 | 826360.8 |


## 7. Balance del lote

| filas_crudas_ventas | duplicados_exactos_eliminados | filas_validadas | transacciones_limpias | cuarentena | pct_cuarentena | outliers_capados | carga_bd |
|---|---|---|---|---|---|---|---|
| 1220 | 20 | 1200 | 1095 | 105 | 8.75 | 13 | COMMIT |


## 8. Motivos de cuarentena

| categoria | canal | registros |
|---|---|---|
| Llave huérfana (producto no está en catálogo) | ONLINE | 33 |
| Llave huérfana (producto no está en catálogo) | FISICA | 28 |
| Correo malformado | ONLINE | 25 |
| Cantidad imposible (<= 0) | FISICA | 10 |
| Monto incoherente con cantidad*precio | ONLINE | 8 |
| Monto excede tope (bot) | ONLINE | 1 |
