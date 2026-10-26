"""Panel web en vivo del Pipeline ETL omnicanal (para la exposición).

    streamlit run app.py

Ejecuta las mismas funciones que main.py (Fases 1 a 7) y muestra los resultados por integrante.
La pestaña "Prueba en vivo" valida con Pydantic una venta capturada a mano y demuestra el ROLLBACK.
Todo lo que escribe (BD, bitácora) queda en <PROYECTO>/ProyectoFinal/, igual que main.py.
"""
import sys

sys.dont_write_bytecode = True  # ningún archivo generado fuera de ProyectoFinal/

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.express as px
import streamlit as st
from pydantic import ValidationError

import config
import extraccion
import ing1_calidad as ana
import ing2_integracion as jose
import ing3_carga_bd as santiago
from ing3_esquemas import METODOS_PAGO, SUCURSALES, VentaLimpia
from main import categoria_motivo
from pruebas_estres import CATALOGO, casos_corruptos, reg

st.set_page_config(page_title="Pipeline ETL Omnicanal", page_icon="🛒", layout="wide")

# Paleta validada (dataviz/validate_palette.js, modo oscuro): categórica segura para daltonismo,
# rampa ordinal de un solo tono y colores de estado reservados para limpio / cuarentena.
SUPERFICIE, PLANO, TINTA, TINTA_2, TENUE, REJILLA, EJE = ("#1a1a19", "#0d0d0d", "#f0efec", "#c3c2b7",
                                                         "#898781", "#2c2c2a", "#383835")
CANAL = {"FISICA": "#3987e5", "ONLINE": "#d95926"}          # slots 1 y 2: la entidad conserva su color
FUENTE = {"fisica": CANAL["FISICA"], "online": CANAL["ONLINE"], "catalogo": "#199e70"}
MONEDA = {"MXN": "#199e70", "USD": "#c98500"}               # slots 3 y 4
SEGMENTO = {"BAJO": "#184f95", "MEDIO": "#2a78d6", "ALTO": "#86b6ef"}  # rampa ordinal azul
BUENO, CRITICO = "#0ca30c", "#d03b3b"                         # estado: siempre con ícono + texto

CSS = f"""
<style>
.block-container {{padding-top: 2rem; max-width: 1280px;}}
.hero {{padding: 1.6rem 1.8rem; border: 1px solid rgba(255,255,255,0.10); border-radius: 16px;
        background: {SUPERFICIE}; margin-bottom: 1rem;}}
.hero .eyebrow {{color: {TENUE}; font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase;}}
.hero h1 {{font-size: 2.1rem; margin: 0.25rem 0 0.4rem; padding: 0; color: {TINTA};}}
.hero p {{color: {TINTA_2}; margin: 0;}}
.equipo {{display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 1.2rem;}}
.persona {{border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; padding: 0.8rem 1rem;}}
.persona b {{color: {TINTA}; display: block;}}
.persona span {{color: {TENUE}; font-size: 0.85rem;}}
.fases {{display: flex; flex-wrap: wrap; gap: 6px; margin: 0.6rem 0 1rem;}}
.fase {{font-size: 0.78rem; padding: 3px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.10);
        color: {TENUE};}}
.fase.ok {{color: {TINTA_2};}}
.fase.ok::before {{content: "✓ "; color: {BUENO}; font-weight: 600;}}
[data-testid="stMetric"] {{background: {SUPERFICIE}; border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px; padding: 0.9rem 1.1rem;}}
[data-testid="stMetricLabel"] p {{color: {TENUE}; font-size: 0.85rem;}}
[data-testid="stMetricValue"] {{font-size: 2rem; color: {TINTA};}}
.stTabs [data-baseweb="tab"] {{font-size: 1rem; padding: 0.6rem 0.4rem;}}
</style>
"""


