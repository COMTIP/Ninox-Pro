import streamlit as st
import requests
from datetime import date
from typing import List, Dict, Any, Optional

# ==========================
# CONFIGURACIÓN / LOGIN
# ==========================
st.set_page_config(page_title="Facturación Electrónica — IOM Panamá (API Ninox)", layout="centered")

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
# NINOX API CONFIG (SOLO-API)
# ==========================
API_TOKEN   = "0b3a1130-785a-11f0-ace0-3fb1fcb242e2"  # <-- coloca tu token válido
TEAM_ID     = "ihp8o8AaLzfodwc4J"
DATABASE_ID = "u2g01uaua8tu"

BASE_URL = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}"
HEADERS  = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

# Nombres de tablas (ajústalos si difieren en tu base):
TABLE_CLIENTES       = "Clientes"
TABLE_PRODUCTOS      = "Productos"
TABLE_FACTURAS       = "Facturas"
TABLE_LINEAS_FACTURA = "Lineas Factura"  # si tu tabla no tiene espacio, cámbiala a "LineasFactura"

# ==========================
# UTILIDADES NINOX
# ==========================
def _ninox_get(path: str, params: Optional[Dict[str, Any]] = None, page_size: int = 200) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = dict(params or {})
        q.update({"limit": page_size, "offset": offset})
        url = f"{BASE_URL}{path}"
        try:
            r = requests.get(url, headers=HEADERS, params=q, timeout=30)
        except Exception as e:
            st.error(f"Error de conexión a Ninox: {e}")
            break

        if not r.ok:
            # Mensaje claro cuando el plan no permite API
            if r.status_code == 403:
                st.error(f"Ninox 403 — Tu plan no permite acceso continuo a la API. {r.text}")
            else:
                st.error(f"Error Ninox GET {path}: {r.status_code} — {r.text}")
            break

        batch = r.json() or []
        out.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return out

def obtener_tabla(tablename: str) -> List[Dict[str, Any]]:
    # URL-encode sencillo para espacios
    safe_name = tablename.replace(" ", "%20")
    return _ninox_get(f"/tables/{safe_name}/records")

def obtener_clientes() -> List[Dict[str, Any]]:
    return obtener_tabla(TABLE_CLIENTES)

def obtener_productos() -> List[Dict[str, Any]]:
    return obtener_tabla(TABLE_PRODUCTOS)

def obtener_facturas() -> List[Dict[str, Any]]:
    return obtener_tabla(TABLE_FACTURAS)

def obtener_lineas_factura() -> List[Dict[str, Any]]:
    # intenta con espacio y sin espacio
    datos = obtener_tabla(TABLE_LINEAS_FACTURA)
    if not datos and " " in TABLE_LINEAS_FACTURA:
        alt = TABLE_LINEAS_FACTURA.replace(" ", "")
        datos = obtener_tabla(alt)
    return datos

