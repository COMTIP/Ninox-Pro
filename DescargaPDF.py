import streamlit as st
import requests
from datetime import date
from typing import List, Dict, Any, Union

# ==========================
# CONFIGURACIÓN / LOGIN
# ==========================
st.set_page_config(page_title="Facturación Electrónica — IOM Panamá", layout="centered")

USUARIOS = {
    "Mispanama": "Maxilo2000",
    "usuario1": "password123",
}

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
    """Descarga todos los registros de una tabla Ninox con paginación."""
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

def as_float(v: Union[str, int, float, None]) -> float:
    """Convierte valores numéricos desde Ninox (soporta '48,00', '1.234,56', etc.)."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "":
        return 0.0
    # Si hay coma decimal (formato ES): quitar separadores de miles y cambiar coma por punto
    if "," in s and s.count(",") == 1:
        s = s.replace(".", "").replace(",", ".")
    # Si queda algo raro, intenta última conversión
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
    """Tabla hija con los ítems de factura."""
    return _ninox_get("/tables/LineasFactura/records")

def calcular_siguiente_factura_no(facturas: List[Dict[str, Any]]) -> str:
    max_factura = 0
    for f in facturas:
        valor = (f.get("fields", {}) or {}).get("Factura No.", "")
        try:
            n = int(str(valor).strip() or 0)
            if n > max_factura:
                max_factura = n
        except Exception:
            continue
    return f"{max_factura + 1:08d}"

# --------------------------
# Relación Factura ↔ Línea
# --------------------------
def _factura_id(rec: Dict[str, Any]) -> str:
    """Devuelve el id Ninox del registro (e.g. 'm4q6…')."""
    return str(rec.get("id") or "")

def _linea_pertenece_a_factura(linea: Dict[str, Any], factura_id: str) -> bool:
    """
    Devuelve True si la línea está vinculada a la factura dada.
    Soporta diferentes formas en que Ninox puede devolver el campo relacional:
    - id simple: 'Factura': 'abcd1234'
    - lista de ids: 'Factura': ['abcd1234', ...]
    - objeto: 'Factura': {'id': 'abcd1234', 'table': 'Facturas'}
    - lista de objetos: 'Factura': [{'id': 'abcd1234'}, ...]
    """
    flds = linea.get("fields", {}) or {}
    link = flds.get("Factura") or flds.get("Facturas") or flds.get("Factura Id")  # nombres posibles
    if not link:
        return False

    def _id_eq(x) -> bool:
        try:
            if isinstance(x, str):
                return x == factura_id
            if isinstance(x, dict):
                return str(x.get("id") or "") == factura_id
            return False
        except Exception:
            return False

    if isinstance(link, list):
        return any(_id_eq(x) for x in link)
    return _id_eq(link)

def lineas_de_factura(lineas: List[Dict[str, Any]], factura_id: str) -> List[Dict[str, Any]]:
    return [lf for lf in lineas if _linea_pertenece_a_factura(lf, factura_id)]

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
    st.warning("No hay clientes en Ninox")
    st.stop()
if not productos:
    st.warning("No hay productos en Ninox")
    st.stop()

# ==========================
# MIGRACIÓN/INICIALIZACIÓN DE ÍTEMS
# ==========================
if "line_items" not in st.session_state:
    prev = st.session_state.get("items", [])
    st.session_state["line_items"] = prev if isinstance(prev, list) else []
    st.session_state.pop("items", None)

# ==========================
# SELECCIÓN DE CLIENTE
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
# FACTURA EXISTENTE O NUEVA
# ==========================
facturas_pendientes = [f for f in facturas if (f.get("fields", {}) or {}).get("Estado", "").strip().lower() == "pendiente"]
if facturas_pendientes:
    opciones_facturas = [(
        f.get("id"),
        (f.get("fields", {}) or {}).get("Factura No.", ""),
    ) for f in facturas_pendientes]
    idx_factura = st.selectbox(
        "Seleccione Factura Pendiente",
        range(len(opciones_facturas)),
        format_func=lambda x: str(opciones_facturas[x][1])
    )
    factura_id_sel, factura_no_preview = opciones_facturas[idx_factura]
else:
    factura_id_sel = ""
    factura_no_preview = calcular_siguiente_factura_no(facturas)

st.text_input("Factura No.", value=factura_no_preview, disabled=True)
fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# ==========================
# NUEVO: CARGAR LÍNEAS DESDE NINOX
# ==========================
def _cargar_lineas_desde_ninox():
    if not factura_id_sel:
        st.warning("Seleccione una factura pendiente para cargar sus líneas.")
        return
    # Filtrar líneas vinculadas a la factura seleccionada
    lns = lineas_de_factura(lineas_factura, factura_id_sel)
    if not lns:
        st.info("Esta factura no tiene líneas asociadas en Ninox.")
        return
    # Limpiar los ítems actuales y poblar desde Ninox
    st.session_state["line_items"] = []
    for lf in lns:
        flds = lf.get("fields", {}) or {}
        codigo      = flds.get("Código", "") or flds.get("Codigo", "") or ""
        descripcion = flds.get("Descripción", "") or flds.get("Descripcion", "") or "SIN DESCRIPCIÓN"
        cantidad    = as_float(flds.get("Cantidad", 0))
        pu          = as_float(flds.get("Precio Unitario", 0))
        tasa        = as_float(flds.get("ITBMS", 0))  # ej. 0.07
        valor_itbms = round(tasa * cantidad * pu, 2)

        st.session_state["line_items"].append({
            "codigo":         codigo,
            "descripcion":    descripcion,
            "cantidad":       float(cantidad),
            "precioUnitario": float(pu),
            "tasa":           float(tasa),
            "valorITBMS":     float(valor_itbms),
        })

st.button("Cargar líneas desde Ninox", on_click=_cargar_lineas_desde_ninox)

# ==========================
# ÍTEMS (Entrada manual adicional)
# ==========================
st.header("Agregar Productos a la Factura")

nombres_productos = [
    f"{(p.get('fields', {}) or {}).get('Código','')} | {(p.get('fields', {}) or {}).get('Descripción','')}"
    for p in productos
]
prod_idx    = st.selectbox("Producto", range(len(nombres_productos)), format_func=lambda x: nombres_productos[x])
prod_fields = productos[prod_idx].get("fields", {}) or {}

cantidad    = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
precio_unit = float(prod_fields.get("Precio Unitario", 0) or 0)
itbms_rate  = float(prod_fields.get("ITBMS", 0) or 0)   # p.ej. 0.07

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
    st.write("#### Ítems de la factura")
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

# TOTALES
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
        st.error("Debe ingresar el nombre de quien emite la factura antes de enviarla.")
        st.stop()
    if not st.session_state["line_items"]:
        st.error("Debe agregar al menos un producto.")
        st.stop()

    forma_pago_codigo = {"Efectivo": "01", "Débito": "02", "Crédito": "03"}[medio_pago]

    # Construcción de ítems payload
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
                "numeroDocumentoFiscal": str(factura_no_preview),
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

    # POST al backend — enviar factura
    try:
        url_envio = f"{BACKEND_URL}/enviar-factura"
        r = requests.post(url_envio, json=payload, timeout=60)
        if r.ok:
            st.success("Factura enviada correctamente. Generando PDF…")
            st.session_state["line_items"] = []
            _ninox_refrescar_facturas()
            st.session_state["ultima_factura_no"] = str(factura_no_preview)

            # Intento de descarga PDF inmediata
            url_pdf = f"{BACKEND_URL}/descargar-pdf"
            pdf_payload = {
                "codigoSucursalEmisor":  "0000",
                "numeroDocumentoFiscal": str(factura_no_preview),
                "puntoFacturacionFiscal":"001",
                "tipoDocumento":         "01",
                "tipoEmision":           "01",
                "serialDispositivo":     "",
            }
            rpdf = requests.post(url_pdf, json=pdf_payload, stream=True, timeout=60)
            ct = rpdf.headers.get("content-type", "")
            if rpdf.ok and ct.startswith("application/pdf"):
                st.session_state["pdf_bytes"] = rpdf.content
                st.session_state["pdf_name"]  = f"Factura_{factura_no_preview}.pdf"
                st.success("¡PDF generado y listo para descargar abajo!")
            else:
                st.session_state["pdf_bytes"] = None
                st.session_state["pdf_name"]  = None
                st.error("Factura enviada, pero no se pudo generar el PDF automáticamente.")
                try:
                    st.write(rpdf.json())
                except Exception:
                    st.write(rpdf.text)
        else:
            st.error("Error al enviar la factura.")
            try:
                st.write(r.json())
            except Exception:
                st.write(r.text)
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
# INFO / AYUDA
# ==========================
with st.expander("Ayuda / Referencias"):
    st.markdown(
        """
        - Tablas Ninox usadas: `Clientes`, `Productos`, `Facturas`, `LineasFactura`.
        - Campos esperados (sensibles a mayúsculas):
          - **Clientes**: Nombre, RUC, DV, Dirección, Teléfono, Correo
          - **Productos**: Código, Descripción, Precio Unitario, ITBMS (decimal; ej. 0.07)
          - **Facturas**: Estado (use "Pendiente"), "Factura No."
          - **LineasFactura**: (relación) Factura → Facturas, Descripción, Cantidad, Precio Unitario, ITBMS, (opcional) Código
        - Botón **“Cargar líneas desde Ninox”**: trae los ítems de la factura seleccionada y recalcula los totales.
        - El parser numérico admite coma decimal (ej. 48,00).
        """
    )
