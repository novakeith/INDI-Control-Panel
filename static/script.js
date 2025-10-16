/*
Javascript to support INDI Control Panel
*/

// Get references to all interactive elements at the start
const connectBtn = document.getElementById('connectBtn');
const getPropertiesBtn = document.getElementById('getPropertiesBtn');
const stopRefreshBtn = document.getElementById('stopRefreshBtn');
const statusDiv = document.getElementById('status');
const devicesContainer = document.getElementById('devicesContainer');

// Global state variable for the polling timer
let pollingInterval = null;

// --- EVENT LISTENERS ---

/**
 * Handles the logic for the "Connect" button.
 * Now, it ONLY establishes the connection and does not start the refresh.
 */
connectBtn.addEventListener('click', () => {
    const host = document.getElementById('indiHostInput').value;
    const connectionStatusSpan = document.getElementById('connectionStatus');

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
        if (data.status === 'success') {
            connectionStatusSpan.textContent = 'Connected';
            connectionStatusSpan.className = 'status-connected';
        } else {
            connectionStatusSpan.textContent = 'Disconnected';
            connectionStatusSpan.className = 'status-disconnected';
            // If connection fails, stop any existing polling and hide buttons
            if (pollingInterval) clearInterval(pollingInterval);
            stopRefreshBtn.style.display = 'none';
        }
        updateStatus(data.message, data.status);
    })
    .catch(error => {
        console.error('Fetch error:', error);
        connectionStatusSpan.textContent = 'Disconnected';
        connectionStatusSpan.className = 'status-disconnected';
        stopRefreshBtn.style.display = 'none';
        updateStatus('Error: Could not communicate with the web server.', 'error');
    });
});

/**
 * Handles the "Get Properties" button.
 * It now sends the command AND starts the polling/refresh cycle.
 */
getPropertiesBtn.addEventListener('click', () => {
    const command = '<getProperties version="1.7"/>';
    sendCommand(command);

    // Start the polling if it's not already running
    if (!pollingInterval) {
        pollingInterval = setInterval(fetchDeviceData, 2000);
        stopRefreshBtn.style.display = 'inline-block'; // Show the stop button
        console.log('Polling started.');
    }
});

/**
 * Handles the "Stop Refresh" button.
 */
stopRefreshBtn.addEventListener('click', () => {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null; // Clear the interval variable
        stopRefreshBtn.style.display = 'none'; // Hide the button
        updateStatus('Live refresh stopped by user.', 'success');
        console.log('Polling stopped.');
    }
});


// --- HELPER FUNCTIONS --- (These are unchanged)

/**
 * Sends a command string to the INDI server.
 */
function sendCommand(command) {
    fetch('/send_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: command })
    })
    .then(response => response.json())
    .then(data => {
        updateStatus(data.message, data.status);
    })
    .catch(error => {
        console.error('Fetch error:', error);
        updateStatus('Error: Could not communicate with the web server.', 'error');
    });
}

/**
 * Updates the main status message box at the bottom of the page.
 */
function updateStatus(message, status) {
    statusDiv.textContent = message;
    if (status === 'success') {
        statusDiv.className = 'status-success';
    } else {
        statusDiv.className = 'status-error';
    }
}

/**
 * Fetches the current device and property data from the backend.
 */
function fetchDeviceData() {
    fetch('/get_device_data')
        .then(response => response.json())
        .then(data => {
            renderDevices(data);
        })
        .catch(error => {
            console.error("Failed to fetch device data:", error);
            if (pollingInterval) clearInterval(pollingInterval);
        });
}

/**
 * Renders the device data into collapsible HTML sections, preserving the open/closed state.
 */
function renderDevices(devices) {
    const openDevices = new Set();
    document.querySelectorAll('#devicesContainer .device-details[open]').forEach(openDetail => {
        const summary = openDetail.querySelector('.device-summary');
        if (summary) {
            openDevices.add(summary.textContent);
        }
    });

    devicesContainer.innerHTML = "";

    for (const deviceName in devices) {
        const device = devices[deviceName];
        const details = document.createElement('details');
        details.className = 'device-details';
        const summary = document.createElement('summary');
        summary.className = 'device-summary';
        summary.textContent = deviceName;
        const propertiesDiv = document.createElement('div');
        propertiesDiv.className = 'device-properties';

        for (const propName in device) {
            const prop = device[propName];
            const attr = prop.attributes;
            const propHeader = document.createElement('h4');
            propHeader.textContent = `${attr.label} (${attr.state})`;
            propertiesDiv.appendChild(propHeader);
            const propList = document.createElement('ul');
            for (const elemName in prop.elements) {
                const elem = prop.elements[elemName];
                const listItem = document.createElement('li');
                listItem.textContent = `${elem.attributes.label}: ${elem.text}`;
                propList.appendChild(listItem);
            }
            propertiesDiv.appendChild(propList);
        }
        
        details.appendChild(summary);
        details.appendChild(propertiesDiv);

        if (openDevices.has(deviceName)) {
            details.open = true;
        }

        devicesContainer.appendChild(details);
    }
}