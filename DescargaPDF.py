import streamlit as st
import requests
import pandas as pd
from datetime import date
from typing import List, Dict, Any

# ==========================
# CONFIGURACIÓN / LOGIN
# ==========================
st.set_page_config(page_title="Facturación Electrónica — IOM Panamá", layout="centered")

USUARIOS = {"Mispanama": "Maxilo2000", "usuario1": "password123"}

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align:center; color:#1c6758'>Acceso</h2>", unsafe_allow_html=True)
    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if usuario in USUARIOS and password == USUARIOS[usuario]:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")
    st.stop()

if st.sidebar.button("Cerrar sesión"):
    st.session_state["autenticado"] = False
    st.rerun()

# ==========================
# MODO DE FUENTE DE DATOS
# ==========================
st.sidebar.markdown("## Fuente de datos")
data_mode = st.sidebar.selectbox("Selecciona", ["CSV (recomendado)", "Ninox API"])

# ==========================
# UTILS GENERALES
# ==========================
def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    # normalizar encabezados: quitar espacios extras, unificar mayúsculas/minúsculas
    df = df.copy()
    df.columns = [c.strip().replace("\n", " ").replace("  ", " ") for c in df.columns]
    return df

def _first_existing(d: dict, keys: list[str], default=""):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default

def _clean_num(x) -> float:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("$", "").replace(",", "").replace("%","").strip()
    try:
        return float(s)
    except Exception:
        return 0.0

# ==========================
# CARGA DE DATOS: CSV
# ==========================
def cargar_csvs() -> dict[str, pd.DataFrame]:
    st.subheader("Cargar datos desde CSV (exportados de Ninox)")
    c1, c2 = st.columns(2)
    with c1:
        f_clientes = st.file_uploader("Clientes.csv", type=["csv"], key="up_cli")
        f_productos = st.file_uploader("Productos.csv", type=["csv"], key="up_prod")
    with c2:
        f_facturas = st.file_uploader("Facturas.csv", type=["csv"], key="up_fac")
        f_lineas = st.file_uploader("LineasFactura.csv", type=["csv"], key="up_lin")

    data = {}
    if f_clientes:  data["clientes"]  = _norm_cols(pd.read_csv(f_clientes))
    if f_productos: data["productos"] = _norm_cols(pd.read_csv(f_productos))
    if f_facturas:  data["facturas"]  = _norm_cols(pd.read_csv(f_facturas))
    if f_lineas:    data["lineas"]    = _norm_cols(pd.read_csv(f_lineas))

    return data

# ==========================
# CARGA DE DATOS: NINOX API (OPCIONAL)
# ==========================
API_TOKEN   = "0b3a1130-785a-11f0-ace0-3fb1fcb242e2"
TEAM_ID     = "ihp8o8AaLzfodwc4J"
DATABASE_ID = "u2g01uaua8tu"
BASE_URL = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}"
HEADERS  = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

def _ninox_get(path: str, params: Dict[str, Any] | None = None, page_size: int = 200) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = dict(params or {})
        q.update({"limit": page_size, "offset": offset})
        url = f"{BASE_URL}{path}"
        r = requests.get(url, headers=HEADERS, params=q, timeout=30)
        if not r.ok:
            st.error(f"Error Ninox GET {path}: {r.status_code} — {r.text}")
            break
        batch = r.json() or []
        out.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return out

def _records_to_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for rec in records:
        f = rec.get("fields", {}) or {}
        rows.append(f)
    df = pd.DataFrame(rows)
    return _norm_cols(df)

def cargar_desde_ninox() -> dict[str, pd.DataFrame]:
    data = {}
    cli = _ninox_get("/tables/Clientes/records")
    pro = _ninox_get("/tables/Productos/records")
    fac = _ninox_get("/tables/Facturas/records")
    lin = _ninox_get("/tables/Lineas%20Factura/records")  # intenta nombre con espacio
    if not lin:  # intento alterno
        lin = _ninox_get("/tables/LineasFactura/records")

    if cli: data["clientes"]  = _records_to_df(cli)
    if pro: data["productos"] = _records_to_df(pro)
    if fac: data["facturas"]  = _records_to_df(fac)
    if lin: data["lineas"]    = _records_to_df(lin)
    return data

# ==========================
# OBTENER DATASET (CSV por defecto)
# ==========================
if data_mode == "CSV (recomendado)":
    data = cargar_csvs()
else:
    st.info("Intentando cargar desde Ninox API…")
    data = cargar_desde_ninox()

