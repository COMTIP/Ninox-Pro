import streamlit as st
import requests
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
# NINOX API CONFIG
# ==========================
API_TOKEN   = "0b3a1130-785a-11f0-ace0-3fb1fcb242e2"
TEAM_ID     = "ihp8o8AaLzfodwc4J"
DATABASE_ID = "u2g01uaua8tu"

BASE_URL = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}"
HEADERS  = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

# ==========================
# UTILIDADES NINOX
# ==========================
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

def obtener_clientes() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Clientes/records")

def obtener_productos() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Productos/records")

def obtener_facturas() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Facturas/records")

# Tabla con espacio -> URL-encoding
def obtener_notas_credito() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Nota%20de%20Credito/records")

def calcular_siguiente_factura_no(facturas: List[Dict[str, Any]]) -> str:
    max_factura = 0
    for f in facturas:
        valor = (f.get("fields", {}) or {}).get("Factura No.", "")
        try:
            n = int(str(valor).strip() or 0)
            max_factura = max(max_factura, n)
        except Exception:
            continue
    return f"{max_factura + 1:08d}"

def calcular_siguiente_nc_no(notas: List[Dict[str, Any]]) -> str:
    max_nc = 0
    for n in notas:
        valor = (n.get("fields", {}) or {}).get("Credit No.", "")
        try:
            num = int(str(valor).strip() or 0)
            max_nc = max(max_nc, num)
        except Exception:
            continue
    return f"{max_nc + 1:08d}"

