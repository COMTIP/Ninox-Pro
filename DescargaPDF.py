import streamlit as st
import requests
from datetime import datetime, date
from typing import List, Dict, Any

# ==========================
# CONFIGURACIÓN / LOGIN
# ==========================
st.set_page_config(page_title="Facturación Electrónica — IOM Panamá", layout="centered")

USUARIOS = {
    "Mispanama": "Maxilo2000",
    "usuario1": "password123",
}

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.markdown("<h2 style='text-align:center; color:#1c6758'>Acceso</h2>", unsafe_allow_html=True)
    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Ingresar", type="primary"):
        if usuario in USUARIOS and password == USUARIOS[usuario]:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")
    st.stop()

if st.sidebar.button("Cerrar sesión"):
    st.session_state.autenticado = False
    st.rerun()

# ==========================
# NINOX API CONFIG
# ==========================
API_TOKEN = "0b3a1130-785a-11f0-ace0-3fb1fcb242e2"  # indicado por el usuario
TEAM_ID = "ihp8o8AaLzfodwc4J"
DATABASE_ID = "u2g01uaua8tu"

BASE_URL = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

# ==========================
# UTILIDADES NINOX
# ==========================

def _ninox_get(path: str, params: Dict[str, Any] | None = None, *, page_size: int = 200) -> List[Dict[str, Any]]:
    """Descarga todos los registros de una tabla Ninox con paginación."""
    out: List[Dict[str, Any]] = []
    offset = 0
    while True:
        p = dict(params or {})
        p.update({"limit": page_size, "offset": offset})
        url = f"{BASE_URL}{path}"
        r = requests.get(url, headers=HEADERS, params=p, timeout=30)
        if not r.ok:
            st.error(f"Error Ninox GET {path}: {r.status_code} — {r.text}")
            return out
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

# ==========================
# CARGA / REFRESCO DE DATOS
# ==========================

if st.button("Actualizar datos de Ninox", type="secondary"):
    for k in ("clientes", "productos", "facturas"):
        st.session_state.pop(k, None)

if "clientes" not in st.session_state:
    st.session_state.clientes = obtener_clientes()
if "productos" not in st.session_state:
    st.session_state.productos = obtener_productos()
if "facturas" not in st.session_state:
    st.session_state.facturas = obtener_facturas()

clientes = st.session_state.clientes
productos = st.session_state.productos
facturas = st.session_state.facturas

if not clientes:
    st.warning("No hay clientes en Ninox")
    st.stop()
if not productos:
    st.warning("No hay productos en Ninox")
    st.stop()

# ==========================
# SELECCIÓN DE CLIENTE
# ==========================

st.header("Datos del Cliente")

nombres_clientes = [c.get('fields', {}).get('Nombre', f"Cliente {i}") for i, c in enumerate(clientes, start=1)]
cliente_idx = st.selectbox("Seleccione Cliente", range(len(nombres_clientes)), format_func=lambda x: nombres_clientes[x])
cliente_fields: Dict[str, Any] = clientes[cliente_idx].get("fields", {})

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC", value=cliente_fields.get('RUC', ''), disabled=True)
    st.text_input("DV", value=cliente_fields.get('DV', ''), disabled=True)
    st.text_area("Dirección", value=cliente_fields.get('Dirección', ''), disabled=True)
with col2:
    st.text_input("Teléfono", value=cliente_fields.get('Teléfono', ''), disabled=True)
    st.text_input("Correo", value=cliente_fields.get('Correo', ''), disabled=True)

# ==========================
# FACTURA EXISTENTE O NUEVA
# ==========================

facturas_pendientes = [f for f in facturas if (f.get("fields", {}).get("Estado", "").strip().lower() == "pendiente")]
if facturas_pendientes:
    opciones_facturas = [f.get('fields', {}).get("Factura No.", "") for f in facturas_pendientes]
    idx_factura = st.selectbox("Seleccione Factura Pendiente", range(len(opciones_facturas)), format_func=lambda x: opciones_facturas[x])
    factura_no_preview = str(opciones_facturas[idx_factura])
