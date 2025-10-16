# app.py

from flask import Flask, jsonify, request, render_template
import socket
import threading
from threading import Lock
import xml.etree.ElementTree as ET

app = Flask(__name__)

# INDI server connection details
INDI_HOST = 'localhost'  # Use a host that might fail for testing, e.g., 'localhost' if no server is running
INDI_PORT = 7624

# Global variable to store the INDI server socket
indi_socket = None

# device states
INDI_DEVICES = {}
devices_lock = Lock()

def listen_to_indi_server():
    global indi_socket, INDI_DEVICES
    buffer = ""
    while True:
        if indi_socket:
            try:
                data = indi_socket.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    print("INDI server disconnected.")
                    with devices_lock:
                        INDI_DEVICES.clear()
                    indi_socket.close()
                    indi_socket = None
                    break
                
                buffer += data

                # Process all complete XML documents in the buffer
                while True:
                    # Find the start of the next XML document
                    start_index = buffer.find('<')
                    if start_index == -1:
                        # No start tag found, nothing to do
                        break

                    # If there's text before the start tag, discard it
                    if start_index > 0:
                        buffer = buffer[start_index:]
                    
                    # Find the end of the opening tag to get the tag name
                    end_of_start_tag = buffer.find('>')
                    if end_of_start_tag == -1:
                        # Incomplete opening tag, wait for more data
                        break
                    
                    # Extract the tag name (e.g., "defTextVector")
                    # Handles tags with and without attributes
                    tag_parts = buffer[1:end_of_start_tag].split()
                    if not tag_parts:
                        # Malformed tag, e.g., "< >"
                        buffer = buffer[end_of_start_tag + 1:]
                        continue # Try again
                    
                    tag_name = tag_parts[0]
                    end_tag = f"</{tag_name}>"
                    
                    end_index = buffer.find(end_tag)
                    if end_index == -1:
                        # Full document not yet in buffer, wait for more data
                        break
                        
                    # Extract the complete XML message
                    message_end = end_index + len(end_tag)
                    message = buffer[:message_end]
                    
                    # Move buffer past the processed message
                    buffer = buffer[message_end:]
                    
                    try:
                        root = ET.fromstring(message)
                        update_device_properties(root)
                    except ET.ParseError as e:
                        print(f"XML Parse Error for message: {message[:100]}... Error: {e}")
                        # Continue to the next message
                        
            except socket.error as e:
                print(f"Socket error during listen: {e}")
                with devices_lock:
                    INDI_DEVICES.clear()
                indi_socket = None
                break

def update_device_properties(root):
    """Parses an XML element and updates the global INDI_DEVICES dictionary."""
    global INDI_DEVICES

    device_name = root.get('device')
    prop_name = root.get('name')

    with devices_lock:
        # Ensure device entry exists
        if device_name not in INDI_DEVICES:
            INDI_DEVICES[device_name] = {}

        # Handle property deletion
        if root.tag == 'delProperty':
            if prop_name in INDI_DEVICES[device_name]:
                del INDI_DEVICES[device_name][prop_name]
                print(f"Deleted property: {device_name}.{prop_name}")
            return

        # Handle property definitions (def... vectors)
        if root.tag.startswith('def'):
            if prop_name not in INDI_DEVICES[device_name]:
                INDI_DEVICES[device_name][prop_name] = {}

            # Store attributes and child elements
            INDI_DEVICES[device_name][prop_name]['attributes'] = root.attrib
            INDI_DEVICES[device_name][prop_name]['elements'] = {}
            for element in root:
                INDI_DEVICES[device_name][prop_name]['elements'][element.get('name')] = {
                    'text': element.text,
                    'attributes': element.attrib
                }
            print(f"Defined property: {device_name}.{prop_name}")

        # Handle property updates (set... vectors)
        if root.tag.startswith('set'):
            if prop_name in INDI_DEVICES[device_name]:
                INDI_DEVICES[device_name][prop_name]['attributes']['state'] = root.get('state')
                for element in root:
                    elem_name = element.get('name')
                    if elem_name in INDI_DEVICES[device_name][prop_name]['elements']:
                        INDI_DEVICES[device_name][prop_name]['elements'][elem_name]['text'] = element.text
                print(f"Set property: {device_name}.{prop_name}")
                #Debugging - print(f"HTML element text: {element.text}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/connect', methods=['POST'])
def connect_to_indi():
    global indi_socket

    # Get the host from the incoming JSON request
    host = request.json.get('host')
    if not host:
        return jsonify({'status': 'error', 'message': 'Error: IP address was not provided.'})

    if not indi_socket:
        try:
            indi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Use the user-provided host to connect
            indi_socket.connect((host, INDI_PORT))

            listener_thread = threading.Thread(target=listen_to_indi_server)
            listener_thread.daemon = True
            listener_thread.start()
            return jsonify({'status': 'success', 'message': f'Successfully connected to {host}'})
        except socket.error as e:
            print(f"Failed to connect to {host}: {e}")
            return jsonify({'status': 'error', 'message': f"Connection to {host} failed: {e}"})
    else:
        return jsonify({'status': 'success', 'message': 'Already connected or socket already created; try refreshing if you have an issue'})

@app.route('/send_command', methods=['POST'])
def send_command():
    global indi_socket
    command = request.json.get('command')
    if indi_socket and command:
        try:
            indi_socket.sendall(command.encode())
            return jsonify({'status': 'success', 'message': 'Command sent successfully'})
        except socket.error as e:
            # NEW: Print the detailed error to the command line
            print(f"Failed to send command: {e}")
            # Return the error message to the browser
            return jsonify({'status': 'error', 'message': f"Failed to send command: {e}"})
    else:
        if not indi_socket:
            return jsonify({'status': 'error', 'message': 'Cannot send command: Not connected to INDI server.'})
        else:
            return jsonify({'status': 'error', 'message': 'Cannot send command: No command provided.'})

@app.route('/get_device_data', methods=['GET'])
def get_device_data():
    with devices_lock:
        return jsonify(INDI_DEVICES)
        
if __name__ == '__main__':
    app.run(debug=True)