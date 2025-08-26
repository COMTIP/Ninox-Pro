import streamlit as st
import requests
from datetime import datetime

# ========== LOGIN ==========
USUARIOS = {
    "Mispanama": "Maxilo2000",
    "usuario1": "password123"
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

# ========== NINOX API CONFIG ==========
API_TOKEN = "0b3a1130-785a-11f0-ace0-3fb1fcb242e2"
TEAM_ID = "ihp8o8AaLzfodwc4J"
DATABASE_ID = "u2g01uaua8tu"

def obtener_clientes():
    url = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}/tables/Clientes/records"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.ok:
        return r.json()
    return []

def obtener_productos():
    url = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}/tables/Productos/records"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.ok:
        return r.json()
    return []

def obtener_facturas():
    url = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}/tables/Facturas/records"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.ok:
        return r.json()
    return []

def calcular_siguiente_factura_no(facturas):
    max_factura = 0
    for f in facturas:
        valor = f["fields"].get("Factura No.", "")
        try:
            n = int(valor)
            if n > max_factura:
                max_factura = n
        except Exception:
            continue
    return f"{max_factura + 1:08d}"

# ========== CARGA DE DATOS ==========
if st.button("Actualizar datos de Ninox"):
    st.session_state.pop("clientes", None)
    st.session_state.pop("productos", None)
    st.session_state.pop("facturas", None)

if "clientes" not in st.session_state:
    st.session_state["clientes"] = obtener_clientes()
if "productos" not in st.session_state:
    st.session_state["productos"] = obtener_productos()
if "facturas" not in st.session_state:
    st.session_state["facturas"] = obtener_facturas()

clientes = st.session_state["clientes"]
productos = st.session_state["productos"]
facturas = st.session_state["facturas"]

if not clientes:
    st.warning("No hay clientes en Ninox")
    st.stop()
if not productos:
    st.warning("No hay productos en Ninox")
    st.stop()

# ========== SELECCIÓN DE CLIENTE ==========
st.header("Datos del Cliente")
nombres_clientes = [c['fields']['Nombre'] for c in clientes]
cliente_idx = st.selectbox("Seleccione Cliente", range(len(nombres_clientes)), format_func=lambda x: nombres_clientes[x])
cliente = clientes[cliente_idx]["fields"]

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC", value=cliente.get('RUC', ''), disabled=True)
    st.text_input("DV", value=cliente.get('DV', ''), disabled=True)
    st.text_area("Dirección", value=cliente.get('Dirección', ''), disabled=True)
with col2:
    st.text_input("Teléfono", value=cliente.get('Teléfono', ''), disabled=True)
    st.text_input("Correo", value=cliente.get('Correo', ''), disabled=True)

# ========== FACTURAS ==========
facturas_pendientes = [
    f for f in facturas
    if f["fields"].get("Estado", "").strip().lower() == "pendiente"
]
if facturas_pendientes:
    opciones_facturas = [f['fields'].get("Factura No.", "") for f in facturas_pendientes]
    idx_factura = st.selectbox("Seleccione Factura Pendiente", range(len(opciones_facturas)), format_func=lambda x: opciones_facturas[x])
    factura_no_preview = opciones_facturas[idx_factura]
else:
    factura_no_preview = calcular_siguiente_factura_no(facturas)
st.text_input("Factura No.", value=factura_no_preview, disabled=True)
fecha_emision = st.date_input("Fecha Emisión", value=datetime.today())

# ========== AGREGAR PRODUCTOS ==========
st.header("Agregar Productos a la Factura")
if 'items' not in st.session_state:
    st.session_state['items'] = []
nombres_productos = [f"{p['fields'].get('Código','')} | {p['fields'].get('Descripción','')}" for p in productos]
prod_idx = st.selectbox("Producto", range(len(nombres_productos)), format_func=lambda x: nombres_productos[x])
prod_elegido = productos[prod_idx]['fields']
cantidad = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
if st.button("Agregar ítem"):
    st.session_state['items'].append({
        "codigo": prod_elegido.get('Código', ''),
        "descripcion": prod_elegido.get('Descripción', ''),
        "cantidad": cantidad,
        "precioUnitario": float(prod_elegido.get('Precio Unitario', 0)),
        "valorITBMS": float(prod_elegido.get('ITBMS', 0)) * cantidad
    })
if st.session_state['items']:
    st.write("#### Ítems de la factura")
    for idx, i in enumerate(st.session_state['items']):
        st.write(f"{idx+1}. {i['codigo']} | {i['descripcion']} | {i['cantidad']} | {i['precioUnitario']} | {i['valorITBMS']}")
    if st.button("Limpiar Ítems"):
        st.session_state['items'] = []

total_neto = sum(i["cantidad"] * i["precioUnitario"] for i in st.session_state['items'])
total_itbms = sum(i["valorITBMS"] for i in st.session_state['items'])
total_factura = total_neto + total_itbms

st.write(f"**Total Neto:** {total_neto:.2f}   **ITBMS:** {total_itbms:.2f}   **Total a Pagar:** {total_factura:.2f}")

medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Débito", "Crédito"])
emisor = st.text_input("Nombre de quien emite la factura (obligatorio)", value=st.session_state.get("emisor", ""))

# ========== ENVIAR Y DESCARGAR PDF ==========
def obtener_facturas_actualizadas():
    url = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}/tables/Facturas/records"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.ok:
        return r.json()
    return []

BACKEND_URL = "https://ninox-factory-server.onrender.com"

