import re
from tabulate import tabulate

# Protocolo estándar de comandos ESC/POS a bajo nivel
ESC = b"\x1b"
GS = b"\x1d"

CMD_INIT_PRINTER = ESC + b"\x40"      # ESC @ : Inicializar impresora
CMD_CUT_PAPER    = GS  + b"\x56\x00"  # GS V 0 : Corte total de papel
CMD_ALIGN_CENTER = ESC + b"\x61\x01"  # ESC a 1 : Alinear al centro
CMD_ALIGN_LEFT   = ESC + b"\x61\x00"  # ESC a 0 : Alinear a la izquierda
CMD_BOLD_ON      = ESC + b"\x45\x01"  # ESC E 1 : Negrita activada
CMD_BOLD_OFF     = ESC + b"\x45\x00"  # ESC E 0 : Negrita desactivada

_VIDPID_RE = re.compile(r"VID_([0-9A-Fa-f]{4}).*PID_([0-9A-Fa-f]{4})")

def generar_payload_boleta_escpos(nombre_empresa: str, sucursal: str, venta_id: int, cajero: str, lineas: list, total: float) -> bytes:
    """
    Construye el stream binario directo en formato ESC/POS para impresión térmica
    sin depender de controladores propietarios ni diálogos de usuario del sistema operativo.
    """
    # 1. Cabecera con formato
    stream = bytearray()
    stream.extend(CMD_INIT_PRINTER)
    stream.extend(CMD_ALIGN_CENTER)
    stream.extend(CMD_BOLD_ON)
    stream.extend(f"*** {nombre_empresa.upper()} ***\n".encode("cp437", errors="replace"))
    stream.extend(CMD_BOLD_OFF)
    stream.extend(f"Sucursal: {sucursal}\n".encode("cp437", errors="replace"))
    stream.extend(f"Boleta ID: {venta_id} | Cajero: {cajero}\n".encode("cp437", errors="replace"))
    stream.extend(b"------------------------------------------\n")

    # 2. Tabla formateada de productos a ancho fijo
    stream.extend(CMD_ALIGN_LEFT)
    headers = ["Cant", "Producto", "Total"]
    tabla_texto = tabulate(
        lineas,
        headers=headers,
        tablefmt="plain",
        maxcolwidths=[4, 24, 10],
        colalign=("left", "left", "right")
    )
    stream.extend(tabla_texto.encode("cp437", errors="replace"))
    stream.extend(b"\n------------------------------------------\n")

    # 3. Total y Cierre
    stream.extend(CMD_BOLD_ON)
    stream.extend(f"TOTAL: ${total:,.0f} CLP\n\n".encode("cp437", errors="replace"))
    stream.extend(CMD_BOLD_OFF)
    stream.extend(CMD_ALIGN_CENTER)
    stream.extend(b"Gracias por su compra!\n\n\n")

    # 4. Corte de papel
    stream.extend(CMD_CUT_PAPER)
    return bytes(stream)

def enviar_a_spooler_windows(printer_name: str, payload_bytes: bytes):
    """
    Envía los bytes ESC/POS en modo RAW directo al spooler de impresión de Windows (win32print).
    """
    try:
        import win32print
        h_printer = win32print.OpenPrinter(printer_name)
        try:
            job = win32print.StartDocPrinter(h_printer, 1, ("Boleta_Termica_POS", None, "RAW"))
            try:
                win32print.StartPagePrinter(h_printer)
                win32print.WritePrinter(h_printer, payload_bytes)
                win32print.EndPagePrinter(h_printer)
            finally:
                win32print.EndDocPrinter(h_printer)
        finally:
            win32print.ClosePrinter(h_printer)
        return True
    except ImportError:
        print("[Mock Mode] win32print no disponible en este entorno. Payload generado exitosamente.")
        return False

def detectar_impresoras_usb_wmi():
    """
    Detecta dinámicamente dispositivos de punto de venta (POS) conectados por USB
    consultando el subsistema WMI (Win32_PnPEntity) y parseando Vendor ID y Product ID (VID/PID).
    """
    dispositivos_encontrados = []
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        wmi = win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer(".", "root\\cimv2")
        usb_entities = wmi.ExecQuery("SELECT Name, PNPDeviceID FROM Win32_PnPEntity WHERE PNPDeviceID LIKE 'USB%'")
        
        for dev in usb_entities:
            pnp_id = str(dev.PNPDeviceID)
            match = _VIDPID_RE.search(pnp_id)
            if match:
                dispositivos_encontrados.append({
                    "nombre": dev.Name,
                    "vendor_id": f"0x{match.group(1)}",
                    "product_id": f"0x{match.group(2)}"
                })
    except Exception as e:
        print(f"Error consultando WMI: {e}")
    return dispositivos_encontrados
