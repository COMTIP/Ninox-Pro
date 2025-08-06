import streamlit as st
import requests
import os

# ... (Resto de tu código arriba, como login, carga de clientes, productos, etc.)

# ========== DESCARGAR PDF DE LA FACTURA ==========
st.markdown("---")
st.header("Descargar PDF de la Factura Electrónica")

factura_para_pdf = factura_no_preview

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
                st.write(error_data)  # Muestra toda la respuesta
                # Si el backend trajo el detalle, lo mostramos más amigable
                if "detalle_respuesta" in error_data:
                    detalle = error_data["detalle_respuesta"]
                    st.error(f"Detalle del servicio: {detalle}")
            except Exception:
                st.write(response.text)
    except Exception as e:
        st.error(f"Error de conexión: {str(e)}")




