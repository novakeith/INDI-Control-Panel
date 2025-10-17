// --- Global Elements & State ---
const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const getPropertiesBtn = document.getElementById('getPropertiesBtn');
const stopRefreshBtn = document.getElementById('stopRefreshBtn');
const statusDiv = document.getElementById('status');
const devicesContainer = document.getElementById('devicesContainer');
const connectionStatusSpan = document.getElementById('connectionStatus');

let imagingPanelBuilt = false;
const socket = io(); // Connect to the server's WebSocket

// --- UI Update Functions ---

/**
 * Updates the main connection status UI (buttons and status pill).
 * This is the single source of truth for the connection UI.
 * @param {boolean} isConnected - Whether we are connected to the INDI server.
 */
function updateConnectionStatus(isConnected) {
    if (isConnected) {
        connectionStatusSpan.textContent = 'Connected';
        connectionStatusSpan.className = 'status-connected';
        connectBtn.style.display = 'none';
        disconnectBtn.style.display = 'inline-block';
    } else {
        connectionStatusSpan.textContent = 'Disconnected';
        connectionStatusSpan.className = 'status-disconnected';
        connectBtn.style.display = 'inline-block';
        disconnectBtn.style.display = 'none';
        devicesContainer.innerHTML = ''; // Clear devices on disconnect
        document.getElementById('imagingJobContainer').style.display = 'none'; // Hide imaging panel
        imagingPanelBuilt = false; // Allow panel to be rebuilt on next connection
    }
}

// --- WebSocket Event Handlers ---

socket.on('connect', () => {
    console.log('Successfully connected to the web server via WebSocket.');
});

socket.on('initial_state', (data) => {
    const { devices, is_indi_connected } = data;
    console.log('Received initial state. Is INDI connected:', is_indi_connected);
    updateConnectionStatus(is_indi_connected);
    if (is_indi_connected) {
        renderDevices(devices);
    }
});

socket.on('server_connected', (data) => {
    console.log('Server has connected to INDI:', data.message);
    updateConnectionStatus(true);
});

socket.on('server_disconnected', (data) => {
    console.log('Server has disconnected from INDI:', data.message);
    updateConnectionStatus(false);
});

socket.on('property_defined', (eventData) => {
    const { device: deviceName, name: propName, data } = eventData;
    renderDeviceProperty(deviceName, propName, data);
});

socket.on('property_updated', (eventData) => {
    updateDeviceProperty(eventData);
});

socket.on('property_deleted', (eventData) => {
    deleteDeviceProperty(eventData);
});


// --- Button Event Listeners ---

connectBtn.addEventListener('click', () => {
    const host = document.getElementById('indiHostInput').value;
    if (!host) {
        updateStatus('Please enter an IP address.', 'error');
        return;
    }
    connectionStatusSpan.textContent = 'Connecting...';
    connectionStatusSpan.className = '';
    fetch('/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: host })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'error') {
            updateConnectionStatus(false);
            updateStatus(data.message, 'error');
        }
    }).catch(error => {
        console.error('Fetch error:', error);
        updateConnectionStatus(false);
    });
});

disconnectBtn.addEventListener('click', () => {
    // THE FIX: Perform an optimistic UI update for instant feedback.
    console.log('Disconnect button clicked. Updating UI and sending request.');
    updateConnectionStatus(false); 
    fetch('/disconnect', { method: 'POST' });
});

getPropertiesBtn.addEventListener('click', () => {
    sendCommand('<getProperties version="1.7"/>');
});

// --- Helper & Rendering Functions ---

function sendCommand(command) {
    fetch('/send_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: command })
    }).then(r => r.json()).then(data => updateStatus(data.message, data.status));
}

function updateStatus(message, status) {
    statusDiv.textContent = message;
    statusDiv.className = status === 'success' ? 'status-success' : 'status-error';
}

function renderDevices(devices) {
    devicesContainer.innerHTML = '';
    for (const deviceName in devices) {
        const deviceData = devices[deviceName];
        for (const propName in deviceData) {
            renderDeviceProperty(deviceName, propName, deviceData[propName]);
        }
    }
}

