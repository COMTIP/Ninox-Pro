import streamlit as st
import requests
from datetime import datetime
import os

st.set_page_config(page_title="Factura Electrónica y Descarga PDF", layout="centered")
st.title("Factura Electrónica y Descarga PDF")

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

# ========== DATOS MOCK PARA DEMO ==========
clientes_demo = [
    {"nombre": "Clínica San Juan", "ruc": "212934-1-397239", "dv": "05", "direccion": "Calle 50, Panamá", "telefono": "61234567", "correo": "info@sanjuan.com"},
    {"nombre": "Empresa XYZ", "ruc": "180123-1-456789", "dv": "23", "direccion": "Avenida Central", "telefono": "67890123", "correo": "xyz@empresa.com"}
]
productos_demo = [
    {"codigo": "P001", "descripcion": "Implante Dental", "precio_unitario": 200.00, "itbms": 14.00},
    {"codigo": "P002", "descripcion": "Corona Cerámica", "precio_unitario": 120.00, "itbms": 8.40},
    {"codigo": "P003", "descripcion": "Prótesis Parcial", "precio_unitario": 80.00, "itbms": 5.60}
]

# ========== SELECCIÓN DE CLIENTE ==========
st.header("Datos del Cliente")
nombres_clientes = [c["nombre"] for c in clientes_demo]
cliente_idx = st.selectbox("Seleccione Cliente", range(len(nombres_clientes)), format_func=lambda x: nombres_clientes[x])
cliente = clientes_demo[cliente_idx]

col1, col2 = st.columns(2)
with col1:
    st.text_input("RUC", value=cliente["ruc"], disabled=True)
    st.text_input("DV", value=cliente["dv"], disabled=True)
    st.text_area("Dirección", value=cliente["direccion"], disabled=True)
with col2:
    st.text_input("Teléfono", value=cliente["telefono"], disabled=True)
    st.text_input("Correo", value=cliente["correo"], disabled=True)

# ========== AGREGAR PRODUCTOS ==========
st.header("Agregar Productos a la Factura")
if 'items' not in st.session_state:
    st.session_state['items'] = []
nombres_productos = [f"{p['codigo']} | {p['descripcion']}" for p in productos_demo]
prod_idx = st.selectbox("Producto", range(len(nombres_productos)), format_func=lambda x: nombres_productos[x])
prod_elegido = productos_demo[prod_idx]
cantidad = st.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
if st.button("Agregar ítem"):
    st.session_state['items'].append({
        "codigo": prod_elegido["codigo"],
        "descripcion": prod_elegido["descripcion"],
        "cantidad": cantidad,
        "precioUnitario": float(prod_elegido["precio_unitario"]),
        "valorITBMS": float(prod_elegido["itbms"]) * cantidad
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
fecha_emision = st.date_input("Fecha Emisión", value=datetime.today())
emisor = st.text_input("Nombre de quien emite la factura (obligatorio)", value=st.session_state.get("emisor", ""))

# ========== ENVIAR FACTURA ==========
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
                    "numeroDocumentoFiscal": "00000001",  # Usa correlativo real en integración
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
                        "numeroRUC": cliente['ruc'].replace("-", ""),
                        "digitoVerificadorRUC": cliente['dv'],
                        "razonSocial": cliente['nombre'],
                        "direccion": cliente['direccion'],
                        "telefono1": cliente['telefono'],
                        "correoElectronico1": cliente['correo'],
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
        url = "https://ninox-factory-server.onrender.com/enviar-factura"
        try:
            response = requests.post(url, json=payload)
            st.success(f"Respuesta: {response.text}")
            st.session_state['items'] = []
        except Exception as e:
            st.error(f"Error: {str(e)}")

# ========== DESCARGAR PDF ==========
st.markdown("---")
st.header("Descargar PDF de la Factura Electrónica")

factura_para_pdf = st.text_input("Factura No. para PDF")

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
    if not factura_para_pdf or not factura_para_pdf.strip():
        st.warning("Debe ingresar el número de factura para descargar el PDF.")
    else:
        url = "https://ninox-factory-server.onrender.com/descargar-pdf"
        try:
            response = requests.post(url, json=payload_pdf, stream=True)
            if response.ok and response.headers.get("content-type") == "application/pdf":
                file_path = f"Factura_{factura_para_pdf}.pdf"
                with open(file_path, "wb") as f:
                    f.write(response.content)
                with open(file_path, "rb") as f:
                    st.download_button(
                        label="Descargar PDF",
                        data=f,
                        file_name=file_path,
                        mime="application/pdf"
                    )
                st.success("PDF descargado correctamente.")
                os.remove(file_path)
            else:
                st.error("No se pudo descargar el PDF.")
                try:
                    error_data = response.json()
                    st.write(error_data)
                    if "detalle_respuesta" in error_data:
                        detalle = error_data["detalle_respuesta"]
                        st.error(f"Detalle del servicio: {detalle}")
                except Exception:
                    st.write(response.text)
        except Exception as e:
            st.error(f"Error de conexión: {str(e)}")
