from flask import Flask, render_template, request, redirect, url_for
import csv
import os
from datetime import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = 'clave_secreta_laizaydavid' 

# --- CONFIGURACIÓN DE ARCHIVOS ---
DB_CONFIRMADOS = 'invitados.csv'
DB_MAESTRA = 'lista_maestra_flexible.csv' # ¡NUEVO NOMBRE!
DB_CONFIRMADOS_CHECK = 'confirmados_check.csv' 

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
SHEET_NAME = 'Lista de Invitados Boda Laiza y David'
WORKSHEET_NAME = 'Confirmados' 
GOOGLE_SERVICE_ACCOUNT_KEY = 'GOOGLE_SERVICE_ACCOUNT_JSON'

# --- FUNCIONES DE BASE DE DATOS LOCALES ---

def cargar_lista_maestra():
    """Carga el CSV de la lista maestra detallada, agrupando por ID_Familia."""
    lista_detallada = {}
    
    try:
        with open(DB_MAESTRA, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Almacena todos los nombres de invitados para el chequeo rápido
            nombres_a_id = {}
            
            for row in reader:
                id_familia = row['ID_Familia'].strip()
                invitado = row['Nombre_Invitado'].strip()
                asignados = int(row['Asignados'].strip())
                
                if id_familia not in lista_detallada:
                    lista_detallada[id_familia] = []
                
                lista_detallada[id_familia].append({
                    'nombre': invitado, 
                    'asignados': asignados
                })
                
                nombres_a_id[invitado] = id_familia # Mapeo inverso
                
    except Exception as e:
        print(f"ERROR leyendo lista maestra: {e}")
        return {}, {}
        
    return lista_detallada, nombres_a_id

def init_db():
    """Inicializa los CSVs de confirmados y chequeo."""
    if not os.path.exists(DB_CONFIRMADOS):
        with open(DB_CONFIRMADOS, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Fecha', 'ID_Familia', 'Nombre_Invitado', 'Asistencia', 'Mensaje', 'Confirmador_Quien_Escribió'])
    
    # Este archivo solo guarda los ID de las familias que ya confirmaron
    if not os.path.exists(DB_CONFIRMADOS_CHECK):
        with open(DB_CONFIRMADOS_CHECK, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['ID_Familia'])

def guardar_confirmador_check(id_familia):
    """Guarda el ID_Familia para evitar duplicados."""
    with open(DB_CONFIRMADOS_CHECK, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([id_familia])

def esta_confirmado(id_familia):
    """Verifica si el ID_Familia ya envió el formulario."""
    try:
        with open(DB_CONFIRMADOS_CHECK, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            return id_familia in [row['ID_Familia'].strip() for row in reader]
    except FileNotFoundError:
        return False

# --- FUNCIÓN DE GOOGLE SHEETS ---

def guardar_en_sheets(datos):
    """Guarda una fila de datos en la hoja de cálculo de Google."""
    try:
        # (Mismo código de Google Sheets)
        creds_json = json.loads(os.environ.get(GOOGLE_SERVICE_ACCOUNT_KEY))
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        sheet.append_row(datos)
        print(f"Datos guardados exitosamente en Google Sheets.")
        
    except Exception as e:
        print(f"ERROR al guardar en Google Sheets: {e}")
        pass


# --- RUTAS DE FLASK ---

@app.route('/')
def home():
    """Ruta principal: Muestra la portada y el formulario de búsqueda de invitado."""
    # current_id: Se usa para el input oculto en el HTML si la familia ya está cargada
    return render_template('index.html', validation={}, family_members=[], current_id='')

@app.route('/rsvp', methods=['POST'])
def rsvp_controller():
    """Controla el flujo: 1. Busca el invitado y carga la familia o 2. Procesa la confirmación."""
    
    lista_detallada, nombres_a_id = cargar_lista_maestra()
    
    if 'invitado_search' in request.form:
        # --- PASO 1: BUSCAR INVITADO (Formulario de portada) ---
        invitado_search = request.form.get('invitado_search').strip()
        
        # 1. Chequea si el nombre del invitado está en CUALQUIER grupo
        if invitado_search not in nombres_a_id:
            return render_template('index.html', 
                                   validation={'error': f'Lo sentimos, el nombre "{invitado_search}" no fue encontrado en nuestra lista. Por favor, ingrese un nombre exacto de su invitación.'},
                                   family_members=[], current_id='')

        # 2. Encuentra el ID de la familia a la que pertenece ese invitado
        id_familia_encontrado = nombres_a_id[invitado_search]
        
        # 3. Chequea si la familia ya confirmó
        if esta_confirmado(id_familia_encontrado):
            return render_template('index.html', 
                                   validation={'error': f'La confirmación de la familia {id_familia_encontrado} ya fue registrada. Si necesita cambiar sus datos, contacte a los novios.'},
                                   family_members=[], current_id='')

        # 4. Familia encontrada. Preparamos el formulario detallado
        members = lista_detallada[id_familia_encontrado]
        return render_template('index.html', 
                               validation={},
                               confirmador_name=invitado_search, # Nombre de quien buscó
                               current_id=id_familia_encontrado,
                               family_members=members)

    elif 'id_familia_hidden' in request.form:
        # --- PASO 2: PROCESAR CONFIRMACIÓN (Formulario detallado) ---
        id_familia = request.form.get('id_familia_hidden').strip()
        confirmador_quien_escribio = request.form.get('confirmador_quien_escribio').strip()
        mensaje = request.form.get('mensaje', '')
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if esta_confirmado(id_familia):
            return redirect(url_for('home')) # Ya confirmaron

        asistentes_confirmados = 0
        total_a_guardar = []
        
        # Recorrer las confirmaciones de los checkboxes/selects
        for key, value in request.form.items():
            if key.startswith('asistencia_'):
                # guest_name es el nombre del invitado
                guest_name = key.replace('asistencia_', '').replace('_', ' ').strip()
                asistencia_status = 'Sí' if value == 'Si' else 'No'

                if asistencia_status == 'Sí':
                    asistentes_confirmados += 1
                
                # Fila para CSV/Sheets: [Fecha, ID_Familia, Invitado, Asistencia, Mensaje, Confirmador_Quien_Escribió]
                fila = [fecha_actual, id_familia, guest_name, asistencia_status, mensaje, confirmador_quien_escribio]
                total_a_guardar.append(fila)
        
        if asistentes_confirmados == 0:
             # Si no confirma nadie, muestra error (o permite 0 si no hay mensaje)
             # Dejaremos la validación de 0 asistentes, pero si el usuario busca y no va, se guarda 'No'
             pass 

        # Guardar en CSV Local y Google Sheets para cada miembro
        init_db()
        for fila in total_a_guardar:
            # CSV Local
            with open(DB_CONFIRMADOS, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(fila)
            
            # Google Sheets
            guardar_en_sheets(fila) 

        # Marcar a la familia como chequeada
        guardar_confirmador_check(id_familia)
        
        print(f"¡Confirmación EXITOSA! Familia {id_familia} - Confirmador: {confirmador_quien_escribio} - {asistentes_confirmados} asistentes.")
        
        return render_template('index.html', 
                               validation={'success': True, 'nombre_invitado': confirmador_quien_escribio},
                               family_members=[], current_id='')

    return redirect(url_for('home'))

if __name__ == '__main__':
    init_db()
    # Asegúrate de crear lista_maestra_flexible.csv
    app.run(debug=True, port=5000)