# Validación mínima
if "clientes" not in data or data["clientes"].empty:
    st.warning("Cargue al menos **Clientes.csv** para continuar."); st.stop()
if "productos" not in data or data["productos"].empty:
    st.warning("Cargue **Productos.csv** para poder agregar ítems."); st.stop()
if "facturas" not in data or data["facturas"].empty:
    st.warning("Cargue **Facturas.csv** (necesario para seleccionar facturas pendientes)."); st.stop()

clientes_df  = data["clientes"]
productos_df = data["productos"]
facturas_df  = data["facturas"]
lineas_df    = data.get("lineas", pd.DataFrame())

# Mapear nombres de columnas flexibles
def col(df: pd.DataFrame, opciones: list[str]) -> str | None:
    for o in opciones:
        if o in df.columns:
            return o
    return None

col_cli_nombre = col(clientes_df, ["cliente", "Cliente", "Nombre"])
col_cli_ruc    = col(clientes_df, ["RUC","Ruc"])
col_cli_dv     = col(clientes_df, ["DV","Dv","dv"])
col_cli_dir    = col(clientes_df, ["Dirección","Direccion"])
col_cli_tel    = col(clientes_df, ["Teléfono","Telefono"])
col_cli_mail   = col(clientes_df, ["Correo","Email","email"])

col_prod_cod   = col(productos_df, ["Código","Codigo","code"])
col_prod_desc  = col(productos_df, ["Descripción","Descripcion","description"])
col_prod_pu    = col(productos_df, ["Precio Unitario","PU","PrecioUnitario"])
col_prod_itbms = col(productos_df, ["ITBMS","IVA","Impuesto"])

col_fac_num    = col(facturas_df, ["Factura No.","Factura No", "Factura", "Numero", "N°", "No."])
col_fac_estado = col(facturas_df, ["Estado","estado"])
col_fac_pago   = col(facturas_df, ["Medio de Pago","MedioPago","Pago"])

col_lin_facnum = col(lineas_df, ["Factura No.","Factura","FacturaNo","Factura_Numero","Factura Id","FacturaID"])
col_lin_desc   = col(lineas_df, ["Descripción","Descripcion"])
col_lin_cant   = col(lineas_df, ["Cantidad"])
col_lin_pu     = col(lineas_df, ["Precio Unitario","PU","PrecioUnitario"])
col_lin_itbms  = col(lineas_df, ["ITBMS","IVA","Impuesto"])
col_lin_cod    = col(lineas_df, ["Código","Codigo"])

# ==========================
# ÍTEMS (state)
# ==========================
if "line_items" not in st.session_state:
    st.session_state["line_items"] = []

# ==========================
# TIPO DOC
# ==========================
st.sidebar.markdown("## Tipo de documento")
doc_humano = st.sidebar.selectbox("Seleccione", ["Factura", "Nota de Crédito"])
DOC_MAP = {"Factura": "01", "Nota de Crédito": "06"}
doc_type = DOC_MAP[doc_humano]

# ==========================
# CLIENTE
# ==========================
st.header("Datos del Cliente")
nombres_clientes = list(clientes_df[col_cli_nombre].astype(str).fillna("").values)
idx_map = list(range(len(nombres_clientes)))
cliente_idx = st.selectbox("Seleccione Cliente", idx_map, format_func=lambda x: nombres_clientes[x])
cli_row = clientes_df.iloc[cliente_idx].to_dict()

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC",       value=_first_existing(cli_row, [col_cli_ruc]) , disabled=True)
    st.text_input("DV",        value=_first_existing(cli_row, [col_cli_dv])  , disabled=True)
    st.text_area ("Dirección", value=_first_existing(cli_row, [col_cli_dir]) , disabled=True)
with col2:
    st.text_input("Teléfono",  value=_first_existing(cli_row, [col_cli_tel]) , disabled=True)
    st.text_input("Correo",    value=_first_existing(cli_row, [col_cli_mail]), disabled=True)

# ==========================
# NÚMERO DOC + FACTURA PENDIENTE
# ==========================
fact_pend = facturas_df
if col_fac_estado:
    fact_pend = fact_pend[(fact_pend[col_fac_estado].astype(str).str.strip().str.lower() == "pendiente")]