def estilo(fig, titulo, alto=360):
    """Cromo recesivo: rejilla sólida de un tono, ejes tenues, barras delgadas y tooltip legible."""
    fig.update_layout(
        title={"text": titulo, "font": {"size": 15, "color": TINTA}, "x": 0, "xanchor": "left"},
        height=alto, paper_bgcolor=SUPERFICIE, plot_bgcolor=SUPERFICIE,
        font={"family": "system-ui, -apple-system, Segoe UI, sans-serif", "color": TINTA_2, "size": 12},
        margin={"l": 16, "r": 16, "t": 64, "b": 16}, bargap=0.45, barcornerradius=4,
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 1, "xanchor": "right", "title": None},
        hoverlabel={"bgcolor": PLANO, "bordercolor": EJE, "font": {"color": TINTA}},
    )
    fig.update_xaxes(gridcolor=REJILLA, linecolor=EJE, zerolinecolor=EJE, tickfont={"color": TENUE})
    fig.update_yaxes(gridcolor=REJILLA, linecolor=EJE, zerolinecolor=EJE, tickfont={"color": TENUE})
    return fig


def grafica(destino, fig):
    destino.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
FASES = ["Extracción de las 3 fuentes", "F1 · Perfilado de calidad", "F2 · Duplicados e imputación",
         "F3 · Outliers con IQR", "F4 · Integración multifuente", "F5 · Min-Max y terciles",
         "F6 · Validación Pydantic", "F7 · Carga transaccional SQLite"]


# ------------------------------------------------------------------------------ pipeline
def ejecutar_pipeline(avance):
    """Mismo flujo que main.main(), guardando las fotos intermedias que necesitan las gráficas."""
    config.configurar_bitacora()
    r = {}
    avance(0)
    catalogo, fisica, online = extraccion.cargar_fuentes()
    r["crudos"] = {"catalogo": len(catalogo), "fisica": len(fisica), "online": len(online)}

    avance(1)
    perfiles = [ana.perfilar(df, n)[0] for n, df in (("catalogo", catalogo), ("fisica", fisica),
                                                      ("online", online))]
    r["perfil_antes"] = pd.concat(perfiles, ignore_index=True)

    avance(2)
    r["faltantes"] = pd.DataFrame([
        ana.clasificar_faltantes(fisica, "monto_total_mxn", ["sucursal", "metodo_pago", "cantidad"]),
        ana.clasificar_faltantes(fisica, "id_cliente", ["sucursal", "metodo_pago", "cantidad"]),
        ana.clasificar_faltantes(online, "shipping_address", ["order_status", "payment_gateway", "currency"]),
        ana.clasificar_faltantes(online, "customer_email", ["order_status", "payment_gateway", "currency"]),
    ])
    fisica, dup_f = ana.eliminar_duplicados_exactos(fisica, "fisica")
    online, dup_o = ana.eliminar_duplicados_exactos(online, "online")
    fisica, _ = ana.imputar_fisica(fisica)
    online, _ = ana.imputar_online(online)
    r["duplicados"] = dup_f + dup_o

    avance(3)
    cant_antes = pd.concat([fisica["cantidad"], online["units"]], ignore_index=True)
    fisica, st_f = ana.tratar_outliers_fisica(fisica)
    online, st_o = ana.tratar_outliers_online(online)
    cant_despues = pd.concat([fisica["cantidad"], online["units"]], ignore_index=True)
    r["cantidad"] = pd.concat([pd.DataFrame({"cantidad": cant_antes, "momento": "Antes del IQR"}),
                               pd.DataFrame({"cantidad": cant_despues, "momento": "Después del capping"})])
    r["outliers"] = pd.DataFrame(st_f + st_o)

    avance(4)
    integrado = jose.unificar_fuentes(fisica, online)
    integrado = jose.cruzar_catalogo(integrado, catalogo)

    avance(5)
    integrado, r["minmax"] = jose.escalar_min_max(integrado)
    integrado, r["terciles"] = jose.discretizar_importe(integrado)
    r["integrado"] = integrado

    avance(6)
    registros = santiago.a_registros(integrado)
    productos = set(catalogo["id_producto"])
    aptos, cuarentena = santiago.segregar(registros, productos)

    avance(7)
    r["carga"] = santiago.cargar(config.DB_PATH, aptos, cuarentena)
    r["aptos"], r["limpias"] = aptos, pd.DataFrame(aptos)
    cuar = pd.DataFrame(cuarentena, columns=["id_registro", "canal", "registro_original",
                                             "motivo_rechazo_cuarentena"])
    cuar["categoria"] = cuar["motivo_rechazo_cuarentena"].map(categoria_motivo)
    r["cuarentena"] = cuar
    r["registros"], r["productos"] = registros, productos
    return r


