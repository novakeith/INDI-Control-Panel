#!/bin/bash

# A script to launch the INDI Control Panel web application
# using the Gunicorn WSGI server. It automatically detects
# if gunicorn is installed in a local virtual environment.

# --- Find the gunicorn executable ---
GUNICORN_CMD=""
if [ -x "./bin/gunicorn" ]; then
    # Found in a local virtual environment (e.g., ./venv/bin/gunicorn)
    GUNICORN_CMD="./bin/gunicorn"
    echo "Found gunicorn in local virtual environment."
elif command -v gunicorn &> /dev/null; then
    # Found in the system's PATH
    GUNICORN_CMD="gunicorn"
    echo "Found gunicorn in system PATH."
else
    # Could not find gunicorn anywhere
    echo "ERROR: gunicorn executable not found." >&2
    echo "Please install gunicorn ('pip install gunicorn') or activate your virtual environment." >&2
    exit 1
fi

# --- Launch the application ---
echo "Starting INDI Control Panel on http://0.0.0.0:5000"

# --worker-class eventlet: A special worker required for WebSocket support.
# -w 1: With eventlet, one worker can handle many concurrent connections.
# --bind 0.0.0.0:5000: Binds to port 8000 on all network interfaces.
# indicontrolpanel:app: Tells Gunicorn to look inside the 'indicontrolpanel.py'
#                      file for the Flask instance named 'app'.
$GUNICORN_CMD --worker-class eventlet -w 1 --bind 0.0.0.0:5000 indicontrolpanel:app

