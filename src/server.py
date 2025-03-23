import re
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import tempfile
import os
import threading
import logging
from wakepy import keep

from .gen_gcode import process_svg_to_gcode
from .serial_device.xidraw_finder import find_4xidraw_port

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)


app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file size to 16 MB

def plot_file(file_path):
    try:
        serial_port = find_4xidraw_port()

        if not serial_port:
            print('Could not initialize connection')
            exit(1)
        
        def send_g_code_file(file):

            with open(file, 'r') as f:
                for l in f.readlines():
                    # remove comments
                    l = re.sub(r';.+$', '', l)

                    if l.strip() == '':
                        continue

                    serial_port.command(l)

        with keep.running():
            send_g_code_file(file_path)

        serial_port.close()

    except Exception as e:
        print(f"Error plotting file: {e}")
        if serial_port:
            serial_port.close()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/plot', methods=['POST'])
def upload_file():
    # Check if the request contains both the file and page_size
    if 'file' not in request.files or 'page_size' not in request.form:
        return jsonify(message="File or page_size parameter is missing"), 400

    file = request.files['file']
    page_size = request.form['page_size']

    # Ensure the file and page_size exist and file has a name
    if file.filename == '' or page_size == '':
        return jsonify(message="File or page_size cannot be empty"), 400
    
    temp_dir = tempfile.mkdtemp()  # This will persist until you delete it manually
    file_path = os.path.join(temp_dir, file.filename)

    # Save the file to the temporary directory
    file_path = os.path.join(temp_dir, file.filename)
    file.save(file_path)

    output_file = os.path.join(temp_dir, 'output')
    process_svg_to_gcode(file_path, output_file, target_page_size=page_size, split_layers=False)

    # Start the plotting process in a separate thread
    thread = threading.Thread(target=plot_file, args=(f'{output_file}.gcode',))
    thread.start()

    # Return a response immediately while plotting happens in the background
    return jsonify(message=f"File '{file.filename}' uploaded successfully!", 
                   page_size=page_size, 
                   temp_file_location=file_path,
                   plotting="started")

if __name__ == '__main__':
    app.run(debug=True)