def leer_bitacora():
    if not config.DB_PATH.exists():
        return pd.DataFrame()
    with closing(sqlite3.connect(config.DB_PATH)) as con:
        return pd.read_sql("SELECT * FROM bitacora_cargas ORDER BY id_carga DESC LIMIT 10", con)


def contar_limpias(db):
    with closing(sqlite3.connect(db)) as con:  # closing(): en Windows el archivo queda bloqueado si no se cierra
        return con.execute("SELECT COUNT(*) FROM transacciones_limpias").fetchone()[0]


def numero(texto):
    """Convierte lo capturado a número si se puede; si no, lo deja como texto para que Pydantic lo rechace."""
    texto = texto.strip()
    if texto == "":
        return None
    try:
        return int(texto) if texto.lstrip("-").isdigit() else float(texto)
    except ValueError:
        return texto


def tarjeta(col, titulo, valor, ayuda=None):
    col.metric(titulo, valor, help=ayuda)


# ------------------------------------------------------------------------------ encabezado
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(f"""
<div class="hero">
  <div class="eyebrow">{config.MATERIA} · Grupo 1 · Retail &amp; E-commerce omnicanal</div>
  <h1>🛒 Pipeline ETL con Zona de Cuarentena</h1>
  <p>Tienda física + tienda online + catálogo → limpieza → integración → validación → SQLite ·
     Docente: {config.DOCENTE}</p>
  <div class="equipo">{"".join(f'<div class="persona"><b>{n}</b><span>{rol}</span></div>'
                                for n, rol in config.EQUIPO)}</div>
</div>
""", unsafe_allow_html=True)

if "r" not in st.session_state:
    st.session_state.r = None

col_boton, col_estado = st.columns([1, 3])
if col_boton.button("▶ Ejecutar pipeline", type="primary", use_container_width=True):
    barra = col_estado.progress(0.0, text="Iniciando…")
    inicio = time.time()

    def avance(i):
        barra.progress((i + 1) / len(FASES), text=FASES[i])
        time.sleep(0.35)  # pausa breve para que se aprecie cada fase durante la exposición

    st.session_state.r = ejecutar_pipeline(avance)
    st.session_state.segundos = time.time() - inicio
    barra.progress(1.0, text="Pipeline terminado")

r = st.session_state.r
hechas = len(FASES) if r is not None else 0
st.markdown('<div class="fases">' + "".join(f'<span class="fase{" ok" if i < hechas else ""}">{f}</span>'
                                            for i, f in enumerate(FASES)) + "</div>", unsafe_allow_html=True)
if r is None:
    col_estado.info("Presiona **Ejecutar pipeline** para correr las 7 fases sobre los datos reales.")
    st.stop()

carga_ok = r["carga"]["ok"]
(col_estado.success if carga_ok else col_estado.error)(f"Carga **{'COMMIT' if carga_ok else 'ROLLBACK'}** en `{config.DB_PATH.name}` · "
                   f"{st.session_state.segundos:.1f} s")

n_validados = len(r["registros"])
k = st.columns(5)
tarjeta(k[0], "Registros crudos", f"{n_validados + r['duplicados']:,}")
tarjeta(k[1], "Duplicados eliminados", r["duplicados"])
tarjeta(k[2], "Outliers topados", int(r["integrado"]["outlier_capado"].sum()))
tarjeta(k[3], "Transacciones limpias", f"{len(r['limpias']):,}")
tarjeta(k[4], "En cuarentena", len(r["cuarentena"]), f"{100 * len(r['cuarentena']) / n_validados:.2f} %")

t_ana, t_jose, t_santi, t_vivo = st.tabs(["👩‍💻 Ana Camila · Calidad", "🔗 José Carlos · Integración",
                                          "🛡️ Santiago · Validación y BD", "🧪 Prueba en vivo"])

