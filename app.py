from flask import Flask, render_template, request, redirect, url_for, flash
import csv
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'clave_secreta_boda'  # Necesario para mensajes flash

# Archivo donde guardaremos a los invitados
DB_FILE = 'invitados.csv'

# Función para inicializar el CSV si no existe
def init_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Fecha', 'Nombre', 'Asistentes', 'Mensaje'])

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/rsvp', methods=['POST'])
def rsvp():
    # Recibir datos del formulario HTML
    nombre = request.form.get('nombre')
    asistentes = request.form.get('asistentes')
    mensaje = request.form.get('mensaje')
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Guardar en CSV (Excel)
    init_db()
    with open(DB_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([fecha_actual, nombre, asistentes, mensaje])

    print(f"¡Nueva confirmación! {nombre} - {asistentes} personas")
    
    # Enviar mensaje de éxito a la página (Feedback visual)
    return render_template('index.html', success=True, nombre_invitado=nombre)

if __name__ == '__main__':
    # debug=True permite que el servidor se actualice si cambias el código
    app.run(debug=True, port=5000)