function getOrCreateDeviceContainer(deviceName) {
    const deviceId = `device-${deviceName.replace(/\s+/g, '-')}`;
    let details = document.getElementById(deviceId);
    if (!details) {
        details = document.createElement('details');
        details.id = deviceId;
        details.className = 'device-details';
        details.innerHTML = `<summary class="device-summary">${deviceName}</summary><div class="device-properties"></div>`;
        devicesContainer.appendChild(details);
    }
    return details.querySelector('.device-properties');
}

function renderDeviceProperty(deviceName, propName, data) {
    const propertiesDiv = getOrCreateDeviceContainer(deviceName);
    const propId = `prop-${deviceName}-${propName}`.replace(/\s+/g, '-');
    
    let propContainer = document.getElementById(propId);
    if (!propContainer) {
        propContainer = document.createElement('div');
        propContainer.id = propId;
        propertiesDiv.appendChild(propContainer);
    }

    let listHTML = '<ul>';
    for (const elemName in data.elements) {
        const elem = data.elements[elemName];
        const elemId = `elem-${deviceName}-${propName}-${elemName}`.replace(/\s+/g, '-');
        listHTML += `<li id="${elemId}">${elem.attributes.label}: <span>${elem.text}</span></li>`;
    }
    listHTML += '</ul>';

    propContainer.innerHTML = `<h4>${data.attributes.label} (<span class="prop-state">${data.attributes.state}</span>)</h4>${listHTML}`;

    if (deviceName.toUpperCase().includes('CCD')) {
        buildAndShowImagingPanel(deviceName);
    }
}

function updateDeviceProperty({ device: deviceName, name: propName, state, elements }) {
    const propId = `prop-${deviceName}-${propName}`.replace(/\s+/g, '-');
    const propContainer = document.getElementById(propId);
    if (!propContainer) return;

    const stateSpan = propContainer.querySelector('.prop-state');
    if (stateSpan) stateSpan.textContent = state;

    for (const elemName in elements) {
        const elemId = `elem-${deviceName}-${propName}-${elemName}`.replace(/\s+/g, '-');
        const elemSpan = document.getElementById(elemId)?.querySelector('span');
        if (elemSpan) {
            elemSpan.textContent = elements[elemName];
        }
    }
}

function deleteDeviceProperty({ device: deviceName, name: propName }) {
    const propId = `prop-${deviceName}-${propName}`.replace(/\s+/g, '-');
    const propContainer = document.getElementById(propId);
    if (propContainer) propContainer.remove();
}

function buildAndShowImagingPanel(ccdName) {
    const imagingPanelContainer = document.getElementById('imagingJobContainer');
    if (!imagingPanelBuilt) {
        buildImagingJobPanel(ccdName);
        imagingPanelBuilt = true;
    }
    imagingPanelContainer.style.display = 'block';
}

function buildImagingJobPanel(ccdName) {
    const container = document.getElementById('imagingJobContainer');
    container.innerHTML = `
        <div id="imaging-panel" class="imaging-panel">
            <h3>Imaging Job: <span class="ccd-name">${ccdName}</span></h3>
            <div class="job-controls">
                <div class="control-group">
                    <label for="photoType">Photo Type</label>
                    <select id="photoType" name="photoType">
                        <option value="light">Light</option>
                        <option value="dark">Dark</option>
                        <option value="bias">Bias</option>
                        <option value="flat">Flat</option>
                    </select>
                </div>
                <div class="control-group">
                    <label for="photoCount">Number of Photos</label>
                    <input type="number" id="photoCount" name="photoCount" value="1" min="1">
                </div>
                <div class="control-group">
                    <label for="exposureLength">Exposure (s)</label>
                    <input type="number" id="exposureLength" name="exposureLength" value="10" min="0.001" step="0.1">
                </div>
                <div class="control-group">
                    <label for="isoSetting">ISO</label>
                    <input type="number" id="isoSetting" name="isoSetting" value="800" step="100" min="100">
                </div>
            </div>
            <div class="job-actions">
                <button id="startJobBtn">Start Job</button>
                <button id="cancelJobBtn">Cancel Job</button>
            </div>
            <div class="job-status">
                <strong>Status:</strong>
                <span id="jobStatusText">Idle</span>
            </div>
        </div>
    `;
}