# ==========================
# HELPERS DE DATOS
# ==========================
def _clean_num(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0

def _fields(rec: Dict[str, Any]) -> Dict[str, Any]:
    return (rec.get("fields", {}) or {})

def _extraer_lineas_embebidas(factura_rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Si tu tabla Facturas tiene un subtable embebido (p.ej. 'LíneasFactura' o 'LineasFactura'),
    lo toma directo del record.
    """
    f = _fields(factura_rec)
    posibles = ["LíneasFactura", "LineasFactura", "Líneas Factura", "Lineas Factura"]
    lineas = None
    for k in posibles:
        if k in f:
            lineas = f[k]
            break

    out: List[Dict[str, Any]] = []
    if isinstance(lineas, list):
        for row in lineas:
            rf = row.get("fields", row) if isinstance(row, dict) else {}
            desc   = (rf.get("Descripción") or rf.get("Descripcion") or "").strip()
            cant   = _clean_num(rf.get("Cantidad"))
            pu     = _clean_num(rf.get("Precio Unitario"))
            tasa   = _clean_num(rf.get("ITBMS"))
            itbmsv = round(cant * pu * tasa, 2)
            out.append({
                "codigo":         rf.get("Código", "") or rf.get("Codigo", "") or "",
                "descripcion":    desc or "SIN DESCRIPCIÓN",
                "cantidad":       float(cant),
                "precioUnitario": float(pu),
                "tasa":           float(tasa),
                "valorITBMS":     float(itbmsv),
            })
    return out

def _extraer_lineas_por_tabla(numero_factura: str, lineas_api: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Si las líneas están en una tabla aparte (Lineas Factura), filtramos por relación.
    Campos probables: 'Factura No.' (texto/num), o enlace-relación (ID) — adapta aquí si usas otro campo.
    """
    out: List[Dict[str, Any]] = []
    for rec in lineas_api:
        rf = _fields(rec)
        # Match por "Factura No." (ajusta si usas otro campo de relación)
        rel_ok = False
        for key in ["Factura No.", "Factura", "FacturaNo", "Factura_Numero"]:
            if key in rf and str(rf[key]).strip() == str(numero_factura).strip():
                rel_ok = True
                break
        if not rel_ok:
            continue

        desc   = (rf.get("Descripción") or rf.get("Descripcion") or "").strip()
        cant   = _clean_num(rf.get("Cantidad"))
        pu     = _clean_num(rf.get("Precio Unitario"))
        tasa   = _clean_num(rf.get("ITBMS"))
        itbmsv = round(cant * pu * tasa, 2)
        out.append({
            "codigo":         rf.get("Código", "") or rf.get("Codigo", "") or "",
            "descripcion":    desc or "SIN DESCRIPCIÓN",
            "cantidad":       float(cant),
            "precioUnitario": float(pu),
            "tasa":           float(tasa),
            "valorITBMS":     float(itbmsv),
        })
    return out

def calcular_siguiente_factura_no(facturas: List[Dict[str, Any]]) -> str:
    max_factura = 0
    for f in facturas:
        valor = _fields(f).get("Factura No.", "")
        try:
            n = int(str(valor).strip() or 0)
            max_factura = max(max_factura, n)
        except Exception:
            continue
    return f"{max_factura + 1:08d}"

# ==========================
# CARGA / REFRESCO DE DATOS
# ==========================
if st.button("Actualizar datos de Ninox"):
    for k in ("clientes", "productos", "facturas", "lineas_factura"):
        st.session_state.pop(k, None)

if "clientes" not in st.session_state:
    st.session_state["clientes"] = obtener_clientes()
if "productos" not in st.session_state:
    st.session_state["productos"] = obtener_productos()
if "facturas" not in st.session_state:
    st.session_state["facturas"] = obtener_facturas()
if "lineas_factura" not in st.session_state:
    st.session_state["lineas_factura"] = obtener_lineas_factura()

clientes  = st.session_state["clientes"]
productos = st.session_state["productos"]
facturas  = st.session_state["facturas"]
lineas    = st.session_state["lineas_factura"]

if not clientes:
    st.warning("No hay clientes en Ninox (API)."); st.stop()
if not productos:
    st.warning("No hay productos en Ninox (API)."); st.stop()
if not facturas:
    st.warning("No hay facturas en Ninox (API)."); st.stop()

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

# Lista legible de clientes
def _nombre_cliente(c: Dict[str, Any], idx: int) -> str:
    f = _fields(c)
    return f.get("cliente") or f.get("Nombre") or f"Cliente {idx}"

nombres_clientes = [_nombre_cliente(c, i+1) for i, c in enumerate(clientes)]
cliente_idx = st.selectbox("Seleccione Cliente", range(len(clientes)), format_func=lambda x: nombres_clientes[x])
cliente_fields = _fields(clientes[cliente_idx])

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC",       value=(cliente_fields.get("RUC") or ""),        disabled=True)
    st.text_input("DV",        value=(cliente_fields.get("DV") or ""),         disabled=True)
    st.text_area ("Dirección", value=(cliente_fields.get("Dirección") or cliente_fields.get("Direccion") or ""), disabled=True)
with col2:
    st.text_input("Teléfono",  value=(cliente_fields.get("Teléfono") or cliente_fields.get("Telefono") or ""), disabled=True)
    st.text_input("Correo",    value=(cliente_fields.get("Correo") or ""),     disabled=True)

# ==========================
# NÚMERO DOC + FACTURA PENDIENTE
# ==========================
facturas_pend = [f for f in facturas if str((_fields(f).get("Estado") or "")).strip().lower() == "pendiente"]

selected_factura_rec = None
if doc_type == "01":
    if facturas_pend:
        opciones_facturas = [str(_fields(f).get("Factura No.", "")) for f in facturas_pend]
        idx_factura = st.selectbox("Seleccione Factura Pendiente", range(len(opciones_facturas)),
                                   format_func=lambda x: opciones_facturas[x])
        numero_preview = str(opciones_facturas[idx_factura])
        selected_factura_rec = facturas_pend[idx_factura]
    else:
        numero_preview = calcular_siguiente_factura_no(facturas)
else:
    # Si luego agregas NC por API, genera correlativo según tu tabla de NC
    numero_preview = "00000001"

st.text_input("Número de Documento Fiscal", value=numero_preview, disabled=True)
fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# Medio de pago (si la factura lo trae)
medio_pago_opciones = ["Efectivo", "Débito", "Crédito"]
medio_pago_default = "Efectivo"
if selected_factura_rec:
    mp = str(_fields(selected_factura_rec).get("Medio de Pago") or "").strip().capitalize()
    if mp in medio_pago_opciones:
        medio_pago_default = mp

# ==========================
# AUTOCARGA DE ÍTEMS (API)
# ==========================
st.divider()
if selected_factura_rec is not None:
    if st.button("Cargar líneas desde la factura (API)"):
        # 1) Intento subtabla embebida
        items = _extraer_lineas_embebidas(selected_factura_rec)

        # 2) Si no hay subtabla, intento por tabla Lineas Factura (match por 'Factura No.')
        if not items:
            items = _extraer_lineas_por_tabla(numero_preview, lineas)

        st.session_state["line_items"] = items
        if not items:
            st.warning("No se encontraron líneas (ni subtabla embebida ni coincidencias en 'Lineas Factura').")

# ==========================
# ÍTEMS: AGREGAR MANUAL (desde Productos)
# ==========================
st.header("Ítems del documento (puedes agregar o editar)")
# Menú productos (código | descripción)
def _label_prod(p: Dict[str, Any]) -> str:
    f = _fields(p)
    return f"{f.get('Código','') or f.get('Codigo','')} | {f.get('Descripción','') or f.get('Descripcion','')}"

prod_labels = [_label_prod(p) for p in productos]
prod_idx = st.selectbox("Producto", range(len(productos)), format_func=lambda x: prod_labels[x])
pf = _fields(productos[prod_idx])

cantidad    = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
precio_unit = _clean_num(pf.get("Precio Unitario") or pf.get("PU"))
itbms_rate  = _clean_num(pf.get("ITBMS") or 0)

if st.button("Agregar ítem"):
    valor_itbms = round(itbms_rate * float(cantidad) * float(precio_unit), 2)
    st.session_state["line_items"].append({
        "codigo":         pf.get("Código", "") or pf.get("Codigo", "") or "",
        "descripcion":    pf.get("Descripción", "") or pf.get("Descripcion", "") or "SIN DESCRIPCIÓN",
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
    st.session_state["facturas"]       = obtener_facturas()
    st.session_state["lineas_factura"] = obtener_lineas_factura()

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

    info_interes = ""
    if doc_type == "06":
        ref = f" (afecta a la factura {str(factura_afectada).strip()})" if str(factura_afectada).strip() else ""
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
                "tipoDocumento": doc_type,
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
                    "razonSocial": cliente_fields.get("cliente") or cliente_fields.get("Nombre") or "",
                    "direccion": cliente_fields.get("Dirección") or cliente_fields.get("Direccion") or "",
                    "telefono1": cliente_fields.get("Teléfono") or cliente_fields.get("Telefono") or "",
                    "correoElectronico1": cliente_fields.get("Correo") or "",
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
# ENVIAR (BACKEND)
# ==========================
if st.button("Enviar Documento a DGI"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite el documento."); st.stop()
    if not st.session_state["line_items"]:
        st.error("Debe agregar al menos un ítem o cargar las líneas desde la factura (API)."); st.stop()

    # NC no activada en esta versión (se puede habilitar rápido si la necesitas)
    motivo_nc = ""
    factura_afectada = ""

    try:
        payload = armar_payload_documento(
            doc_type=doc_type,
            numero_documento=numero_preview,
            fecha_emision=fecha_emision,
            cliente_fields=cliente_fields,
            items=st.session_state["line_items"],
            total_neto=sum(i["cantidad"] * i["precioUnitario"] for i in st.session_state["line_items"]),
            total_itbms=sum(i["valorITBMS"] for i in st.session_state["line_items"]),
            total=sum(i["cantidad"] * i["precioUnitario"] + i["valorITBMS"] for i in st.session_state["line_items"]),
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
with st.expander("Ayuda / Referencias (API Ninox)"):
    st.markdown(
        """
        - Esta versión usa **exclusivamente la API de Ninox** (sin CSV).
        - Asegura que tu plan Ninox tenga acceso a API (Business/Enterprise).
        - Tablas esperadas: `Clientes`, `Productos`, `Facturas`, `Lineas Factura` (o `LineasFactura`).
        - Para cargar ítems: selecciona una **Factura Pendiente** y pulsa **“Cargar líneas desde la factura (API)”**.
        - Si tus campos tienen otro nombre (p. ej. “PU”, “ITBMS %”, “Cliente Nombre”), dímelos y te ajusto el parser.
        """
    )