if doc_type == "01":
    if not fact_pend.empty and col_fac_num:
        opciones_facturas = list(fact_pend[col_fac_num].astype(str).values)
        idx_factura = st.selectbox("Seleccione Factura Pendiente", range(len(opciones_facturas)),
                                   format_func=lambda x: opciones_facturas[x])
        numero_preview = opciones_facturas[idx_factura]
        factura_sel = fact_pend.iloc[idx_factura]
    else:
        # Siguiente correlativo simple desde CSV
        try:
            nums = pd.to_numeric(facturas_df[col_fac_num], errors="coerce").fillna(0).astype(int)
            numero_preview = f"{(nums.max()+1):08d}"
        except Exception:
            numero_preview = "00000001"
        factura_sel = None
else:
    # Calcular correlativo para NC si tienes CSV de NC; por simplicidad, autoincremento aparte
    numero_preview = "00000001"
    factura_sel = None

st.text_input("Número de Documento Fiscal", value=str(numero_preview), disabled=True)
fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# Medio de pago por defecto
medio_pago_opciones = ["Efectivo", "Débito", "Crédito"]
medio_pago_default = "Efectivo"
if factura_sel is not None and col_fac_pago and factura_sel.get(col_fac_pago):
    mp = str(factura_sel[col_fac_pago]).strip().capitalize()
    if mp in medio_pago_opciones:
        medio_pago_default = mp

# ==========================
# AUTOCARGA DE ÍTEMS DESDE CSV (Líneas Factura)
# ==========================
if doc_type == "01" and factura_sel is not None:
    if st.button("Cargar líneas desde la factura seleccionada"):
        if lineas_df.empty:
            st.warning("No se cargó el CSV de Líneas Factura.")
        else:
            df = lineas_df.copy()
            if col_lin_facnum is None:
                st.warning("No se encontró columna que relacione Líneas con la Factura (p. ej., 'Factura No.').")
            else:
                df = df[df[col_lin_facnum].astype(str) == str(numero_preview)]
                nuevos = []
                for _, r in df.iterrows():
                    desc  = str(r.get(col_lin_desc, "")).strip() if col_lin_desc else "SIN DESCRIPCIÓN"
                    cant  = _clean_num(r.get(col_lin_cant)) if col_lin_cant else 1.0
                    pu    = _clean_num(r.get(col_lin_pu)) if col_lin_pu else 0.0
                    tasa  = _clean_num(r.get(col_lin_itbms)) if col_lin_itbms else 0.0
                    codigo = str(r.get(col_lin_cod, "")).strip() if col_lin_cod else ""
                    valor_itbms = round(cant * pu * tasa, 2)
                    nuevos.append({
                        "codigo":         codigo,
                        "descripcion":    desc or "SIN DESCRIPCIÓN",
                        "cantidad":       float(cant),
                        "precioUnitario": float(pu),
                        "tasa":           float(tasa),
                        "valorITBMS":     float(valor_itbms),
                    })
                st.session_state["line_items"] = nuevos
                if not nuevos:
                    st.warning("No se encontraron líneas para la factura seleccionada.")

# ==========================
# ÍTEMS UI (agregar manualmente también)
# ==========================
st.header("Ítems del documento (puedes agregar o editar)")
# Combo productos para agregar rápido
prod_labels = []
for _, p in productos_df.iterrows():
    cod = str(p.get(col_prod_cod, "") if col_prod_cod else "")
    ds  = str(p.get(col_prod_desc, "") if col_prod_desc else "")
    prod_labels.append(f"{cod} | {ds}")

prod_idx = st.selectbox("Producto", range(len(prod_labels)), format_func=lambda x: prod_labels[x])
p = productos_df.iloc[prod_idx].to_dict()

cantidad = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
precio_unit = _clean_num(_first_existing(p, [col_prod_pu])) if col_prod_pu else 0.0
itbms_rate  = _clean_num(_first_existing(p, [col_prod_itbms])) if col_prod_itbms else 0.0

if st.button("Agregar ítem"):
    valor_itbms = round(itbms_rate * cantidad * precio_unit, 2)
    st.session_state["line_items"].append({
        "codigo":         _first_existing(p, [col_prod_cod]),
        "descripcion":    _first_existing(p, [col_prod_desc]) or "SIN DESCRIPCIÓN",
        "cantidad":       float(cantidad),
        "precioUnitario": float(precio_unit),
        "tasa":           float(itbms_rate),
        "valorITBMS":     float(valor_itbms),
    })