if "pdf_bytes" not in st.session_state:
    st.session_state["pdf_bytes"] = None
    st.session_state["pdf_name"] = None

if st.button("Enviar Factura a DGI"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite la factura antes de enviarla.")
    elif not st.session_state['items']:
        st.error("Debe agregar al menos un producto.")
    else:
        forma_pago = {
            "formaPagoFact": {"Efectivo": "01", "Débito": "02", "Crédito": "03"}[medio_pago],
            "valorCuotaPagada": f"{total_factura:.2f}"
        }
        payload = {
            "documento": {
                "codigoSucursalEmisor": "0000",
                "tipoSucursal": "1",
                "datosTransaccion": {
                    "tipoEmision": "01",
                    "tipoDocumento": "01",
                    "numeroDocumentoFiscal": factura_no_preview,
                    "puntoFacturacionFiscal": "001",
                    "naturalezaOperacion": "01",
                    "tipoOperacion": 1,
                    "destinoOperacion": 1,
                    "formatoCAFE": 1,
                    "entregaCAFE": 1,
                    "envioContenedor": 1,
                    "procesoGeneracion": 1,
                    "tipoVenta": 1,
                    "fechaEmision": str(fecha_emision) + "T09:00:00-05:00",
                    "cliente": {
                        "tipoClienteFE": "02",
                        "tipoContribuyente": 1,
                        "numeroRUC": cliente.get('RUC', '').replace("-", ""),
                        "digitoVerificadorRUC": cliente.get('DV', ''),
                        "razonSocial": cliente.get('Nombre', ''),
                        "direccion": cliente.get('Dirección', ''),
                        "telefono1": cliente.get('Teléfono', ''),
                        "correoElectronico1": cliente.get('Correo', ''),
                        "pais": "PA"
                    }
                },
                "listaItems": {
                    "item": [
                        {
                            "codigo": i["codigo"],
                            "descripcion": i["descripcion"],
                            "codigoGTIN": "0",
                            "cantidad": f"{i['cantidad']:.2f}",
                            "precioUnitario": f"{i['precioUnitario']:.2f}",
                            "precioUnitarioDescuento": "0.00",
                            "precioItem": f"{i['cantidad'] * i['precioUnitario']:.2f}",
                            "valorTotal": f"{i['cantidad'] * i['precioUnitario'] + i['valorITBMS']:.2f}",
                            "cantGTINCom": f"{i['cantidad']:.2f}",
                            "codigoGTINInv": "0",
                            "tasaITBMS": "01" if i["valorITBMS"] > 0 else "00",
                            "valorITBMS": f"{i['valorITBMS']:.2f}",
                            "cantGTINComInv": f"{i['cantidad']:.2f}"
                        } for i in st.session_state['items']
                    ]
                },
                "totalesSubTotales": {
                    "totalPrecioNeto": f"{total_neto:.2f}",
                    "totalITBMS": f"{total_itbms:.2f}",
                    "totalMontoGravado": f"{total_itbms:.2f}",
                    "totalDescuento": "0.00",
                    "totalAcarreoCobrado": "0.00",
                    "valorSeguroCobrado": "0.00",
                    "totalFactura": f"{total_factura:.2f}",
                    "totalValorRecibido": f"{total_factura:.2f}",
                    "vuelto": "0.00",
                    "tiempoPago": "1",
                    "nroItems": str(len(st.session_state['items'])),
                    "totalTodosItems": f"{total_factura:.2f}",
                    "listaFormaPago": {
                        "formaPago": [forma_pago]
                    }
                }
            }
        }
        url = BACKEND_URL + "/enviar-factura"
        try:
            response = requests.post(url, json=payload)
            if response.ok:
                st.success(f"Factura enviada correctamente. Generando PDF…")
                st.session_state['items'] = []
                st.session_state["facturas"] = obtener_facturas_actualizadas()
                st.session_state["ultima_factura_no"] = factura_no_preview

                # Intentar descargar el PDF automáticamente
                pdf_payload = {
                    "codigoSucursalEmisor": "0000",
                    "numeroDocumentoFiscal": factura_no_preview,
                    "puntoFacturacionFiscal": "001",
                    "tipoDocumento": "01",
                    "tipoEmision": "01",
                    "serialDispositivo": ""
                }
                pdf_url = BACKEND_URL + "/descargar-pdf"
                pdf_response = requests.post(pdf_url, json=pdf_payload, stream=True)
                if pdf_response.ok and pdf_response.headers.get("content-type") == "application/pdf":
                    st.session_state["pdf_bytes"] = pdf_response.content
                    st.session_state["pdf_name"] = f"Factura_{factura_no_preview}.pdf"
                    st.success("¡PDF generado y listo para descargar abajo!")
                else:
                    st.session_state["pdf_bytes"] = None
                    st.session_state["pdf_name"] = None
                    st.error("Factura enviada, pero no se pudo generar el PDF automáticamente.")
                    try:
                        st.write(pdf_response.json())
                    except Exception:
                        st.write(pdf_response.text)
            else:
                st.error("Error al enviar la factura.")
                try:
                    st.write(response.json())
                except Exception:
                    st.write(response.text)
        except Exception as e:
            st.error(f"Error: {str(e)}")

# ========== BOTÓN DE DESCARGA PDF ==========
if st.session_state.get("pdf_bytes") and st.session_state.get("pdf_name"):
    st.markdown("---")
    st.header("Descargar PDF de la Factura Electrónica")
    st.download_button(
        label="Descargar PDF",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state["pdf_name"],
        mime="application/pdf"
    )