else:
    factura_no_preview = calcular_siguiente_factura_no(facturas)

st.text_input("Factura No.", value=factura_no_preview, disabled=True)
fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# ==========================
# ÍTEMS
# ==========================

st.header("Agregar Productos a la Factura")
if "line_items" not in st.session_state:
    st.session_state['line_items'] = []

nombres_productos = [
    f"{(p.get('fields', {}) or {}).get('Código','')} | {(p.get('fields', {}) or {}).get('Descripción','')}"
    for p in productos
]
prod_idx = st.selectbox("Producto", range(len(nombres_productos)), format_func=lambda x: nombres_productos[x])
prod_fields = productos[prod_idx].get("fields", {})

cantidad = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
precio_unit = float(prod_fields.get('Precio Unitario', 0) or 0)
# ITBMS esperado como decimal (p.ej., 0.07). Si no existe, asumimos 0.
itbms_rate = float(prod_fields.get('ITBMS', 0) or 0)

if st.button("Agregar ítem", type="primary"):
    valor_itbms = round(itbms_rate * cantidad * precio_unit, 2)
    st.session_state['line_items'].append({
        "codigo": prod_fields.get('Código', ''),
        "descripcion": prod_fields.get('Descripción', ''),
        "cantidad": float(cantidad),
        "precioUnitario": float(precio_unit),
        "tasa": float(itbms_rate),
        "valorITBMS": float(valor_itbms),
    })

if st.session_state['line_items']:
    st.write("#### Ítems de la factura")
    for idx, i in enumerate(st.session_state['line_items']):
        st.write(f"{idx+1}. {i['codigo']} | {i['descripcion']} | Cant: {i['cantidad']:.2f} | P.U.: {i['precioUnitario']:.2f} | ITBMS: {i['valorITBMS']:.2f}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Limpiar Ítems", type="secondary"):
            st.session_state['line_items'] = []
    with c2:
        idx_del = st.number_input("Eliminar ítem #", min_value=0, value=0, step=1)
        if st.button("Eliminar", type="secondary"):
            if 0 < idx_del <= len(st.session_state['line_items']):
                st.session_state['line_items'].pop(idx_del-1)

# TOTALES
_total_neto = sum(i["cantidad"] * i["precioUnitario"] for i in st.session_state['line_items'])
_total_itbms = sum(i["valorITBMS"] for i in st.session_state['line_items'])
_total_factura = _total_neto + _total_itbms

st.write(f"**Total Neto:** {_total_neto:.2f}   **ITBMS:** {_total_itbms:.2f}   **Total a Pagar:** {_total_factura:.2f}")

medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Débito", "Crédito"])  # Map: 01, 02, 03
emisor = st.text_input("Nombre de quien emite la factura (obligatorio)", value=st.session_state.get("emisor", ""))
if emisor:
    st.session_state["emisor"] = emisor

# ==========================
# BACKEND DGI
# ==========================

BACKEND_URL = "https://ninox-factory-server.onrender.com"

if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None
    st.session_state.pdf_name = None


def _ninox_refrescar_facturas():
    st.session_state.facturas = obtener_facturas()


# ==========================
# ENVIAR A DGI
# ==========================