if st.session_state["line_items"]:
    st.write("#### Ítems del documento")
    for idx, i in enumerate(st.session_state["line_items"], start=1):
        st.write(f"{idx}. {i['codigo']} | {i['descripcion']} | Cant: {i['cantidad']:.2f} | P.U.: {i['precioUnitario']:.2f} | ITBMS: {i['valorITBMS']:.2f}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Limpiar Ítems"):
            st.session_state["line_items"] = []
    with c2:
        idx_del = st.number_input("Eliminar ítem #", min_value=0, value=0, step=1)
        if st.button("Eliminar"):
            if 0 < idx_del <= len(st.session_state["line_items"]):
                st.session_state["line_items"].pop(idx_del - 1)

# ==========================
# TOTALES
# ==========================
total_neto  = sum(i["cantidad"] * i["precioUnitario"] for i in st.session_state["line_items"])
total_itbms = sum(i["valorITBMS"] for i in st.session_state["line_items"])
total_total = total_neto + total_itbms

st.write(f"**Total Neto:** {total_neto:.2f}   **ITBMS:** {total_itbms:.2f}   **Total:** {total_total:.2f}")

medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Débito", "Crédito"],
                          index=["Efectivo","Débito","Crédito"].index(medio_pago_default))
emisor     = st.text_input("Nombre de quien emite el documento (obligatorio)", value=st.session_state.get("emisor", ""))
if emisor:
    st.session_state["emisor"] = emisor

# ==========================
# BACKEND + EMAIL UI
# ==========================
BACKEND_URL = "https://ninox-factory-server.onrender.com"

enviar_email = st.checkbox("Enviar CAFE por correo al cliente", value=True)
email_destino_default = str(_first_existing(cli_row, [col_cli_mail])).strip()
email_to = st.text_input("Email destino", value=email_destino_default if enviar_email else "", disabled=not enviar_email)
email_cc = st.text_input("CC (opcional, separa por comas)", value="", disabled=not enviar_email)

# ==========================
# PAYLOAD
# ==========================
def armar_payload_documento(
    *,
    doc_type: str,
    numero_documento: str,
    fecha_emision: date,
    cliente_row: Dict[str, Any],
    items: List[Dict[str, Any]],
    total_neto: float,
    total_itbms: float,
    total: float,
    medio_pago: str,
) -> Dict[str, Any]:

    forma_pago_codigo = {"Efectivo": "01", "Débito": "02", "Crédito": "03"}[medio_pago]

    lista_items = []
    for i in items:
        precio_item = i["cantidad"] * i["precioUnitario"]
        valor_total = precio_item + i["valorITBMS"]
        tasa_itbms  = "01" if (i.get("tasa", 0) or 0) > 0 else "00"
        lista_items.append({
            "codigo":                  i.get("codigo") or "0",
            "descripcion":             i.get("descripcion") or "SIN DESCRIPCIÓN",
            "codigoGTIN":              "0",
            "cantidad":                f"{i['cantidad']:.2f}",
            "precioUnitario":          f"{i['precioUnitario']:.2f}",
            "precioUnitarioDescuento": "0.00",
            "precioItem":              f"{precio_item:.2f}",
            "valorTotal":              f"{valor_total:.2f}",
            "cantGTINCom":             f"{i['cantidad']:.2f}",
            "codigoGTINInv":           "0",
            "tasaITBMS":               tasa_itbms,
            "valorITBMS":              f"{i['valorITBMS']:.2f}",
            "cantGTINComInv":          f"{i['cantidad']:.2f}",
        })

    payload = {
        "documento": {
            "codigoSucursalEmisor": "0000",
            "tipoSucursal": "1",
            "datosTransaccion": {
                "tipoEmision": "01",
                "tipoDocumento": doc_type,                # 01=Factura, 06=Nota de Crédito
                "numeroDocumentoFiscal": str(numero_documento),
                "puntoFacturacionFiscal": "001",
                "fechaEmision": f"{fecha_emision.isoformat()}T09:00:00-05:00",
                "naturalezaOperacion": "01",
                "tipoOperacion": 1,
                "destinoOperacion": 1,
                "formatoCAFE": 1,
                "entregaCAFE": 1,
                "envioContenedor": 1,
                "procesoGeneracion": 1,
                "tipoVenta": 1,
                "informacionInteres": "",
                "cliente": {
                    "tipoClienteFE": "02" if str(_first_existing(cliente_row,[col_cli_ruc])).strip() else "01",
                    "tipoContribuyente": 1,
                    "numeroRUC": str(_first_existing(cliente_row,[col_cli_ruc])).replace("-", ""),
                    "digitoVerificadorRUC": _first_existing(cliente_row,[col_cli_dv]),
                    "razonSocial": _first_existing(cliente_row,[col_cli_nombre]),
                    "direccion": _first_existing(cliente_row,[col_cli_dir]),
                    "telefono1": _first_existing(cliente_row,[col_cli_tel]),
                    "correoElectronico1": _first_existing(cliente_row,[col_cli_mail]),
                    "pais": "PA",
                },
            },
            "listaItems": {"item": lista_items},
            "totalesSubTotales": {
                "totalPrecioNeto":    f"{total_neto:.2f}",
                "totalITBMS":         f"{total_itbms:.2f}",
                "totalMontoGravado":  f"{total_itbms:.2f}",
                "totalDescuento":     "0.00",
                "totalAcarreoCobrado":"0.00",
                "valorSeguroCobrado": "0.00",
                "totalFactura":       f"{total:.2f}",
                "totalValorRecibido": f"{total:.2f}",
                "vuelto":             "0.00",
                "tiempoPago":         "1",
                "nroItems":           str(len(lista_items)),
                "totalTodosItems":    f"{total:.2f}",
                "listaFormaPago": {
                    "formaPago": [{
                        "formaPagoFact":    forma_pago_codigo,
                        "valorCuotaPagada": f"{total:.2f}",
                    }]
                },
                "listaPagoPlazo": {
                    "pagoPlazo": [{
                        "fechaVenceCuota": f"{fecha_emision.isoformat()}T23:59:59-05:00",
                        "valorCuota": f"{total:.2f}"
                    }]
                }
            },
        }
    }
    return payload