# ------------------------------------------------------------------------------ Ana Camila
with t_ana:
    st.subheader(config.EQUIPO[0][0])
    st.caption("Fases 1-3 · perfilado, nulos (MCAR/MAR), duplicados, imputación y outliers IQR")
    izq, der = st.columns(2)
    nulos = r["perfil_antes"].query("nulos > 0")
    fig = px.bar(nulos, x="nulos", y="columna", color="fuente", orientation="h", text="nulos",
                 color_discrete_map=FUENTE, hover_data={"pct_nulos": True})
    fig.update_traces(textposition="outside", textfont_color=TINTA_2, cliponaxis=False)
    fig.update_layout(yaxis_title=None, xaxis_title="celdas nulas", yaxis={"categoryorder": "total ascending"})
    grafica(izq, estilo(fig, "Valores nulos en los datos crudos"))

    datos_cant = r["cantidad"].query("cantidad > 0")
    fig = px.box(datos_cant, x="momento", y="cantidad", color="momento", points="outliers", log_y=True,
                 color_discrete_sequence=[TENUE, CANAL["FISICA"]])
    fig.update_traces(line_width=2, marker_size=9)
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="cantidad (escala log)")
    grafica(der, estilo(fig, "Cantidad: antes y después del capping IQR"))

    st.markdown("**Clasificación de faltantes (prueba chi-cuadrada, α = 0.05)**")
    st.dataframe(r["faltantes"], use_container_width=True, hide_index=True)
    st.markdown("**Límites de Tukey aplicados** (Q1 − 1.5·IQR, Q3 + 1.5·IQR)")
    cols = ["fuente", "variable", "grupo", "Q1", "Q3", "IQR", "limite_inferior", "limite_superior",
            "outliers_altos", "outliers_bajos", "max_antes"]
    st.dataframe(r["outliers"][cols].round(2), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------ José Carlos
with t_jose:
    st.subheader(config.EQUIPO[1][0])
    st.caption("Fases 4-5 · fechas ISO, USD→MXN, cruce con catálogo, Min-Max y discretización")
    integ = r["integrado"]
    k = st.columns(4)
    tarjeta(k[0], "Filas integradas", f"{len(integ):,}")
    tarjeta(k[1], "Órdenes en USD convertidas", int((integ["moneda_original"] == "USD").sum()),
            f"Tipo de cambio fijo: ${config.TIPO_CAMBIO_USD:.2f}")
    tarjeta(k[2], "Llaves huérfanas", int(integ["es_huerfano"].sum()),
            f"{integ.loc[integ.es_huerfano == 1, 'id_producto'].nunique()} códigos que no están en el catálogo")
    tarjeta(k[3], "Rango Min-Max", f"{r['minmax']['min']:,.0f} – {r['minmax']['max']:,.0f}")

    izq, der = st.columns(2)
    origen = integ.groupby(["canal", "moneda_original"]).size().reset_index(name="transacciones")
    fig = px.bar(origen, x="transacciones", y="canal", color="moneda_original", orientation="h",
                 text="transacciones", color_discrete_map=MONEDA)
    fig.update_traces(textposition="inside", insidetextanchor="middle", textfont_color=PLANO,
                      marker_line_color=SUPERFICIE, marker_line_width=2)
    fig.update_layout(barmode="stack", yaxis_title=None, xaxis_title="transacciones", bargap=0.55)
    grafica(izq, estilo(fig, f"Origen y moneda · USD convertidos a MXN @ ${config.TIPO_CAMBIO_USD:.2f}", 380))

    seg = integ[integ["monto_total_mxn"] > 0]
    fig = px.strip(seg, x="monto_total_mxn", y="segmento_importe", color="segmento_importe", log_x=True,
                   category_orders={"segmento_importe": ["ALTO", "MEDIO", "BAJO"]},
                   color_discrete_map=SEGMENTO, hover_data=["id_transaccion", "canal"])
    fig.update_traces(marker_size=8, marker_opacity=0.75, jitter=0.6)
    for corte in r["terciles"].values():
        fig.add_vline(x=corte, line_width=1, line_color=TENUE)
    fig.update_layout(showlegend=False, xaxis_title="monto total MXN (escala log)", yaxis_title=None)
    t1, t2 = r["terciles"]["tercil_1"], r["terciles"]["tercil_2"]
    grafica(der, estilo(fig, f"Segmentos por terciles · cortes en ${t1:,.0f} y ${t2:,.0f}", 380))

    st.markdown("**Dataset integrado (antes de la validación)**")
    canal = st.radio("Canal", ["Todos", "FISICA", "ONLINE"], horizontal=True, key="canal_integ")
    vista = integ if canal == "Todos" else integ[integ["canal"] == canal]
    st.dataframe(vista.head(200), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------ Santiago
with t_santi:
    st.subheader(config.EQUIPO[2][0])
    st.caption("Fases 6-7 · esquema Pydantic VentaLimpia, zona de cuarentena y carga transaccional")
    cuar = r["cuarentena"]
    n_l, n_c = len(r["limpias"]), len(cuar)
    destino = pd.DataFrame({"destino": [f"✔ Limpias · {n_l:,} ({100 * n_l / (n_l + n_c):.2f} %)",
                                        f"⚠ Cuarentena · {n_c:,} ({100 * n_c / (n_l + n_c):.2f} %)"],
                            "registros": [n_l, n_c], "y": ["", ""]})
    fig = px.bar(destino, x="registros", y="y", color="destino", orientation="h",
                 color_discrete_sequence=[BUENO, CRITICO])
    fig.update_traces(marker_line_color=SUPERFICIE, marker_line_width=2)
    fig.update_layout(barmode="stack", bargap=0.35, xaxis_title=None, yaxis_title=None)
    fig.update_yaxes(showticklabels=False)
    grafica(st, estilo(fig, f"Destino de los {n_l + n_c:,} registros validados", 200))

    motivos = cuar.groupby(["categoria", "canal"]).size().reset_index(name="registros")
    totales = motivos.groupby("categoria")["registros"].sum()
    fig = px.bar(motivos, x="registros", y="categoria", color="canal", orientation="h",
                 color_discrete_map=CANAL)
    fig.update_traces(marker_line_color=SUPERFICIE, marker_line_width=2)
    for categoria, total in totales.items():  # un solo número por barra: el total
        fig.add_annotation(x=total, y=categoria, text=f"<b>{total}</b>", showarrow=False, xanchor="left",
                           xshift=6, font={"color": TINTA})
    fig.update_layout(barmode="stack", yaxis_title=None, xaxis_title="registros",
                      yaxis={"categoryorder": "total ascending"})
    grafica(st, estilo(fig, "Motivos de cuarentena por canal", 340))

    st.markdown("**Tabla `cuarentena_errores`**")
    elegidos = st.multiselect("Filtrar por motivo", sorted(cuar["categoria"].unique()),
                              placeholder="Todos los motivos")
    vista = cuar if not elegidos else cuar[cuar["categoria"].isin(elegidos)]
    st.dataframe(vista[["id_registro", "canal", "categoria", "motivo_rechazo_cuarentena"]],
                 use_container_width=True, hide_index=True)

    st.markdown("**Bitácora de cargas (`bitacora_cargas` en SQLite)**")
    st.dataframe(leer_bitacora(), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------ Prueba en vivo
with t_vivo:
    st.subheader("Captura una venta y mira cómo la valida el pipeline")
    st.caption("Escribe datos válidos o rómpelos a propósito: email sin @, cantidad -5, un producto "
               "que no existe, una fecha futura… El registro nunca tumba el pipeline.")
    with st.form("venta"):
        a, b, c = st.columns(3)
        id_tx = a.text_input("id_transaccion", "DEMO-0001")
        canal = b.selectbox("canal", ["FISICA", "ONLINE"])
        fecha = c.text_input("fecha_venta (AAAA-MM-DD)", "2026-10-15")
        sucursal = a.selectbox("sucursal", sorted(SUCURSALES))
        producto = b.text_input("id_producto", "PROD-010")
        cantidad = c.text_input("cantidad", "2")
        precio = a.text_input("precio_unitario_mxn", "350")
        monto = b.text_input("monto_total_mxn (vacío = cantidad × precio)", "")
        moneda = c.selectbox("moneda_original", ["MXN", "USD", "EUR"])
        email = a.text_input("email_cliente", "cliente@correo.com")
        metodo = b.selectbox("metodo_pago", [m.title() for m in METODOS_PAGO] + ["Bitcoin"])
        estado = c.selectbox("estado", ["COMPLETADO", "PAGADO", "PENDIENTE", "CANCELADO", "ROBADO"])
        enviado = st.form_submit_button("Validar venta", type="primary")

    if enviado:
        cant_v, precio_v = numero(cantidad), numero(precio)
        monto_v = numero(monto)
        if monto_v is None and all(isinstance(x, (int, float)) for x in (cant_v, precio_v)):
            monto_v = round(cant_v * precio_v, 2)
        if isinstance(monto_v, (int, float)):
            mm = r["minmax"]
            escalado = round((monto_v - mm["min"]) / (mm["max"] - mm["min"]), 6)
            t = r["terciles"]
            segmento = "BAJO" if monto_v <= t["tercil_1"] else "MEDIO" if monto_v <= t["tercil_2"] else "ALTO"
        else:
            escalado, segmento = 0.0, "BAJO"
        productos = r["productos"]
        venta = {
            "id_transaccion": id_tx, "canal": canal, "fecha_venta": fecha, "sucursal": sucursal,
            "id_producto": producto.strip(),
            "categoria": "Demo",
            "cantidad": cant_v, "precio_unitario_mxn": precio_v, "monto_total_mxn": monto_v,
            "moneda_original": moneda, "id_cliente": config.ETIQUETA_ANONIMO, "email_cliente": email,
            "metodo_pago": metodo, "estado": estado, "monto_escalado": escalado,
            "segmento_importe": segmento, "outlier_capado": 0,
        }
        izq, der = st.columns(2)
        izq.markdown("**Registro que entra a la Fase 6**")
        izq.code(json.dumps(venta, ensure_ascii=False, indent=2), language="json")
        try:
            limpio = VentaLimpia.model_validate(venta, context={"productos": productos})
            der.success("✅ Registro válido → iría a **transacciones_limpias**")
            der.code(json.dumps(limpio.model_dump(mode="json"), ensure_ascii=False, indent=2), language="json")
        except ValidationError as exc:
            der.error(f"🚫 Rechazado → **cuarentena_errores** ({exc.error_count()} regla(s) violada(s))")
            for e in exc.errors():
                campo = ".".join(str(x) for x in e["loc"]) or "registro"
                der.markdown(f"- `{campo}`: {e['msg'].removeprefix('Value error, ')}")

    st.divider()
    st.subheader("Prueba de estrés: 25 inyecciones de datos corruptos")
    if st.button("💣 Inyectar datos corruptos"):
        filas = []
        for nombre, caso in casos_corruptos().items():
            aptos, cuar_e = santiago.segregar([caso], CATALOGO)
            filas.append({"caso": nombre, "resultado": "✅ pasó" if aptos else "🚫 cuarentena",
                          "motivo": cuar_e[0]["motivo_rechazo_cuarentena"] if cuar_e else ""})
        st.session_state.estres = pd.DataFrame(filas)
    if "estres" in st.session_state:
        filas = st.session_state.estres
        rechazados = int((filas["resultado"] != "✅ pasó").sum())
        st.success(f"{rechazados} de {len(filas)} registros corruptos fueron a cuarentena · el pipeline no se cayó")
        st.dataframe(filas, use_container_width=True, hide_index=True)

    st.subheader("Sabotaje de la base de datos: ROLLBACK")
    st.caption("Se carga una base de prueba y luego se intenta una segunda carga con una llave primaria "
               "duplicada a mitad de la transacción.")
    if st.button("🔥 Sabotear la carga"):
        db = config.DB_ESTRES_PATH
        db.unlink(missing_ok=True)
        primera = santiago.cargar(db, r["aptos"], [])
        antes = contar_limpias(db)
        apto, _ = santiago.segregar([reg(id_transaccion="SABOTAJE")], CATALOGO)
        segunda = santiago.cargar(db, apto * 2, [])  # PRIMARY KEY duplicada a mitad de la transacción
        st.session_state.sabotaje = (primera, segunda, antes, contar_limpias(db))
    if "sabotaje" in st.session_state:
        primera, segunda, antes, despues = st.session_state.sabotaje
        k = st.columns(3)
        tarjeta(k[0], "Carga 1", "COMMIT" if primera["ok"] else "ROLLBACK", f"{antes:,} filas")
        tarjeta(k[1], "Carga 2 (saboteada)", "COMMIT" if segunda["ok"] else "ROLLBACK")
        tarjeta(k[2], "Filas después del sabotaje", f"{despues:,}")
        if not segunda["ok"] and antes == despues:
            st.success(f"La base quedó intacta: {antes:,} filas antes y {despues:,} después. "
                       f"Error capturado: `{segunda['error']}`")
        else:
            st.error("La base cambió tras el sabotaje")
