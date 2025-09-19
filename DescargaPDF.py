import streamlit as st
import requests
from datetime import date
from typing import List, Dict, Any, Union
import re

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
API_TOKEN   = "03035f50-93e2-11f0-883e-db77626d62e5"
TEAM_ID     = "fhmgaLpFghyh5sNHh"
DATABASE_ID = "er0sibgl3dug"

BASE_URL = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}"
HEADERS  = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

# ==========================
# UTILIDADES
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

_num_keep = re.compile(r"[^0-9\-,\.]")  # elimina todo lo que NO sea dígito, coma, punto o signo -
def as_float(v: Union[str, int, float, None]) -> float:
    """Convierte valores tipo '48,00', '$25,50', '1.234,56'."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "":
        return 0.0
    s = _num_keep.sub("", s)  # quita $ y otros símbolos
    # si hay coma decimal única, convertir a punto y eliminar separadores de miles
    if s.count(",") == 1 and (s.rfind(",") > s.rfind(".")):
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

# ==========================
# LECTURA DE TABLAS
# ==========================
def obtener_clientes() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Clientes/records")

def obtener_productos() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Productos/records")

def obtener_facturas() -> List[Dict[str, Any]]:
    return _ninox_get("/tables/Facturas/records")

def obtener_lineas_factura() -> List[Dict[str, Any]]:
    # OJO: nombre con espacio
    return _ninox_get("/tables/Lineas%20Factura/records")

def calcular_siguiente_factura_no(facturas: List[Dict[str, Any]]) -> str:
    max_factura = 0
    for f in facturas:
        valor = (f.get("fields", {}) or {}).get("Factura No.", "")
        try:
            n = int(str(valor).strip() or 0)
            max_factura = max(max_factura, n)
        except Exception:
            pass
    return f"{max_factura + 1:08d}"

# --------------------------
# Relación Factura ↔ Línea
# --------------------------
def _linea_pertenece_a_factura(linea: Dict[str, Any], factura_id: str) -> bool:
    flds = linea.get("fields", {}) or {}
    # nombres comunes del link
    link = flds.get("Factura") or flds.get("Facturas") or flds.get("Factura Id") or flds.get("FacturaRef")
    if not link:
        return False

    def _eq(x) -> bool:
        if isinstance(x, str):
            return x == factura_id
        if isinstance(x, dict):
            return str(x.get("id") or "") == factura_id
        return False

    if isinstance(link, list):
        return any(_eq(x) for x in link)
    return _eq(link)

def lineas_de_factura(factura_id: str, lineas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [lf for lf in lineas if _linea_pertenece_a_factura(lf, factura_id)]

def item_desde_linea(fields: Dict[str, Any]) -> Dict[str, Any]:
    codigo      = fields.get("Código", "") or fields.get("Codigo", "") or ""
    descripcion = fields.get("Descripción", "") or fields.get("Descripcion", "") or "SIN DESCRIPCIÓN"
    cantidad    = as_float(fields.get("Cantidad", 0))
    pu          = as_float(fields.get("Precio Unitario", 0))
    tasa        = as_float(fields.get("ITBMS", 0))
    valor_itbms = round(tasa * cantidad * pu, 2)
    return {
        "codigo":         codigo,
        "descripcion":    descripcion,
        "cantidad":       float(cantidad),
        "precioUnitario": float(pu),
        "tasa":           float(tasa),
        "valorITBMS":     float(valor_itbms),
    }

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

clientes       = st.session_state["clientes"]
productos      = st.session_state["productos"]
facturas       = st.session_state["facturas"]
lineas_factura = st.session_state["lineas_factura"]

if not clientes:
    st.warning("No hay clientes en Ninox"); st.stop()
if not productos:
    st.warning("No hay productos en Ninox"); st.stop()

# ==========================
# STATE ÍTEMS
# ==========================
if "line_items" not in st.session_state:
    st.session_state["line_items"] = []
if "lock_items" not in st.session_state:
    st.session_state["lock_items"] = True  # bloquea edición cuando vienen de Ninox

# ==========================
# CLIENTE
# ==========================
st.header("Datos del Cliente")
nombres_clientes = [c.get("fields", {}).get("Nombre", f"Cliente {i}") for i, c in enumerate(clientes, start=1)]
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
# FACTURA: SELECCIÓN Y AUTO-CARGA
# ==========================
st.header("Factura")

# mapa numero -> id
map_no_to = {}
for f in facturas:
    flds = f.get("fields", {}) or {}
    no   = str(flds.get("Factura No.", "")).strip()
    if no:
        map_no_to[no] = f.get("id")

siguiente_no = calcular_siguiente_factura_no(facturas)

colf1, colf2 = st.columns([2,1])
with colf1:
    opciones = ["(Nueva) " + siguiente_no] + sorted(map_no_to.keys())
    sel = st.selectbox("Factura (existente por número)", opciones, key="sel_factura_no")
with colf2:
    st.checkbox("Bloquear edición si viene de Ninox", value=st.session_state["lock_items"],
                key="lock_items")

# número visible y editable si quieres escribirlo manualmente
factura_no = st.text_input("Factura No.", value=(siguiente_no if sel.startswith("(Nueva)") else sel),
                           help="Escribe o selecciona un número existente para cargar sus ítems automáticamente.")

# Detecta si ese número existe en Ninox
factura_id_sel = map_no_to.get(factura_no.strip())

# Si existe, traer SIEMPRE las líneas más recientes desde Ninox (no usamos cache)
if factura_id_sel:
    # refresco de lineas por si cambiaste algo en Ninox
    lineas_factura = obtener_lineas_factura()
    st.session_state["lineas_factura"] = lineas_factura

    lns = lineas_de_factura(factura_id_sel, lineas_factura)
    st.session_state["line_items"] = [item_desde_linea((lf.get("fields") or {})) for lf in lns]
    st.session_state["lock_items"] = True  # bloquear por defecto cuando vienen de Ninox
else:
    # Nueva factura: no tocamos lo que el usuario añada manualmente
    pass

fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# ==========================
# ÍTEMS (ocultar si bloqueado)
# ==========================
if not st.session_state["lock_items"]:
    st.header("Agregar Productos manualmente")
    nombres_productos = [
        f"{(p.get('fields', {}) or {}).get('Código','')} | {(p.get('fields', {}) or {}).get('Descripción','')}"
        for p in productos
    ]
    prod_idx    = st.selectbox("Producto", range(len(nombres_productos)),
                               format_func=lambda x: nombres_productos[x])
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
else:
    st.info("Ítems cargados automáticamente desde Ninox.")

# Mostrar ítems (solo lectura si vienen de Ninox)
if st.session_state["line_items"]:
    st.write("#### Ítems de la factura")
    for idx, i in enumerate(st.session_state["line_items"], start=1):
        st.write(f"{idx}. {i['codigo']} | {i['descripcion']} | Cant: {i['cantidad']:.2f} | "
                 f"P.U.: {i['precioUnitario']:.2f} | ITBMS: {i['valorITBMS']:.2f}")

    if not st.session_state["lock_items"]:
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
total_neto    = sum(i["cantidad"] * i["precioUnitario"] for i in st.session_state["line_items"])
total_itbms   = sum(i["valorITBMS"] for i in st.session_state["line_items"])
total_factura = total_neto + total_itbms
st.write(f"**Total Neto:** {total_neto:.2f}   **ITBMS:** {total_itbms:.2f}   **Total a Pagar:** {total_factura:.2f}")

medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Débito", "Crédito"])
emisor     = st.text_input("Nombre de quien emite la factura (obligatorio)", value=st.session_state.get("emisor", ""))
if emisor:
    st.session_state["emisor"] = emisor

# ==========================
# BACKEND DGI
# ==========================
BACKEND_URL = "https://ninox-factory-server.onrender.com"

if "pdf_bytes" not in st.session_state:
    st.session_state["pdf_bytes"] = None
    st.session_state["pdf_name"]  = None

def _ninox_refrescar_facturas():
    st.session_state["facturas"] = obtener_facturas()

# ==========================
# ENVIAR A DGI
# ==========================
if st.button("Enviar Factura a DGI"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite la factura antes de enviarla."); st.stop()
    if not st.session_state["line_items"]:
        st.error("Debe haber al menos un ítem (de Ninox o manual)."); st.stop()

    forma_pago_codigo = {"Efectivo": "01", "Débito": "02", "Crédito": "03"}[medio_pago]

    lista_items = []
    for i in st.session_state["line_items"]:
        precio_item = i["cantidad"] * i["precioUnitario"]
        valor_total = precio_item + i["valorITBMS"]
        tasa_itbms  = "01" if (i.get("tasa", 0) or 0) > 0 else "00"
        lista_items.append({
            "codigo":                  i["codigo"] or "0",
            "descripcion":             i["descripcion"] or "SIN DESCRIPCIÓN",
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
                "tipoDocumento": "01",
                "numeroDocumentoFiscal": str(factura_no),
                "puntoFacturacionFiscal": "001",
                "naturalezaOperacion": "01",
                "tipoOperacion": 1,
                "destinoOperacion": 1,
                "formatoCAFE": 1,
                "entregaCAFE": 1,
                "envioContenedor": 1,
                "procesoGeneracion": 1,
                "tipoVenta": 1,
                "fechaEmision": f"{fecha_emision.isoformat()}T09:00:00-05:00",
                "cliente": {
                    "tipoClienteFE": "02",
                    "tipoContribuyente": 1,
                    "numeroRUC": (cliente_fields.get("RUC", "") or "").replace("-", ""),
                    "digitoVerificadorRUC": cliente_fields.get("DV", ""),
                    "razonSocial": cliente_fields.get("Nombre", ""),
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
                "totalFactura":       f"{total_factura:.2f}",
                "totalValorRecibido": f"{total_factura:.2f}",
                "vuelto":             "0.00",
                "tiempoPago":         "1",
                "nroItems":           str(len(lista_items)),
                "totalTodosItems":    f"{total_factura:.2f}",
                "listaFormaPago": {
                    "formaPago": [{
                        "formaPagoFact":    forma_pago_codigo,
                        "valorCuotaPagada": f"{total_factura:.2f}",
                    }]
                },
            },
        }
    }

    try:
        r = requests.post(f"{BACKEND_URL}/enviar-factura", json=payload, timeout=60)
        if r.ok:
            st.success("Factura enviada correctamente. Generando PDF…")
            st.session_state["line_items"] = []
            _ninox_refrescar_facturas()
            st.session_state["ultima_factura_no"] = str(factura_no)

            rpdf = requests.post(f"{BACKEND_URL}/descargar-pdf", json={
                "codigoSucursalEmisor":  "0000",
                "numeroDocumentoFiscal": str(factura_no),
                "puntoFacturacionFiscal":"001",
                "tipoDocumento":         "01",
                "tipoEmision":           "01",
                "serialDispositivo":     "",
            }, stream=True, timeout=60)
            ct = rpdf.headers.get("content-type", "")
            if rpdf.ok and ct.startswith("application/pdf"):
                st.session_state["pdf_bytes"] = rpdf.content
                st.session_state["pdf_name"]  = f"Factura_{factura_no}.pdf"
                st.success("¡PDF generado y listo para descargar abajo!")
            else:
                st.session_state["pdf_bytes"] = None
                st.session_state["pdf_name"]  = None
                st.error("Factura enviada, pero no se pudo generar el PDF automáticamente.")
                try: st.write(rpdf.json())
                except Exception: st.write(rpdf.text)
        else:
            st.error("Error al enviar la factura.")
            try: st.write(r.json())
            except Exception: st.write(r.text)
    except Exception as e:
        st.error(f"Error de conexión con el backend: {e}")

# ==========================
# DESCARGA PDF
# ==========================
if st.session_state.get("pdf_bytes") and st.session_state.get("pdf_name"):
    st.markdown("---")
    st.header("Descargar PDF de la Factura Electrónica")
    st.download_button(
        label="Descargar PDF",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state["pdf_name"],
        mime="application/pdf",
    )

# ==========================
# AYUDA
# ==========================
with st.expander("Ayuda / Referencias"):
    st.markdown(
        """
        - Tablas: `Clientes`, `Productos`, `Facturas`, `Lineas Factura` (con espacio).
        - Al seleccionar o escribir un **Factura No.** que exista en Ninox,
          se cargan **automáticamente** sus líneas y se bloquea la edición (puedes desactivar el bloqueo).
        - El parser numérico acepta `$25,50`, `1.234,56`, etc.
        """
    )