# ==========================
# ENVIAR
# ==========================
if st.button("Enviar Documento a DGI"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite el documento."); st.stop()
    if not st.session_state["line_items"]:
        st.error("Debe agregar al menos un ítem o cargar las líneas desde la factura."); st.stop()

    try:
        payload = armar_payload_documento(
            doc_type=DOC_MAP["Factura"],  # esta versión envia solo Factura; activa NC si la necesitas
            numero_documento=str(numero_preview),
            fecha_emision=fecha_emision,
            cliente_row=cli_row,
            items=st.session_state["line_items"],
            total_neto=total_neto,
            total_itbms=total_itbms,
            total=total_total,
            medio_pago=medio_pago,
        )

        r = requests.post(f"{BACKEND_URL}/enviar-factura", json=payload, timeout=60)
        if r.ok:
            st.success(f"{doc_humano} enviada correctamente ✅")
            st.session_state["line_items"] = []

            if enviar_email and (email_to or "").strip():
                email_json = {
                    "to": [e.strip() for e in (email_to or "").split(",") if e.strip()],
                    "cc": [e.strip() for e in (email_cc or "").split(",") if e.strip()],
                    "subject": f"Factura electrónica #{numero_documento}",
                    "body_html": f"""
                    <p>Estimado(a),</p>
                    <p>Se ha generado su Factura <b>#{numero_documento}</b>.</p>
                    <p>Adjuntamos el CAFE oficial desde nuestro sistema.</p>
                    <p>Saludos,<br>IOM Panamá</p>
                    """,
                    "meta": {
                        "codigoSucursalEmisor":  "0000",
                        "numeroDocumentoFiscal": str(numero_documento),
                        "puntoFacturacionFiscal":"001",
                        "tipoDocumento":         "01",
                        "tipoEmision":           "01",
                    }
                }
                rem = requests.post(f"{BACKEND_URL}/enviar-cafe-email", json=email_json, timeout=60)
                if rem.ok:
                    st.success("CAFE enviado por correo 📧")
                else:
                    st.warning("Documento creado; no se pudo enviar el email (revisa backend / logs).")
        else:
            st.error("Error al enviar el documento.")
            try:
                st.write(r.json())
            except Exception:
                st.write(r.text)
    except Exception as e:
        st.error(f"Error de conexión con el backend: {e}")

# ==========================
# AYUDA
# ==========================
with st.expander("Ayuda / Referencias"):
    st.markdown(
        """
        **Uso con CSV**
        1) Exporta desde Ninox las tablas: *Clientes*, *Productos*, *Facturas*, *Líneas Factura* (CSV).
        2) Cárgalas arriba en esta página.
        3) Selecciona la factura pendiente y pulsa **“Cargar líneas…”** para traer los ítems.
        4) Verifica totales y envía.

        **Notas**
        - Los nombres de columnas son flexibles (se aceptan variantes comunes).
        - Si el CSV de *Líneas Factura* no trae una columna que vincule con la factura (p. ej., “Factura No.”),
          agrega una antes de subir o indícame qué columna usar y lo adapto.
        """
    )