# ==========================
# HELPERS PARA LÍNEAS DESDE FACTURAS
# ==========================
def _limpiar_num(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0

def extraer_lineas_desde_factura_record(factura_rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Lee el subtable de líneas embebido dentro de un record de Facturas.
    Soporta nombres: 'LíneasFactura', 'LineasFactura', 'Líneas Factura', 'Lineas Factura'.
    Columnas esperadas: Descripción/Descripcion, Cantidad, Precio Unitario, ITBMS, (opcional) Código/Codigo.
    """
    fields = (factura_rec or {}).get("fields", {}) or {}
    posibles = ["LíneasFactura", "LineasFactura", "Líneas Factura", "Lineas Factura"]
    lineas = None
    for k in posibles:
        if k in fields:
            lineas = fields[k]
            break

    salida: List[Dict[str, Any]] = []
    if isinstance(lineas, list) and lineas:
        for row in lineas:
            rf = row.get("fields", row) if isinstance(row, dict) else {}
            desc   = (rf.get("Descripción") or rf.get("Descripcion") or "").strip()
            cant   = _limpiar_num(rf.get("Cantidad"))
            precio = _limpiar_num(rf.get("Precio Unitario"))
            tasa   = _limpiar_num(rf.get("ITBMS"))  # ej. 0.07 ó 0
            valor_itbms = round(cant * precio * tasa, 2)
            salida.append({
                "codigo":         rf.get("Código", "") or rf.get("Codigo", "") or "",
                "descripcion":    desc or "SIN DESCRIPCIÓN",
                "cantidad":       cant,
                "precioUnitario": precio,
                "tasa":           tasa,
                "valorITBMS":     valor_itbms,
            })
    return salida

# ==========================
# CARGA / REFRESCO DE DATOS
# ==========================
if st.button("Actualizar datos de Ninox"):
    for k in ("clientes", "productos", "facturas", "notas_credito"):
        st.session_state.pop(k, None)

if "clientes" not in st.session_state:
    st.session_state["clientes"] = obtener_clientes()
if "productos" not in st.session_state:
    st.session_state["productos"] = obtener_productos()
if "facturas" not in st.session_state:
    st.session_state["facturas"] = obtener_facturas()
if "notas_credito" not in st.session_state:
    st.session_state["notas_credito"] = obtener_notas_credito()

clientes      = st.session_state["clientes"]
productos     = st.session_state["productos"]
facturas      = st.session_state["facturas"]
notas_credito = st.session_state["notas_credito"]

if not clientes:
    st.warning("No hay clientes en Ninox"); st.stop()
if not productos:
    st.warning("No hay productos en Ninox"); st.stop()

# ==========================
# ÍTEMS (state)
# ==========================
if "line_items" not in st.session_state:
    prev = st.session_state.get("items", [])
    st.session_state["line_items"] = prev if isinstance(prev, list) else []
    st.session_state.pop("items", None)

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
nombres_clientes = [c.get("fields", {}).get("cliente", f"Cliente {i}") for i, c in enumerate(clientes, start=1)]
cliente_idx = st.selectbox("Seleccione Cliente", range(len(nombres_clientes)), format_func=lambda x: nombres_clientes[x])
cliente_fields: Dict[str, Any] = clientes[cliente_idx].get("fields", {}) or {}

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC",       value=cliente_fields.get("RUC", ""),        disabled=True)
    st.text_input("DV",        value=cliente_fields.get("DV", ""),         disabled=True)
    st.text_area ("Dirección", value=cliente_fields.get("Dirección", ""),  disabled=True)
with col2:
    st.text_input("Teléfono",  value=cliente_fields.get("Teléfono", ""),   disabled=True)
    st.text_input("Correo",    value=cliente_fields.get("Correo", ""),     disabled=True)

# ==========================
# NÚMERO DOC + AUTOCARGA DESDE FACTURAS
# ==========================
facturas_pendientes = [
    f for f in facturas
    if ((f.get("fields", {}) or {}).get("Estado", "") or "").strip().lower() == "pendiente"
]

selected_factura_rec = None

if doc_type == "01":
    if facturas_pendientes:
        opciones_facturas = [(f.get("fields", {}) or {}).get("Factura No.", "") for f in facturas_pendientes]
        idx_factura = st.selectbox(
            "Seleccione Factura Pendiente",
            range(len(opciones_facturas)),
            format_func=lambda x: str(opciones_facturas[x])
        )
        numero_preview = str(opciones_facturas[idx_factura])
        selected_factura_rec = facturas_pendientes[idx_factura]
    else:
        numero_preview = calcular_siguiente_factura_no(facturas)
else:
    numero_preview = calcular_siguiente_nc_no(notas_credito)

st.text_input("Factura No." if doc_type == "01" else "Número de Documento Fiscal", value=numero_preview, disabled=True)

# Fecha Emisión (si la factura trae fecha, podrías mapearla aquí; por simplicidad usamos hoy)
fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# Medio de Pago (por defecto desde la factura si existe)
medio_pago_opciones = ["Efectivo", "Débito", "Crédito"]
fact_fields = (selected_factura_rec or {}).get("fields", {}) if selected_factura_rec else {}
medio_pago_default  = (fact_fields.get("Medio de Pago") or "").strip().capitalize()
if medio_pago_default not in medio_pago_opciones:
    medio_pago_default = "Efectivo"

# ==========================
# AUTOCARGA DE ÍTEMS SI SELECCIONA FACTURA
# ==========================
if selected_factura_rec is not None:
    if st.button("Cargar líneas desde la factura seleccionada"):
        st.session_state["line_items"] = extraer_lineas_desde_factura_record(selected_factura_rec)
        if not st.session_state["line_items"]:
            st.warning("La factura no contiene líneas embebidas o no se pudieron leer los campos esperados.")

# ==========================
# ÍTEMS UI
# ==========================
st.header("Ítems del documento (puedes agregar o editar)")
nombres_productos = [
    f"{(p.get('fields', {}) or {}).get('Código','')} | {(p.get('fields', {}) or {}).get('Descripción','')}"
    for p in productos
]
prod_idx    = st.selectbox("Producto", range(len(nombres_productos)), format_func=lambda x: nombres_productos[x])
prod_fields = productos[prod_idx].get("fields", {}) or {}

cantidad    = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
precio_unit = float(prod_fields.get("Precio Unitario", 0) or 0)
itbms_rate  = float(prod_fields.get("ITBMS", 0) or 0)

if st.button("Agregar ítem"):
    valor_itbms = round(itbms_rate * cantidad * precio_unit, 2)
    st.session_state["line_items"].append({
        "codigo":         prod_fields.get("Código", ""),
        "descripcion":    prod_fields.get("Descripción", ""),
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

medio_pago = st.selectbox("Medio de Pago", medio_pago_opciones, index=medio_pago_opciones.index(medio_pago_default))
emisor     = st.text_input("Nombre de quien emite el documento (obligatorio)", value=st.session_state.get("emisor", ""))
if emisor:
    st.session_state["emisor"] = emisor

# ==========================
# BACKEND + EMAIL UI
# ==========================
BACKEND_URL = "https://ninox-factory-server.onrender.com"

enviar_email = st.checkbox("Enviar CAFE por correo al cliente", value=True)
email_destino_default = (cliente_fields.get("Correo") or "").strip()
email_to = st.text_input("Email destino", value=email_destino_default if enviar_email else "", disabled=not enviar_email)
email_cc = st.text_input("CC (opcional, separa por comas)", value="", disabled=not enviar_email)

def _ninox_refrescar_tablas():
    st.session_state["facturas"]      = obtener_facturas()
    st.session_state["notas_credito"] = obtener_notas_credito()

# ==========================
# PAYLOAD A DGI
# ==========================
def armar_payload_documento(
    *,
    doc_type: str,
    numero_documento: str,
    fecha_emision: date,
    cliente_fields: Dict[str, Any],
    items: List[Dict[str, Any]],
    total_neto: float,
    total_itbms: float,
    total: float,
    medio_pago: str,
    motivo_nc: str = "",
    factura_afectada: str = "",
) -> Dict[str, Any]:

    forma_pago_codigo = {"Efectivo": "01", "Débito": "02", "Crédito": "03"}[medio_pago]
    formato_cafe  = 3 if doc_type == "06" else 1
    entrega_cafe  = 3 if doc_type == "06" else 1
    tipo_venta    = "" if doc_type == "06" else 1

    # Motivo + referencia de la factura afectada en 'informacionInteres'
    info_interes = ""
    if doc_type == "06":
        ref = f" (afecta a la factura {factura_afectada.strip()})" if factura_afectada.strip() else ""
        info_interes = (motivo_nc or "Nota de crédito") + ref

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
                "formatoCAFE": formato_cafe,
                "entregaCAFE": entrega_cafe,
                "envioContenedor": 1,
                "procesoGeneracion": 1,
                "tipoVenta": tipo_venta,
                "informacionInteres": info_interes,
                "cliente": {
                    "tipoClienteFE": "02" if (cliente_fields.get("RUC") or "").strip() else "01",
                    "tipoContribuyente": 1,
                    "numeroRUC": (cliente_fields.get("RUC", "") or "").replace("-", ""),
                    "digitoVerificadorRUC": cliente_fields.get("DV", ""),
                    "razonSocial": cliente_fields.get("cliente", ""),
                    "direccion": cliente_fields.get("Dirección", ""),
                    "telefono1": cliente_fields.get("Teléfono", ""),
                    "correoElectronico1": cliente_fields.get("Correo", ""),
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
                "tiempoPago":         "1" if doc_type == "01" else "3",
                "nroItems":           str(len(lista_items)),
                "totalTodosItems":    f"{total:.2f}",
                "listaFormaPago": {
                    "formaPago": [{
                        "formaPagoFact":    forma_pago_codigo,
                        "valorCuotaPagada": f"{total:.2f}",
                    }]
                },
                # Requisito del WS
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
# ENVIAR SIN GENERAR PDF LOCAL
# ==========================
if st.button("Enviar Documento a DGI"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite el documento."); st.stop()
    if not st.session_state["line_items"]:
        st.error("Debe agregar al menos un ítem o cargar las líneas desde la factura."); st.stop()

    motivo_nc = ""
    factura_afectada = ""
    if doc_type == "06":
        st.error("Para Nota de Crédito, habilita los campos correspondientes en la UI.")  # placeholder si luego activas NC
        st.stop()

    numero_documento = numero_preview

    try:
        payload = armar_payload_documento(
            doc_type=doc_type,
            numero_documento=numero_documento,
            fecha_emision=fecha_emision,
            cliente_fields=cliente_fields,
            items=st.session_state["line_items"],
            total_neto=total_neto,
            total_itbms=total_itbms,
            total=total_total,
            medio_pago=medio_pago,
            motivo_nc=motivo_nc,
            factura_afectada=factura_afectada,
        )

        r = requests.post(f"{BACKEND_URL}/enviar-factura", json=payload, timeout=60)
        if r.ok:
            st.success(f"{doc_humano} enviada correctamente ✅")
            st.session_state["line_items"] = []
            _ninox_refrescar_tablas()

            # ===== Envío por email (opcional) =====
            if enviar_email and (email_to or "").strip():
                email_json = {
                    "to": [e.strip() for e in (email_to or "").split(",") if e.strip()],
                    "cc": [e.strip() for e in (email_cc or "").split(",") if e.strip()],
                    "subject": f"{'Nota de Crédito' if doc_type=='06' else 'Factura'} electrónica #{numero_documento}",
                    "body_html": f"""
                    <p>Estimado(a),</p>
                    <p>Se ha generado su {'Nota de Crédito' if doc_type=='06' else 'Factura'} <b>#{numero_documento}</b>.</p>
                    <p>Adjuntamos el CAFE oficial desde nuestro sistema.</p>
                    <p>Saludos,<br>IOM Panamá</p>
                    """,
                    "meta": {
                        "codigoSucursalEmisor":  "0000",
                        "numeroDocumentoFiscal": str(numero_documento),
                        "puntoFacturacionFiscal":"001",
                        "tipoDocumento":         doc_type,
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
        - Tablas Ninox: `Clientes`, `Productos`, `Facturas`, **`Nota de Credito`**.
        - Para cargar los ítems de una factura pendiente, usa el botón **"Cargar líneas desde la factura seleccionada"**.
        - No se genera PDF en la app; el correo se envía llamando a **/enviar-cafe-email** en tu backend.
        - Requisitos WS: `listaPagoPlazo.pagoPlazo[0]` con `fechaVenceCuota` y `valorCuota`.
        - El campo de nombre del cliente se espera como **`cliente`** en la tabla `Clientes`.
        """
    )
