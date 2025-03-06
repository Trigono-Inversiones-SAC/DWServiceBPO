import threading
import time
import serial
import serial.tools.list_ports
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173",
    "https://inventarios-dev.bluepacificoils.com",
    "https://inventarios.bluepacificoils.com"
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ------------------------------------------------------------------
# 1) FUNCIÓN PARA TRANSFORMAR LA TRAMA (sin cambios)
# ------------------------------------------------------------------
def transformar_trama(trama):
    """
    Resta 0x80 a cada caracter cuyo código sea >= 0x80.
    Esto convierte, por ejemplo, 0x82 en 0x02 y 0x8D en 0x0D.
    """
    nueva = ""
    for c in trama:
        if ord(c) >= 0x80:
            nueva += chr(ord(c) - 0x80)
        else:
            nueva += c
    return nueva


# ------------------------------------------------------------------
# 2) CLASE PRINCIPAL (Simula la BalanzaApp de Tkinter,
#    pero sin la interfaz gráfica).
# ------------------------------------------------------------------
class BalanzaApp:
    def __init__(self):
        # Variable para acumular la trama recibida
        self.cPeso = ""

        # ---------------------------
        # CONFIGURACIÓN SERIAL
        # ---------------------------
        self.oComm = serial.Serial()
        self.oComm.port = "COM4"  # Conexión fija al COM4
        self.oComm.baudrate = 9600
        self.oComm.parity = serial.PARITY_NONE
        self.oComm.bytesize = serial.EIGHTBITS
        self.oComm.stopbits = serial.STOPBITS_ONE
        self.oComm.timeout = 0  # Lectura no bloqueante

        # Almacenamos los valores que antes iban en "Entry" de Tkinter
        self.txtPeso = "----"
        self.txtTrama = ""

        # Intervalo del "timer" en milisegundos (en Tkinter era 250 ms).
        # Aquí lo convertimos a segundos (0.25) para el hilo.
        self.timer_interval = 0.25
        self.timer_active = False

        # Hilo de lectura en segundo plano
        self._thread = None

    def get_serial_ports(self):
        """
        Devuelve una lista de puertos seriales disponibles en el sistema.
        (En el original se usaba para llenar el Combobox)
        """
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def toggle_connection(self):
        """
        Abre o cierra el puerto serial y activa/desactiva el hilo de lectura.
        Emula la lógica original del botón INICIAR/DETENER.
        """
        if not self.timer_active:
            # Emula la acción "INICIAR":
            try:
                # Abrimos el puerto
                print(f"[DEBUG] Abriendo puerto: {self.oComm.port}")
                self.oComm.open()

                # Activamos la bandera y lanzamos el hilo
                self.timer_active = True
                self._thread = threading.Thread(target=self.oTimer_Tick, daemon=True)
                self._thread.start()

                print("[DEBUG] Puerto abierto y Timer iniciado.")
            except Exception as e:
                print(f"[ERROR] No se pudo abrir el puerto: {e}")
                raise e
        else:
            # Emula la acción "DETENER":
            try:
                print("[DEBUG] Deteniendo lectura y cerrando puerto.")
                self.timer_active = False

                # Esperamos a que el hilo termine su ciclo
                if self._thread is not None:
                    self._thread.join(timeout=1.0)

                if self.oComm.is_open:
                    self.oComm.close()
                    print("[DEBUG] Puerto cerrado correctamente.")

                # Restablecemos el campo de peso y la trama
                self.txtPeso = "0"
                self.cPeso = ""
                print("[DEBUG] Lectura detenida.")
            except Exception as e:
                print(f"[ERROR] No se pudo cerrar el puerto: {e}")
                raise e

    def oTimer_Tick(self):
        """
        Función que imita el 'after()' de Tkinter: se ejecuta mientras
        'self.timer_active' sea True, cada 250 ms (0.25 seg).
        Acumula bytes en self.cPeso y, cuando supera cierto largo, procesa la trama.
        """
        while self.timer_active:
            try:
                if self.oComm.is_open:
                    in_waiting = self.oComm.in_waiting
                    if in_waiting > 0:
                        # Lee todos los bytes disponibles
                        data = self.oComm.read(in_waiting)
                        chunk = data.decode('latin-1', errors='ignore')
                        self.cPeso += chunk
                        print(f"[DEBUG] Datos recibidos: {chunk}")

                    # Si se acumula una trama suficientemente larga (>= 30 caracteres)
                    if len(self.cPeso) >= 30:
                        print(f"[DEBUG] Trama completa (>=30 chars): {self.cPeso}")
                        # Transforma la trama
                        trama_corregida = transformar_trama(self.cPeso)
                        print(f"[DEBUG] Trama corregida: {trama_corregida}")

                        self.txtTrama = trama_corregida

                        # Buscamos el carácter de inicio (STX, \x02)
                        pos = trama_corregida.find('\x02')
                        if pos != -1:
                            # sumamos 4 para llegar al inicio del peso
                            start_idx = pos + 4
                            # Extraemos 6 caracteres
                            weight = trama_corregida[start_idx:start_idx+6]
                            print(f"[DEBUG] Peso extraído: {weight}")
                            self.txtPeso = weight
                        else:
                            print("[DEBUG] No se encontró el carácter STX en la trama corregida.")
                            self.txtPeso = "----"

                        # Reiniciamos la acumulación para la siguiente trama
                        self.cPeso = ""
                    else:
                        # Si no hay datos acumulados, muestra '----'
                        if len(self.cPeso) == 0:
                            self.txtPeso = "----"
            except Exception as e:
                print(f"[ERROR] Error de lectura: {e}")
                # Detenemos todo si ocurre un error
                self.timer_active = False
                try:
                    if self.oComm.is_open:
                        self.oComm.close()
                except:
                    pass

            # Espera antes de la siguiente iteración
            time.sleep(self.timer_interval)


# ------------------------------------------------------------------
# 3) INSTANCIA GLOBAL DE BalanzaApp
# ------------------------------------------------------------------
balanza = BalanzaApp()

# ------------------------------------------------------------------
# 4) ENDPOINTS EN FASTAPI
# ------------------------------------------------------------------

@app.get("/weight/")
def home():
    """
    Endpoint simple que devuelve el estado actual:
    - Peso leído (txtPeso)
    - Última trama recibida (txtTrama)
    - Si está activo el 'timer' (timer_active)
    """
    fecha_y_hora = time.strftime("%Y-%m-%d %H:%M:%S")
    
    return {
        "peso": balanza.txtPeso,
        "trama": balanza.txtTrama,
        "timer_active": balanza.timer_active,
        'fecha_and_time': fecha_y_hora
    }


@app.post("/iniciar")
def iniciar_lectura():
    """
    Llama al toggle_connection() solo si no está activo.
    Equivale al botón "Iniciar" en el GUI original.
    """
    if not balanza.timer_active:
        balanza.toggle_connection()
        return {"message": "Lectura iniciada en COM4."}
    else:
        return {"message": "La lectura ya está activa."}


@app.post("/detener")
def detener_lectura():
    """
    Llama al toggle_connection() solo si está activo.
    Equivale al botón "Detener" en el GUI original.
    """
    if balanza.timer_active:
        balanza.toggle_connection()
        return {"message": "Lectura detenida."}
    else:
        return {"message": "La lectura ya está detenida."}


@app.get("/puertos")
def listar_puertos():
    """
    (Opcional) Retorna la lista de puertos disponibles, 
    aunque en este ejemplo la app está fijada a COM4.
    """
    return balanza.get_serial_ports()
