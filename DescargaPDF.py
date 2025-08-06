import streamlit as st
import requests
from datetime import datetime
import pandas as pd

# ========== LOGIN OBLIGATORIO ==========
USUARIOS = {
    "Mispanama": "Maxilo2000",
    "usuario1": "password123"
}

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align:center; color:#1c6758'>Acceso a Facturación Electrónica</h2>", unsafe_allow_html=True)
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

# ======= NINOX API CONFIG ==========
API_TOKEN = "d3c82d50-60d4-11f0-9dd2-0154422825e5"
TEAM_ID = "6dA5DFvfDTxCQxpDF"
DATABASE_ID = "yoq1qy9euurq"

def obtener_clientes():
    url = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}/tables/Clientes/records"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.get(url, headers=headers)
    return r.json() if r.ok else []

def obtener_facturas():
    url = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}/tables/Facturas/records"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.get(url, headers=headers)
    return r.json() if r.ok else []

def obtener_lineas_factura():
    url = f"https://api.ninox.com/v1/teams/{TEAM_ID}/databases/{DATABASE_ID}/tables/LineasFactura/records"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.get(url, headers=headers)
    return r.json() if r.ok else []

# ================== FACTURACIÓN ======================
st.set_page_config(page_title="Factura Electrónica Ninox + DGI", layout="centered")
st.title("Factura Electrónica")

if st.button("Actualizar datos de Ninox"):
    st.session_state.pop("clientes", None)
    st.session_state.pop("facturas", None)
    st.session_state.pop("lineas_factura", None)

if "clientes" not in st.session_state:
    st.session_state["clientes"] = obtener_clientes()
if "facturas" not in st.session_state:
    st.session_state["facturas"] = obtener_facturas()
if "lineas_factura" not in st.session_state:
    st.session_state["lineas_factura"] = obtener_lineas_factura()

clientes = st.session_state["clientes"]
facturas = st.session_state["facturas"]
lineas_factura = st.session_state["lineas_factura"]

# --- Selección de Cliente
nombres_clientes = [c['fields'].get('Nombre', f"Cliente {c['id']}") for c in clientes]
cliente_idx = st.selectbox("Seleccione Cliente", range(len(nombres_clientes)), format_func=lambda x: nombres_clientes[x])
cliente = clientes[cliente_idx]
cliente_id = cliente["id"]
cliente_fields = cliente["fields"]

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC", value=cliente_fields.get('RUC', ''), disabled=True)
    st.text_input("DV", value=cliente_fields.get('DV', ''), disabled=True)
    st.text_area("Dirección", value=cliente_fields.get('Dirección', ''), disabled=True)
with col2:
    st.text_input("Teléfono", value=cliente_fields.get('Teléfono', ''), disabled=True)
    st.text_input("Correo", value=cliente_fields.get('Correo', ''), disabled=True)

# --- Filtrar facturas pendientes de este cliente
facturas_cliente = [
    f for f in facturas
    if f["fields"].get("Estado", "") == "Pendiente"
    and str(f["fields"].get("Cliente", "")) == str(cliente_id)
]

if not facturas_cliente:
    st.info("Este cliente no tiene facturas pendientes.")
    st.stop()

factura_nos = [f["fields"].get("Factura No.", f["id"]) for f in facturas_cliente]
factura_idx = st.selectbox("Seleccione Factura No. pendiente", range(len(factura_nos)), format_func=lambda x: factura_nos[x])
factura_seleccionada = facturas_cliente[factura_idx]
factura_no = factura_seleccionada["fields"].get("Factura No.", factura_seleccionada["id"])

# --- Buscar y mostrar líneas de la factura seleccionada
lineas = [
    l for l in lineas_factura
    if str(l["fields"].get("Factura No.", "")) == str(factura_no)
]

if not lineas:
    st.warning("No hay productos asociados a esta factura.")
    st.stop()

st.markdown("### Productos en la factura")
total_neto = 0
total_itbms = 0
total_factura = 0

# Mostrar tabla de productos
data_items = []
for l in lineas:
    flds = l["fields"]
    cantidad = float(flds.get("Cantidad", 0))
    precio = float(str(flds.get("Precio Unitario", "0")).replace("$",""))
    itbms = float(flds.get("ITBMS", 0))
    subtotal = cantidad * precio
    total_neto += subtotal
    total_itbms += itbms
    total = subtotal + itbms
    total_factura += total
    data_items.append({
        "Código": flds.get("Código", ""),
        "Descripción": flds.get("Descripción", ""),
        "Cantidad": cantidad,
        "Precio Unitario": precio,
        "ITBMS": itbms,
        "Subtotal Línea": subtotal
    })

df = pd.DataFrame(data_items)
st.dataframe(df, use_container_width=True)

