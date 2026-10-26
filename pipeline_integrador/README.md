# Pipeline ETL Omnicanal con Zona de Cuarentena — Grupo 1 (Retail & E-commerce)

Ingeniería de Datos (ATD-2602) · Unidad 2 · TecNM Campus Colima

## Estructura

```
PROYECTO/
├── catalogo_productos.pdf · ventas_tienda_fisica.pdf · ventas_online.pdf   (fuentes)
├── PORTADA ID.docx                                                          (portada original, no se modifica)
├── pipeline_integrador/            ← CÓDIGO
│   ├── config.py                   común: rutas, constantes, crea ProyectoFinal/
│   ├── extraccion.py               común: reconstruye CSV/JSON desde los PDF
│   ├── ing1_calidad.py             Ana Camila    · Fases 1-3 + reporte antes/después
│   ├── ing2_integracion.py         José Carlos   · Fases 4-5
│   ├── ing3_esquemas.py            Santiago      · Fase 6 (modelo Pydantic)
│   ├── ing3_carga_bd.py            Santiago      · Fase 6 (cuarentena) + Fase 7 (SQLite)
│   ├── pruebas_estres.py           Santiago      · pruebas con datos corruptos
│   ├── portada.py                  común: rellena la portada existente
│   └── main.py                     orquestador
└── ProyectoFinal/                  ← TODO lo generado (se crea solo)
    ├── ventas_omnicanal.db         transacciones_limpias · cuarentena_errores · bitacora_cargas
    ├── ventas_estres.db            BD de la prueba de estrés
    ├── pipeline.log
    ├── PORTADA_PROYECTO_FINAL.docx
    ├── REGLAS_DE_NEGOCIO.md · GUION_EXPOSICION.md · GUIA_VIDEO_MUDO.md
    ├── datos_crudos/               catalogo_productos.csv · ventas_tienda_fisica.csv · ventas_online.json
    └── reportes/                   REPORTE_CALIDAD.md · perfiles · outliers · CSV de ambas tablas · pruebas
```

## Cómo se conectan los tres roles

```
extraccion ──► Ana Camila ──────────────► José Carlos ──────────────► Santiago
 3 fuentes     F1 perfilar()               F4 unificar_fuentes()        F6 segregar()  ─► aptos / cuarentena
 crudas        F2 imputar_*()              F4 cruzar_catalogo()         F7 cargar()    ─► COMMIT / ROLLBACK
               F3 tratar_outliers_*()      F5 escalar / discretizar
       DataFrames por fuente (limpios)  ►  un DataFrame integrado    ►  lista de dicts validados
```

El contrato entre módulos es simple: Ana Camila entrega **dos DataFrames por fuente** ya sin
duplicados, nulos ni outliers; José Carlos los convierte en **un DataFrame con el esquema común**
(más `categoria`, `monto_escalado`, `segmento_importe`); Santiago recibe esa tabla como lista de
diccionarios y decide, registro por registro, si va a la tabla limpia o a cuarentena.

## Ejecución

```bash
python -m pip install -r requirements.txt
```

```bash
python main.py
```

```bash
python main.py --estres
```

```bash
python pruebas_estres.py
```

`main.py` crea `ProyectoFinal/` (y sus subcarpetas) con `pathlib.Path.mkdir(parents=True, exist_ok=True)`
en `config.preparar_directorios()`. Si en `PROYECTO/` se colocan los CSV/JSON originales, se usan en
lugar de los PDF sin cambiar nada del código.

## Portada: cómo se usa la portada existente

`portada.py` (lo llama `main.py` al final, o se corre solo con `python portada.py`):

1. Abre **`PROYECTO/PORTADA ID.docx`** con `python-docx` (logos, fuente Candara y formato intactos).
2. Cambia `NOMBRE TAREA` por el título del proyecto.
3. Cambia "Nombre de las alumnas" por **"Integrantes del equipo"** y escribe los 3 nombres con su
   rol; como la portada original solo tenía 2 renglones, **clona el último** para el tercero y así
   conserva el mismo estilo. (El nombre de Ariadna Andrea Muñoz Andrade, que venía de otra tarea,
   se reemplaza.)
4. Corrige la materia a "Ingeniería de Datos (ATD-2602)" y pone la fecha de entrega.
5. Guarda la copia en **`ProyectoFinal/PORTADA_PROYECTO_FINAL.docx`**; el original no se toca.

Para cambiar textos (por ejemplo la fecha), editen `LUGAR_FECHA`, `TITULO_PORTADA` o `EQUIPO` en
`config.py` y vuelvan a ejecutar.

## Reporte final (Word + PDF) automático

```bash
python generar_reporte.py
```

Une portada + introducción + `REGLAS_DE_NEGOCIO.md` + `reportes/REPORTE_CALIDAD.md` + conclusiones
y genera en `ProyectoFinal/`: `REPORTE_FINAL.md` (texto unificado), `REPORTE_FINAL.docx` y, si
Microsoft Word está instalado, `REPORTE_FINAL.pdf`. Ejecuten antes `python main.py`.

## Panel web en vivo (exposición)

```bash
streamlit run app.py
```

Abre `http://localhost:8501` en el navegador. El botón **Ejecutar pipeline** corre las 7 fases con
las mismas funciones que `main.py` (y deja la BD en `ProyectoFinal/`). Pestañas:

- **Ana Camila**: nulos de los datos crudos, boxplot de cantidad antes/después del capping, MCAR/MAR y límites de Tukey.
- **José Carlos**: origen de las transacciones (canal y moneda), huérfanos, rango Min-Max y segmentos por terciles.
- **Santiago**: limpias contra cuarentena, motivos de rechazo, tabla `cuarentena_errores` filtrable y bitácora de cargas.
- **Prueba en vivo**: formulario para capturar una venta (válida o corrupta) y ver la decisión de Pydantic;
  inyección de los 25 casos corruptos y sabotaje de la carga para demostrar el ROLLBACK (usa `ventas_estres.db`).

El tema oscuro del panel está en `pipeline_integrador/.streamlit/config.toml` (se aplica al correr
`streamlit run app.py` desde esa carpeta). Los colores de las gráficas son una paleta validada para
daltonismo: cada canal conserva su color en todas las gráficas (física azul, online naranja), los
segmentos usan una sola rampa azul ordenada y verde/rojo se reservan para limpio/cuarentena.
