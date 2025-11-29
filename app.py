from flask import Flask, render_template, request
import csv
import os
from datetime import datetime
# Librerías para Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
# La clave secreta es necesaria para la gestión de sesiones y mensajes
app.secret_key = 'clave_secreta_laizaydavid' 

# --- CONFIGURACIÓN DE ARCHIVOS ---
DB_CONFIRMADOS = 'invitados.csv'
DB_MAESTRA = 'lista_maestra.csv'

# --- CONFIGURACIÓN DE GOOGLE SHEETS (DEBES MODIFICAR ESTO) ---
# Nombre del archivo JSON que contiene la clave de la Cuenta de Servicio
GOOGLE_KEY_FILE = 'service_account_key.json' 
# Nombre de tu Hoja de Cálculo (el nombre que le diste en Google Drive)
SHEET_NAME = 'Lista de Invitados Boda Laiza y David'
# Nombre de la Pestaña dentro de la hoja (normalmente 'Hoja1' o 'Confirmados')
WORKSHEET_NAME = 'Confirmados' 

# --- FUNCIONES DE BASE DE DATOS LOCALES ---

def cargar_lista_maestra():
    """Carga el CSV de la lista maestra para la validación de boletos."""
    maestra = {}
    try:
        # El archivo lista_maestra.csv debe existir en la misma carpeta que app.py
        with open(DB_MAESTRA, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                nombre_limpio = row['Nombre'].strip()
                # La columna 'Asignados' debe tener números enteros
                maestra[nombre_limpio] = int(row['Asignados'].strip())
    except FileNotFoundError:
        print(f"ERROR: Archivo {DB_MAESTRA} no encontrado. Asegúrese de que esté en la raíz del proyecto.")
        return {} 
    except ValueError:
        print(f"ERROR: La columna 'Asignados' en {DB_MAESTRA} debe contener solo números enteros.")
        return {}
    return maestra

def init_db():
    """Inicializa el CSV de confirmados si no existe."""
    if not os.path.exists(DB_CONFIRMADOS):
        with open(DB_CONFIRMADOS, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Fecha', 'Nombre', 'Asistentes', 'Mensaje'])

# --- FUNCIÓN DE GOOGLE SHEETS ---

def guardar_en_sheets(datos):
    """Guarda una fila de datos en la hoja de cálculo de Google."""
    try:
        # 1. Autenticación usando el archivo JSON de la cuenta de servicio
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # El archivo service_account_key.json debe estar en la raíz del proyecto
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_KEY_FILE, scope)
        client = gspread.authorize(creds)
        
        # 2. Abrir la hoja de cálculo y la pestaña
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        
        # 3. Insertar la fila de datos
        sheet.append_row(datos)
        print("Datos guardados exitosamente en Google Sheets.")
        
    except FileNotFoundError:
        print(f"ERROR CRÍTICO: Archivo de clave JSON no encontrado: {GOOGLE_KEY_FILE}")
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"ERROR CRÍTICO: Hoja de cálculo '{SHEET_NAME}' no encontrada. Verifique el nombre en Google Drive.")
    except Exception as e:
        print(f"ERROR al guardar en Google Sheets: {e}")
        # En caso de error, la aplicación sigue funcionando (solo falla el guardado remoto)
        pass


# --- RUTAS DE FLASK ---

@app.route('/')
def home():
    # Siempre enviamos validation={} al cargar la página (soluciona UndefinedError)
    return render_template('index.html', validation={})

@app.route('/rsvp', methods=['POST'])
def rsvp():
    nombre_form = request.form.get('nombre').strip()
    try:
        asistentes_form = int(request.form.get('asistentes'))
    except (ValueError, TypeError):
        return render_template('index.html', validation={'error': 'El número de asistentes debe ser un número válido.'})
    
    mensaje = request.form.get('mensaje')
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # VALIDACIÓN DE ASIENTOS
    lista_maestra = cargar_lista_maestra()
    if nombre_form not in lista_maestra:
        return render_template('index.html', validation={'error': f'Lo sentimos, el nombre "{nombre_form}" no fue encontrado.'})
    
    asignados_permitidos = lista_maestra.get(nombre_form, 0)
    if asistentes_form > asignados_permitidos:
        return render_template('index.html', validation={'error': f'Solo tiene asignados {asignados_permitidos} lugares. Por favor, ajuste la cantidad.'})
    
    # Chequeo de duplicados
    init_db()
    with open(DB_CONFIRMADOS, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        if nombre_form in [row['Nombre'] for row in reader]:
            return render_template('index.html', validation={'error': f'¡{nombre_form}, ya confirmaste tu asistencia! Si desea modificar, contacte a los novios.'})


    # 1. GUARDA EN CSV LOCAL
    datos_fila = [fecha_actual, nombre_form, asistentes_form, mensaje]
    with open(DB_CONFIRMADOS, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(datos_fila)
    
    # 2. GUARDA EN GOOGLE SHEETS
    guardar_en_sheets(datos_fila)

    print(f"¡Nueva confirmación EXITOSA! {nombre_form} - {asistentes_form} personas")
    
    # ÉXITO: Aseguramos que 'validation' siempre se pase
    return render_template('index.html', 
                           validation={'success': True, 'nombre_invitado': nombre_form})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