st.write(f"**Total Neto:** {total_neto:.2f}   **ITBMS:** {total_itbms:.2f}   **Total a Pagar:** {total_factura:.2f}")

# Selección de medio de pago y emisor
medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Débito", "Crédito"])
emisor = st.text_input("Nombre de quien emite la factura (obligatorio)")

# --- Enviar a DGI
if st.button("Enviar Factura a DGI"):
    if not emisor.strip():
        st.error("Debe ingresar el nombre de quien emite la factura antes de enviarla.")
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
                    "numeroDocumentoFiscal": factura_no,
                    "puntoFacturacionFiscal": "001",
                    "naturalezaOperacion": "01",
                    "tipoOperacion": 1,
                    "destinoOperacion": 1,
                    "formatoCAFE": 1,
                    "entregaCAFE": 1,
                    "envioContenedor": 1,
                    "procesoGeneracion": 1,
                    "tipoVenta": 1,
                    "fechaEmision": str(datetime.today().date()) + "T09:00:00-05:00",
                    "cliente": {
                        "tipoClienteFE": "02",
                        "tipoContribuyente": 1,
                        "numeroRUC": cliente_fields.get('RUC', '').replace("-", ""),
                        "digitoVerificadorRUC": cliente_fields.get('DV', ''),
                        "razonSocial": cliente_fields.get('Nombre', ''),
                        "direccion": cliente_fields.get('Dirección', ''),
                        "telefono1": cliente_fields.get('Teléfono', ''),
                        "correoElectronico1": cliente_fields.get('Correo', ''),
                        "pais": "PA"
                    }
                },
                "listaItems": {
                    "item": [
                        {
                            "codigo": i["Código"],
                            "descripcion": i["Descripción"],
                            "codigoGTIN": "0",
                            "cantidad": f"{i['Cantidad']:.2f}",
                            "precioUnitario": f"{i['Precio Unitario']:.2f}",
                            "precioUnitarioDescuento": "0.00",
                            "precioItem": f"{i['Subtotal Línea']:.2f}",
                            "valorTotal": f"{i['Subtotal Línea']+i['ITBMS']:.2f}",
                            "cantGTINCom": f"{i['Cantidad']:.2f}",
                            "codigoGTINInv": "0",
                            "tasaITBMS": "01" if i["ITBMS"] > 0 else "00",
                            "valorITBMS": f"{i['ITBMS']:.2f}",
                            "cantGTINComInv": f"{i['Cantidad']:.2f}"
                        } for i in data_items
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
                    "nroItems": str(len(data_items)),
                    "totalTodosItems": f"{total_factura:.2f}",
                    "listaFormaPago": {
                        "formaPago": [forma_pago]
                    }
                }
            }
        }
        st.write("JSON enviado:")
        st.json(payload)

        url = "https://ninox-factory-server.onrender.com/enviar-factura"
        try:
            response = requests.post(url, json=payload)
            st.success(f"Respuesta: {response.text}")
            st.session_state['items'] = []
            st.session_state["facturas"] = obtener_facturas_actualizadas()
            # Guardar el número de factura para descargar el PDF
            st.session_state["last_factura_no"] = factura_no_final
        except Exception as e:
            st.error(f"Error: {str(e)}")

# ========== DESCARGAR PDF ==========
st.markdown("---")
st.header("Descargar PDF de la Factura Electrónica")

# Usa el número de factura emitido, si existe
factura_para_pdf = st.session_state.get("last_factura_no", factura_no_preview)
st.text_input("Factura No. para PDF", value=factura_para_pdf, disabled=True)

payload_pdf = {
    "documento": {
        "codigoSucursalEmisor": "0000",
        "numeroDocumentoFiscal": factura_para_pdf,
        "puntoFacturacionFiscal": "001",
        "tipoDocumento": "01",
        "tipoEmision": "01",
        "serialDispositivo": ""
    }
}

if st.button("Descargar PDF de esta factura"):
    url = "https://ninox-factory-server.onrender.com/descargar-pdf"
    response = requests.post(url, json=payload_pdf, stream=True)
    if response.ok and response.headers.get("content-type") == "application/pdf":
        # Guarda y muestra el PDF con botón de descarga
        with open("factura_dgi_descargada.pdf", "wb") as f:
            f.write(response.content)
        with open("factura_dgi_descargada.pdf", "rb") as f:
            st.download_button(
                label="Descargar PDF",
                data=f,
                file_name=f"Factura_{factura_para_pdf}.pdf",
                mime="application/pdf"
            )
        st.success("PDF descargado correctamente.")
    else:
        try:
            st.error(response.json().get("error", "No se pudo descargar el PDF."))
        except Exception:
            st.error("No se pudo descargar el PDF.")

