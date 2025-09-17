import streamlit as st
import requests
import re
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
API_TOKEN   = "03035f50-93e2-11f0-883e-db77626d62e5"
TEAM_ID     = "fhmgaLpFghyh5sNHh"
DATABASE_ID = "er0sibgl3dug"

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

def obtener_lineas_factura() -> List[Dict[str, Any]]:
    # Ajusta si tu tabla se llama distinto
    return _ninox_get("/tables/Lineas%20Factura/records")

def calcular_siguiente_factura_no(facts: List[Dict[str, Any]]) -> str:
    max_factura = 0
    for f in facts:
        valor = (f.get("fields", {}) or {}).get("Factura No.", "")
        try:
            n = int(str(valor).strip() or 0)
            if n > max_factura:
                max_factura = n
        except Exception:
            continue
    return f"{max_factura + 1:08d}"

# Normalizador robusto: extrae solo dígitos y completa a 8
def _norm_num_any(x: Any, width: int = 8) -> str:
    s = str(x) if x is not None else ""
    digits = re.sub(r"\D", "", s)
    if digits == "":
        return ""
    return digits.zfill(width)

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

# Índice por código de producto (para hallar ITBMS si falta en la línea)
productos_por_codigo: Dict[str, Dict[str, Any]] = {}
for p in productos:
    f = p.get("fields", {}) or {}
    productos_por_codigo[str(f.get("Código", "")).strip()] = f

# ==========================
# STATE
# ==========================
if "line_items" not in st.session_state:
    st.session_state["line_items"] = []
if "debug_info" not in st.session_state:
    st.session_state["debug_info"] = {}

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
# FUNC: Cargar líneas desde Lineas Factura
# ==========================
def cargar_lineas_factura(factura_id: str, factura_no_norm: str) -> list[dict]:
    """
    Busca líneas que pertenezcan a la factura:
      1) por relación al ID de la factura (campo string o lista)
      2) respaldo por cualquier campo cuyo nombre contenga 'factura' y cuyo valor normalizado coincida
    """
    vistos_ids = set()
    lineas_encontradas: list[Dict[str, Any]] = []

    for lf in lineas_factura:
        fields = lf.get("fields", {}) or {}
        match = False

        # 1) Relación por ID (string o lista que contenga el id)
        for v in fields.values():
            if isinstance(v, str) and v == factura_id:
                match = True; break
            if isinstance(v, list) and factura_id in v:
                match = True; break

        # 2) Respaldo: por numero en cualquier campo con 'factura' en el nombre
        if not match:
            for k, v in fields.items():
                k_norm = str(k).lower().replace("\xa0", " ")  # quita NBSP
                if "factura" in k_norm:
                    if _norm_num_any(v) == factura_no_norm:
                        match = True
                        break

        if match and lf.get("id") not in vistos_ids:
            lineas_encontradas.append(fields)
            vistos_ids.add(lf.get("id"))

    # Mapear a items internos
    items = []
    for lf in lineas_encontradas:
        codigo = str(lf.get("Código", "")).strip()
        desc   = lf.get("Descripción", "") or lf.get("Descripcion", "") or ""
        try:    cant = float(lf.get("Cantidad", 0) or 0)
        except: cant = 0.0
        try:    pu   = float(lf.get("Precio Unitario", 0) or 0)
        except: pu   = 0.0

        # ITBMS: toma tasa de la línea si es numérica; si no, cae a Productos por código; si no, 0
        tasa = None
        if lf.get("ITBMS") is not None:
            try: tasa = float(lf["ITBMS"])
            except Exception: tasa = None
        if tasa is None:
            tasa = float((productos_por_codigo.get(codigo, {}) or {}).get("ITBMS", 0) or 0)

        valor_itbms = round((tasa or 0) * cant * pu, 2)
        items.append({
            "codigo":         codigo,
            "descripcion":    desc,
            "cantidad":       cant,
            "precioUnitario": pu,
            "tasa":           float(tasa or 0),
            "valorITBMS":     valor_itbms,
        })

    # Guardar debug
    st.session_state["debug_info"] = {
        "factura_id": factura_id,
        "factura_no_norm": factura_no_norm,
        "lineas_encontradas": len(lineas_encontradas),
        "ejemplo_linea": (lineas_encontradas[0] if lineas_encontradas else {}),
    }
    return items

# ==========================
# FACTURA EXISTENTE O NUEVA (carga desde Lineas Factura)
# ==========================
facturas_pendientes = [
    f for f in facturas
    if (f.get("fields", {}) or {}).get("Estado", "").strip().lower() == "pendiente"
]

if facturas_pendientes:
    opciones_facturas = [(f.get("fields", {}) or {}).get("Factura No.", "") for f in facturas_pendientes]
    idx_factura = st.selectbox("Seleccione Factura Pendiente", range(len(opciones_facturas)),
                               format_func=lambda x: str(opciones_facturas[x]))

    factura_sel        = facturas_pendientes[idx_factura]
    factura_id         = factura_sel.get("id")
    factura_no_raw     = (factura_sel.get("fields", {}) or {}).get("Factura No.", "")
    factura_no_preview = _norm_num_any(factura_no_raw)

    changed = st.session_state.get("factura_seleccionada") != factura_id
    if changed or st.button("Refrescar líneas"):
        st.session_state["factura_seleccionada"] = factura_id
        st.session_state["line_items"] = cargar_lineas_factura(factura_id, factura_no_preview)

else:
    factura_no_preview = calcular_siguiente_factura_no(facturas)
    st.info("No hay facturas pendientes. Este modo solo carga ítems desde 'Lineas Factura'.")

st.text_input("Factura No.", value=factura_no_preview, disabled=True)
fecha_emision = st.date_input("Fecha Emisión", value=date.today())

# ==========================
# ÍTEMS (SOLO LECTURA)
# ==========================
st.header("Ítems de la factura (desde 'Lineas Factura')")
if not st.session_state["line_items"]:
    st.warning("No se encontraron líneas para la factura seleccionada.")
else:
    for idx, i in enumerate(st.session_state["line_items"], start=1):
        st.write(f"{idx}. {i['codigo']} | {i['descripcion']} | Cant: {i['cantidad']:.2f} | P.U.: {i['precioUnitario']:.2f} | ITBMS calc.: {i['valorITBMS']:.2f}")

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
        st.error("Debe ingresar el nombre de quien emite la factura antes de enviarla."); st.stop()
    if not st.session_state["line_items"]:
        st.error("La factura no tiene líneas en 'Lineas Factura'."); st.stop()

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

    try:
        url_envio = f"{BACKEND_URL}/enviar-factura"
        r = requests.post(url_envio, json=payload, timeout=60)
        if r.ok:
            st.success("Factura enviada correctamente. Generando PDF…")
            st.session_state["line_items"] = []
            _ninox_refrescar_facturas()
            st.session_state["ultima_factura_no"] = str(factura_no_preview)

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
# DEPURACIÓN
# ==========================
with st.expander("Depuración (para diagnosticar empates)"):
    st.json(st.session_state.get("debug_info", {}))

# ==========================
# INFO / AYUDA
# ==========================
with st.expander("Ayuda / Referencias"):
    st.markdown(
        """
        - Ítems cargados **solo** desde `Lineas Factura`.
        - Coincidencia por **ID de factura** (relación) y respaldo por **número** en cualquier campo que contenga “factura”.
        - `_norm_num_any` extrae dígitos y normaliza a 8 caracteres (ej. 74 → 00000074).
        - Si tu campo `ITBMS` en la línea es **monto** (no tasa), avísame y lo sumo directo en lugar de calcular.
        """
    )