if st.button("Enviar Factura a DGI", type="primary"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite la factura antes de enviarla.")
        st.stop()
    if not st.session_state['line_items']:
        st.error("Debe agregar al menos un producto.")
        st.stop()

    # Map medio de pago
    forma_pago_codigo = {"Efectivo": "01", "Débito": "02", "Crédito": "03"}[medio_pago]

    # Construcción de ítems para el payload
    lista_items = []
    for i in st.session_state['line_items']:
        precio_item = i['cantidad'] * i['precioUnitario']
        valor_total = precio_item + i['valorITBMS']
        tasa_itbms = "01" if (i.get("tasa", 0) or 0) > 0 else "00"
        lista_items.append({
            "codigo": i["codigo"] or "0",
            "descripcion": i["descripcion"] or "SIN DESCRIPCIÓN",
            "codigoGTIN": "0",
            "cantidad": f"{i['cantidad']:.2f}",
            "precioUnitario": f"{i['precioUnitario']:.2f}",
            "precioUnitarioDescuento": "0.00",
            "precioItem": f"{precio_item:.2f}",
            "valorTotal": f"{valor_total:.2f}",
            "cantGTINCom": f"{i['cantidad']:.2f}",
            "codigoGTINInv": "0",
            "tasaITBMS": tasa_itbms,
            "valorITBMS": f"{i['valorITBMS']:.2f}",
            "cantGTINComInv": f"{i['cantidad']:.2f}",
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
                    "numeroRUC": (cliente_fields.get('RUC', '') or '').replace('-', ''),
                    "digitoVerificadorRUC": cliente_fields.get('DV', ''),
                    "razonSocial": cliente_fields.get('Nombre', ''),
                    "direccion": cliente_fields.get('Dirección', ''),
                    "telefono1": cliente_fields.get('Teléfono', ''),
                    "correoElectronico1": cliente_fields.get('Correo', ''),
                    "pais": "PA",
                },
            },
            "listaItems": {"item": lista_items},
            "totalesSubTotales": {
                "totalPrecioNeto": f"{_total_neto:.2f}",
                "totalITBMS": f"{_total_itbms:.2f}",
                "totalMontoGravado": f"{_total_itbms:.2f}",
                "totalDescuento": "0.00",
                "totalAcarreoCobrado": "0.00",
                "valorSeguroCobrado": "0.00",
                "totalFactura": f"{_total_factura:.2f}",
                "totalValorRecibido": f"{_total_factura:.2f}",
                "vuelto": "0.00",
                "tiempoPago": "1",
                "nroItems": str(len(lista_items)),
                "totalTodosItems": f"{_total_factura:.2f}",
                "listaFormaPago": {"formaPago": [{
                    "formaPagoFact": forma_pago_codigo,
                    "valorCuotaPagada": f"{_total_factura:.2f}",
                }]},
            },
        }
    }

    # POST al backend — enviar factura
    try:
        url_envio = f"{BACKEND_URL}/enviar-factura"
        r = requests.post(url_envio, json=payload, timeout=60)
        if r.ok:
            st.success("Factura enviada correctamente. Generando PDF…")
            st.session_state['line_items'] = []
            _ninox_refrescar_facturas()
            st.session_state.ultima_factura_no = str(factura_no_preview)

            # Intento de descarga PDF inmediata
            url_pdf = f"{BACKEND_URL}/descargar-pdf"
            pdf_payload = {
                "codigoSucursalEmisor": "0000",
                "numeroDocumentoFiscal": str(factura_no_preview),
                "puntoFacturacionFiscal": "001",
                "tipoDocumento": "01",
                "tipoEmision": "01",
                "serialDispositivo": "",
            }
            rpdf = requests.post(url_pdf, json=pdf_payload, stream=True, timeout=60)
            ct = rpdf.headers.get("content-type", "")
            if rpdf.ok and ct.startswith("application/pdf"):
                st.session_state.pdf_bytes = rpdf.content
                st.session_state.pdf_name = f"Factura_{factura_no_preview}.pdf"
                st.success("¡PDF generado y listo para descargar abajo!")
            else:
                st.session_state.pdf_bytes = None
                st.session_state.pdf_name = None
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
        - Base Ninox: `Clientes`, `Productos`, `Facturas`.
        - Campos esperados (sensibles a mayúsculas):
          - **Clientes**: Nombre, RUC, DV, Dirección, Teléfono, Correo
          - **Productos**: Código, Descripción, Precio Unitario, ITBMS (decimal; ej. 0.07)
          - **Facturas**: Estado (use "Pendiente" para listar aquí), "Factura No." (numérico consecutivo)
        - Token/API: gestionado por cabecera `Authorization: Bearer <token>`.
        - Si no hay facturas pendientes, el número se calcula como el mayor `Factura No.` + 1, con 8 dígitos.
        - Envío a DGI vía backend: `/enviar-factura` y `/descargar-pdf`.
        - Zona horaria/CAFE: fija 09:00 -05:00 (ajuste si es necesario).
        """
    )







