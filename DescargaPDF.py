# Modulo que brinda funciones de SOAP
import zeep
# Link del WS
wsdl = 'https://demoemision.thefactoryhka.com.pa/ws/obj/v1.0/Service.svc?singleWsdl'
# Establecemos el cliente como el WS
cliente = zeep.Client(wsdl=wsdl)
# Declaramos el diccionario que pasa los datos de factura
datos = {
    "tokenEmpresa": "SOLICITAR",
    "tokenPassword": "SOLICITAR",
    "datosDocumento": {
        "codigoSucursalEmisor": "SUCURSAL",
        "numeroDocumentoFiscal": 0000,
        "puntoFacturacionFiscal": "001",
        "tipoDocumento": "01",
        "tipoEmision": "01",
        "serialDispositivo": "",
    }
}
# Declaramos el metodo a usar, recorremos el diccionario y lo enviamos
res = (cliente.service.DescargaPDF(**datos))
# Se imprime la respuesta a la solicitud del servicio
print(res)