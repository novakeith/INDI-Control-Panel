import socket
import threading
import xml.etree.ElementTree as ET
from threading import Lock
from flask import Flask, jsonify, request, render_template
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)

# --- Global State ---
indi_socket = None
listener_thread = None
INDI_DEVICES = {}
devices_lock = Lock()
CURRENT_SAVE_SUBFOLDER = None
LAST_SAVED_IMAGE = None

# --- Helper function to handle incoming image data ---
def handle_blob_vector(sock, root):
    global CURRENT_SAVE_SUBFOLDER, LAST_SAVED_IMAGE
    device_name = root.get('device')
    try:
        blob_element = root.find('oneBLOB')
        if blob_element is None: return
        blob_size = int(blob_element.get('size'))
        blob_format = blob_element.get('format')
        print(f"[DEBUG] Receiving BLOB: Size {blob_size}, Format {blob_format}")
        image_data = bytearray()
        sock.settimeout(30.0)
        while len(image_data) < blob_size:
            remaining = blob_size - len(image_data)
            chunk = sock.recv(min(4096, remaining))
            if not chunk: return
            image_data.extend(chunk)
        
        base_dir = 'images'
        subfolder_name = CURRENT_SAVE_SUBFOLDER if CURRENT_SAVE_SUBFOLDER else ''
        target_dir = os.path.join(base_dir, subfolder_name)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_{device_name.replace(' ', '_')}{blob_format}"
        filepath = os.path.join(target_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        LAST_SAVED_IMAGE = os.path.join(subfolder_name, filename)
        print(f"[DEBUG] Saved image to {filepath}. Stored last image as {LAST_SAVED_IMAGE}")
    except Exception as e:
        print(f"[DEBUG] ERROR in handle_blob_vector: {e}")
    finally:
        sock.settimeout(1.0)

# --- Core INDI Listener Thread ---
def listen_to_indi_server():
    global indi_socket, INDI_DEVICES
    print("[DEBUG] Main listener thread started and is running.")
    while True:
        if not indi_socket:
            time.sleep(1)
            continue
        
        active_socket = indi_socket
        buffer = ""
        try:
            while active_socket == indi_socket and indi_socket is not None:
                try:
                    data = active_socket.recv(4096).decode('utf-8', errors='ignore')
                    if not data:
                        print("[DEBUG] INDI server disconnected.")
                        break
                    
                    buffer += data
                    while True:
                        start_index = buffer.find('<')
                        if start_index == -1: break
                        if start_index > 0: buffer = buffer[start_index:]
                        end_of_start_tag = buffer.find('>')
                        if end_of_start_tag == -1: break
                        tag_parts = buffer[1:end_of_start_tag].split()
                        if not tag_parts:
                            buffer = buffer[end_of_start_tag + 1:]
                            continue
                        tag_name = tag_parts[0]
                        end_tag = f"</{tag_name}>"
                        end_index = buffer.find(end_tag)
                        if end_index == -1: break
                        message_end = end_index + len(end_tag)
                        message = buffer[:message_end]
                        buffer = buffer[message_end:]
                        try:
                            root = ET.fromstring(message)
                            if root.tag == 'setBLOBVector':
                                handle_blob_vector(active_socket, root)
                            else:
                                update_device_properties(root)
                        except ET.ParseError as e:
                            print(f"[DEBUG] XML Parse Error: {e}")
                except socket.timeout:
                    continue 
                except Exception as e:
                    print(f"[DEBUG] Unhandled exception in receive loop: {e}")
                    break
        finally:
            print("[DEBUG] Exited receive loop. Cleaning up this connection.")
            if active_socket:
                try: active_socket.close()
                except Exception: pass
            if indi_socket == active_socket:
                indi_socket = None
                with devices_lock:
                    INDI_DEVICES.clear()

# --- Property Update Handler ---
def update_device_properties(root):
    global INDI_DEVICES, devices_lock
    device_name = root.get('device')
    prop_name = root.get('name')
    if not device_name or not prop_name: return

    with devices_lock:
        if device_name not in INDI_DEVICES: INDI_DEVICES[device_name] = {}
        if root.tag == 'delProperty':
            if prop_name in INDI_DEVICES[device_name]: del INDI_DEVICES[device_name][prop_name]
            return
        if root.tag.startswith('def'):
            prop_data = {'attributes': root.attrib, 'elements': {}}
            for element in root:
                prop_data['elements'][element.get('name')] = {'text': element.text.strip() if element.text else '', 'attributes': element.attrib}
            INDI_DEVICES[device_name][prop_name] = prop_data
        elif root.tag.startswith('set'):
            if prop_name in INDI_DEVICES[device_name]:
                for key, value in root.attrib.items():
                    INDI_DEVICES[device_name][prop_name]['attributes'][key] = value
                for element in root:
                    elem_name = element.get('name')
                    if elem_name in INDI_DEVICES[device_name][prop_name]['elements']:
                        INDI_DEVICES[device_name][prop_name]['elements'][elem_name]['text'] = element.text.strip() if element.text else ''

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/connect', methods=['POST'])
def connect_to_indi():
    global indi_socket
    if indi_socket:
        return jsonify({'status': 'error', 'message': 'A connection is already active.'})
    host = request.json.get('host')
    try:
        new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        new_socket.settimeout(1.0)
        new_socket.connect((host, 7624))
        indi_socket = new_socket
        print(f"[DEBUG] Connection successful. Socket assigned.")
        return jsonify({'status': 'success', 'message': f'Successfully connected to {host}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Connection failed: {e}"})

@app.route('/disconnect', methods=['POST'])
def disconnect_from_indi():
    global indi_socket
    if indi_socket:
        print("[DEBUG] Disconnect requested. Closing socket.")
        try:
            indi_socket.close()
        except Exception: pass
        indi_socket = None
        with devices_lock:
            INDI_DEVICES.clear()
    return jsonify({'status': 'success', 'message': 'Disconnected.'})

@app.route('/send_command', methods=['POST'])
def send_command():
    command = request.json.get('command')
    if indi_socket and command:
        try:
            indi_socket.sendall(command.encode())
            return jsonify({'status': 'success', 'message': 'Command sent.'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f"Send failed: {e}"})
    return jsonify({'status': 'error', 'message': 'Not connected.'})

# --- THE DEFINITIVE FIX: AN INTELLIGENT IMAGING JOB ---
@app.route('/start_imaging_job', methods=['POST'])
def start_imaging_job():
    global CURRENT_SAVE_SUBFOLDER, LAST_SAVED_IMAGE, INDI_DEVICES, devices_lock
    if not indi_socket:
        return jsonify({'status': 'error', 'message': 'Not connected.'})
    
    LAST_SAVED_IMAGE = None
    data = request.json
    subfolder, exposure, ccd_name, photo_type, iso = data.get('subfolder'), data.get('exposure'), data.get('ccdName'), data.get('photoType'), data.get('iso')
    
    CURRENT_SAVE_SUBFOLDER = secure_filename(subfolder) if subfolder else None
    
    commands_to_send = []
    
    with devices_lock:
        ccd_properties = INDI_DEVICES.get(ccd_name, {})

        print("\n[DEBUG] === Building Intelligent Imaging Sequence ===")
        
        # Step 1: Connect to the driver (The Handshake)
        # This is mandatory to ensure the driver is awake and has defined its properties.
        commands_to_send.append(f'<newSwitchVector device="{ccd_name}" name="CONNECTION"><oneSwitch name="CONNECT">On</oneSwitch></newSwitchVector>')
        print(f"[DEBUG] Step 1 (MANDATORY): Connecting to driver '{ccd_name}'.")
        
        # Step 2: Claim BLOB ownership
        commands_to_send.append(f'<enableBLOB device="{ccd_name}">Also</enableBLOB>')
        print("[DEBUG] Step 2: Claiming BLOB ownership...")
        
        # Step 3: Check for FRAME_TYPE support
        if 'CCD_FRAME_TYPE' in ccd_properties:
            frame_type_map = {'light': 'FRAME_LIGHT', 'bias': 'FRAME_BIAS', 'dark': 'FRAME_DARK', 'flat': 'FRAME_FLAT'}
            indi_frame_type = frame_type_map.get(photo_type.lower(), 'FRAME_LIGHT')
            commands_to_send.append(f'<newSwitchVector device="{ccd_name}" name="CCD_FRAME_TYPE"><oneSwitch name="{indi_frame_type}">On</oneSwitch></newSwitchVector>')
            print(f"[DEBUG] Step 3: CCD_FRAME_TYPE property found. Will set to {indi_frame_type}.")
        else:
            print("[DEBUG] Step 3: CCD_FRAME_TYPE property not found. Skipping.")

        # Step 4: Check for UPLOAD_MODE support
        if 'CCD_UPLOAD_MODE' in ccd_properties:
            commands_to_send.append(f'<newSwitchVector device="{ccd_name}" name="CCD_UPLOAD_MODE"><oneSwitch name="UPLOAD_CLIENT">On</oneSwitch></newSwitchVector>')
            print("[DEBUG] Step 4: CCD_UPLOAD_MODE property found. Will set to CLIENT.")
        else:
            print("[DEBUG] Step 4: CCD_UPLOAD_MODE property not found. Skipping.")

        # Step 5: Check for ISO support
        if 'CCD_CONTROLS' in ccd_properties and 'ISO' in ccd_properties['CCD_CONTROLS']['elements']:
            commands_to_send.append(f'<newNumberVector device="{ccd_name}" name="CCD_CONTROLS"><oneNumber name="ISO">{iso}</oneNumber></newSwitchVector>')
            print(f"[DEBUG] Step 5: CCD_CONTROLS.ISO property found. Will set to {iso}.")
        else:
            print("[DEBUG] Step 5: CCD_CONTROLS.ISO property not found. Skipping.")
            
        # Step 6: The exposure command is always sent
        commands_to_send.append(f'<newNumberVector device="{ccd_name}" name="CCD_EXPOSURE"><oneNumber name="CCD_EXPOSURE_VALUE">{exposure}</oneNumber></newNumberVector>')
        print(f"[DEBUG] Step 6: Will set exposure to {exposure}s.")

    try:
        # Send the dynamically built command sequence with delays
        for i, command in enumerate(commands_to_send):
            print(f"[DEBUG] Sending command {i+1}/{len(commands_to_send)}: {command}")
            indi_socket.sendall(command.encode())
            # Use a longer delay after the crucial connection command
            delay = 1.0 if "CONNECTION" in command else 0.5
            time.sleep(delay)
            
        print("[DEBUG] === Imaging Command Sequence Sent Successfully ===\n")
        return jsonify({'status': 'success', 'message': f'Exposure started for {exposure}s.'})
    except Exception as e:
        print(f"[DEBUG] ERROR sending imaging sequence: {e}")
        return jsonify({'status': 'error', 'message': f'Failed to send commands: {e}'})

@app.route('/get_device_data', methods=['GET'])
def get_device_data():
    global LAST_SAVED_IMAGE
    with devices_lock:
        is_connected = indi_socket is not None
        response_data = {
            'devices': INDI_DEVICES,
            'is_connected': is_connected,
            'last_saved_image': LAST_SAVED_IMAGE
        }
        return jsonify(response_data)

# --- Start the single, immortal listener thread when the app starts ---
if __name__ != '__main__':
    if listener_thread is None:
        listener_thread = threading.Thread(target=listen_to_indi_server, daemon=True)
        listener_thread.start()

