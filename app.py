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
DB_MAESTRA = 'lista_maestra_flexible.csv' 
GOOGLE_SERVICE_ACCOUNT_KEY = 'GOOGLE_SERVICE_ACCOUNT_JSON'
SHEET_NAME = 'Lista de Invitados Boda Laiza y David'
WORKSHEET_NAME = 'Confirmados'

# --- CONFIGURACIÓN DE ETAPAS ---
# Solo permitimos Base y Etapa 1 por ahora
ETAPAS_PERMITIDAS = ['BASE', 'ETAPA 1']

# --- FUNCIONES DE APOYO ---

def get_google_sheet():
    """Conecta con Google Sheets usando la clave en variables de entorno."""
    try:
        creds_json = json.loads(os.environ.get(GOOGLE_SERVICE_ACCOUNT_KEY))
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    except Exception as e:
        print(f"Error conexión Sheets: {e}")
        return None

def cargar_lista_maestra():
    """Carga los invitados del CSV maestro."""
    lista = {}
    nombres_to_id = {}
    try:
        if not os.path.exists(DB_MAESTRA): return {}, {}
        with open(DB_MAESTRA, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                id_f = row['ID_Familia'].strip()
                if id_f not in lista: lista[id_f] = []
                invitado = {
                    'nombre': row['Nombre_Invitado'].strip(),
                    'asignados': row['Asignados'].strip(),
                    'fase': row['Fase'].strip().upper()
                }
                lista[id_f].append(invitado)
                nombres_to_id[invitado['nombre'].upper()] = id_f
    except: pass
    return lista, nombres_to_id

def obtener_respuestas_previas(id_familia):
    """Busca en el Google Sheet si la familia ya tiene respuestas guardadas."""
    ws = get_google_sheet()
    if not ws: return {}, "", ""
    
    records = ws.get_all_records()
    respuestas = {}
    msg = ""
    conf = ""
    
    for row in records:
        if str(row.get('ID_Familia')) == str(id_familia):
            nombre = row.get('Nombre_Invitado')
            respuestas[nombre] = row.get('Asistencia')
            msg = row.get('Mensaje', '')
            conf = row.get('Confirmador_Quien_Escribió', '')
    
    return respuestas, msg, conf

# --- RUTAS ---

@app.route('/')
def home():
    return render_template('index.html', validation={}, family_members=[], current_id='')

@app.route('/rsvp', methods=['POST'])
def rsvp_controller():
    lista_maestra, nombres_to_id = cargar_lista_maestra()
    
    # CASO 1: BUSCAR INVITADO
    if 'invitado_search' in request.form:
        search = request.form.get('invitado_search').strip().upper()
        
        if search not in nombres_to_id:
            return render_template('index.html', 
                validation={'error': f'No encontramos el nombre "{search}". Revisa que esté igual que en tu invitación.'},
                family_members=[], current_id='')

        id_f = nombres_to_id[search]
        miembros = lista_maestra[id_f]
        fase_familia = miembros[0]['fase']

        # Filtro de Etapa
        if fase_familia not in ETAPAS_PERMITIDAS:
            return render_template('index.html', 
                validation={'error': 'Tu invitación aún no está disponible para confirmación.'},
                family_members=[], current_id='')

        # Cargar respuestas anteriores si existen para EDITAR
        resp_previas, msg_previo, conf_previo = obtener_respuestas_previas(id_f)
        
        # Inyectamos la asistencia previa en el objeto de miembros
        for m in miembros:
            m['asistencia_actual'] = resp_previas.get(m['nombre'], 'Pendiente')

        return render_template('index.html', 
            validation={}, 
            current_id=id_f, 
            family_members=miembros,
            confirmador_name=conf_previo if conf_previo else search,
            mensaje_anterior=msg_previo)

    # CASO 2: GUARDAR / EDITAR RESPUESTAS
    elif 'id_familia_hidden' in request.form:
        id_f = request.form.get('id_familia_hidden')
        quien = request.form.get('confirmador_quien_escribio')
        mensaje = request.form.get('mensaje', '')
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        ws = get_google_sheet()
        if not ws: return "Error de conexión con la base de datos", 500
        
        # Obtenemos encabezados para saber qué columna es cada cosa
        headers = ws.row_values(1)
        try:
            col_id = headers.index('ID_Familia') + 1
            col_nombre = headers.index('Nombre_Invitado') + 1
            col_asis = headers.index('Asistencia') + 1
            col_msg = headers.index('Mensaje') + 1
            col_conf = headers.index('Confirmador_Quien_Escribió') + 1
            col_fecha = headers.index('Fecha') + 1
        except: return "Error: Las columnas del Sheet no coinciden", 500

        # Procesamos cada invitado
        all_rows = ws.get_all_values()
        
        for key, value in request.form.items():
            if key.startswith('asistencia_'):
                guest_name = key.replace('asistencia_', '').replace('_', ' ').strip()
                
                # Buscamos si ya existe la fila para este invitado de esta familia para ACTUALIZAR
                fila_encontrada = -1
                for i, row in enumerate(all_rows):
                    if str(row[col_id-1]) == str(id_f) and row[col_nombre-1].upper() == guest_name.upper():
                        fila_encontrada = i + 1
                        break
                
                if fila_encontrada != -1:
                    # EDITAR EXISTENTE
                    ws.update_cell(fila_encontrada, col_asis, value)
                    ws.update_cell(fila_encontrada, col_msg, mensaje)
                    ws.update_cell(fila_encontrada, col_conf, quien)
                    ws.update_cell(fila_encontrada, col_fecha, fecha)
                else:
                    # NUEVO REGISTRO
                    nueva_fila = [""] * len(headers)
                    nueva_fila[col_id-1] = id_f
                    nueva_fila[col_nombre-1] = guest_name
                    nueva_fila[col_asis-1] = value
                    nueva_fila[col_msg-1] = mensaje
                    nueva_fila[col_conf-1] = quien
                    nueva_fila[col_fecha-1] = fecha
                    ws.append_row(nueva_fila)

        return render_template('index.html', validation={'success': True}, family_members=[], current_id='')

    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
