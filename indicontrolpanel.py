import socket
import threading
import xml.etree.ElementTree as ET
from threading import Lock
from flask import Flask, jsonify, request, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-key!'
socketio = SocketIO(app)

# --- Global State ---
indi_socket = None
INDI_DEVICES = {}
devices_lock = Lock()
listener_thread = None # Global variable to hold our background thread

# --- Core INDI Listener Thread ---

def listen_to_indi_server():
    """
    This function now runs in a continuous loop in the background,
    waiting for the indi_socket to be active.
    """
    global indi_socket, INDI_DEVICES
    while True:
        if not indi_socket:
            socketio.sleep(1) # Use eventlet-safe sleep
            continue

        try:
            buffer = ""
            while indi_socket:
                data = indi_socket.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    print("INDI server disconnected (recv returned empty).")
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
                        update_device_properties(root)
                    except ET.ParseError as e:
                        print(f"XML Parse Error: {e} - for message: {message[:100]}...")
                    except Exception as e:
                        print(f"An unexpected error occurred while parsing: {e}")
                        
        except socket.error as e:
            print(f"Socket error in listener (e.g., disconnected by user): {e}")

        # --- UNCONDITIONAL CLEANUP for this connection attempt ---
        print("Listener performing cleanup for disconnected socket.")
        sock_to_close = indi_socket
        if sock_to_close:
            try: sock_to_close.close()
            except Exception: pass
        
        # This check prevents a redundant 'disconnected' event if the /disconnect route already sent one
        if indi_socket is not None:
            indi_socket = None
            with devices_lock:
                INDI_DEVICES.clear()
            socketio.emit('server_disconnected', {'message': 'INDI server connection lost.'}, namespace='/')

# --- Property Update Handler ---

def update_device_properties(root):
    global INDI_DEVICES
    device_name = root.get('device')
    prop_name = root.get('name')
    
    with devices_lock:
        if device_name not in INDI_DEVICES:
            INDI_DEVICES[device_name] = {}

        event_data = {'device': device_name, 'name': prop_name}

        if root.tag == 'delProperty':
            if prop_name in INDI_DEVICES[device_name]:
                del INDI_DEVICES[device_name][prop_name]
                print(f"Deleted property: {device_name}.{prop_name}")
                socketio.emit('property_deleted', event_data, namespace='/')
            return

        if root.tag.startswith('def'):
            prop_data = {'attributes': root.attrib, 'elements': {}}
            for element in root:
                prop_data['elements'][element.get('name')] = {
                    'text': element.text.strip() if element.text else '',
                    'attributes': element.attrib
                }
            INDI_DEVICES[device_name][prop_name] = prop_data
            event_data['data'] = prop_data
            print(f"Defined property: {device_name}.{prop_name}")
            socketio.emit('property_defined', event_data, namespace='/')

        if root.tag.startswith('set'):
            if prop_name in INDI_DEVICES[device_name]:
                INDI_DEVICES[device_name][prop_name]['attributes']['state'] = root.get('state')
                updated_elements = {}
                for element in root:
                    elem_name = element.get('name')
                    elem_text = element.text.strip() if element.text else ''
                    if elem_name in INDI_DEVICES[device_name][prop_name]['elements']:
                        INDI_DEVICES[device_name][prop_name]['elements'][elem_name]['text'] = elem_text
                        updated_elements[elem_name] = elem_text
                
                event_data['state'] = root.get('state')
                event_data['elements'] = updated_elements
                print(f"Set property: {device_name}.{prop_name}")
                socketio.emit('property_updated', event_data, namespace='/')

# --- Standard Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/connect', methods=['POST'])
def connect_to_indi():
    global indi_socket
    host = request.json.get('host')
    if not host:
        return jsonify({'status': 'error', 'message': 'Error: IP address was not provided.'})

    if not indi_socket:
        try:
            new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_socket.connect((host, 7624))
            print(f"Successfully connected to INDI server at {host}")
            indi_socket = new_socket
            socketio.emit('server_connected', {'message': f'Successfully connected to {host}'}, namespace='/')
            return jsonify({'status': 'success', 'message': f'Successfully connected to {host}'})
        except socket.error as e:
            print(f"Failed to connect to {host}: {e}")
            return jsonify({'status': 'error', 'message': f"Connection to {host} failed: {e}"})
    else:
        return jsonify({'status': 'success', 'message': 'Already connected'})

@app.route('/disconnect', methods=['POST'])
def disconnect_from_indi():
    global indi_socket
    if indi_socket:
        try:
            # THE FIX: Immediately notify clients and then perform cleanup.
            print("Disconnect command received. Broadcasting event.")
            socketio.emit('server_disconnected', {'message': 'User initiated disconnect.'}, namespace='/')
            indi_socket.close()
            indi_socket = None
            with devices_lock:
                INDI_DEVICES.clear()
        except Exception as e:
            print(f"Ignoring error during disconnect signal: {e}")
            # Ensure state is cleared even if close() fails
            indi_socket = None
            with devices_lock:
                INDI_DEVICES.clear()

    return jsonify({'status': 'success', 'message': 'Disconnect signal sent.'})


@app.route('/send_command', methods=['POST'])
def send_command():
    global indi_socket
    command = request.json.get('command')
    if indi_socket and command:
        try:
            indi_socket.sendall(command.encode())
            return jsonify({'status': 'success', 'message': 'Command sent successfully'})
        except socket.error as e:
            print(f"Failed to send command: {e}")
            return jsonify({'status': 'error', 'message': f"Failed to send command: {e}"})
    else:
        return jsonify({'status': 'error', 'message': 'Not connected or no command provided.'})

# --- SocketIO Connection Handler ---

@socketio.on('connect')
def handle_connect():
    global listener_thread
    print('Client connected')
    
    with devices_lock:
        if listener_thread is None:
            listener_thread = socketio.start_background_task(target=listen_to_indi_server)
            print("Started INDI listener background thread.")
        
        is_connected = indi_socket is not None
        emit('initial_state', {'devices': INDI_DEVICES, 'is_indi_connected': is_connected})

if __name__ == '__main__':
    socketio.run(app, debug=True)

