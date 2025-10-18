// --- Global Elements & State ---
const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const getPropertiesBtn = document.getElementById('getPropertiesBtn');
const stopRefreshBtn = document.getElementById('stopRefreshBtn');
const statusDiv = document.getElementById('status');
const devicesContainer = document.getElementById('devicesContainer');
const connectionStatusSpan = document.getElementById('connectionStatus');

let pollingInterval = null;
let imagingPanelBuilt = false;

// --- UI Update Functions ---
function updateConnectionStatusUI(isConnected) {
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
        devicesContainer.innerHTML = '';
        const imagingPanel = document.getElementById('imagingJobContainer');
        if(imagingPanel) imagingPanel.style.display = 'none';
        imagingPanelBuilt = false;
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
            if(stopRefreshBtn) stopRefreshBtn.style.display = 'none';
        }
    }
}

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
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            updateConnectionStatusUI(true);
            updateStatus(data.message, 'success');
        } else {
            updateConnectionStatusUI(false);
            updateStatus(data.message, 'error');
        }
    })
    .catch(err => {
        console.error("Connection fetch error:", err);
        updateConnectionStatusUI(false);
        updateStatus("Error: Could not communicate with web server.", "error");
    });
});

disconnectBtn.addEventListener('click', () => {
    fetch('/disconnect', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        updateConnectionStatusUI(false);
        updateStatus(data.message, 'success');
    });
});

getPropertiesBtn.addEventListener('click', () => {
    sendCommand('<getProperties version="1.7"/>');
    if (!pollingInterval) {
        // Immediately fetch data once, then start the interval
        fetchDeviceData(); 
        pollingInterval = setInterval(fetchDeviceData, 2000);
        stopRefreshBtn.style.display = 'inline-block';
    }
});

stopRefreshBtn.addEventListener('click', () => {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
        stopRefreshBtn.style.display = 'none';
        updateStatus('Live refresh stopped.', 'success');
    }
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

function fetchDeviceData() {
    fetch('/get_device_data')
    .then(res => res.json())
    .then(data => {
        if (!data.is_connected && pollingInterval) {
            console.log("Server reports INDI is disconnected. Stopping polling.");
            updateConnectionStatusUI(false);
            return;
        }
        renderDevices(data.devices);
        
        // THE FIX: Call the dedicated status updater on every poll
        updateImagingStatus(data);

    }).catch(err => {
        console.error("Fetch error:", err);
        updateConnectionStatusUI(false);
    });
}

// function to update the imaging status bar
function updateImagingStatus(data) {
    const jobStatusText = document.getElementById('jobStatusText');
    if (!jobStatusText) return;

    // Priority 1: A new image has been saved. This is the final state.
    if (data.last_saved_image) {
        // Use replace to handle both Windows and Linux paths
        jobStatusText.textContent = `Image Saved: ${data.last_saved_image.replace(/\\/g, '/')}`;
        return;
    }

    // Priority 2: Exposure is in progress.
    // Find any CCD device in the data payload.
    const ccdDeviceName = Object.keys(data.devices).find(name => name.toUpperCase().includes('CCD'));
    if (ccdDeviceName) {
        const ccd = data.devices[ccdDeviceName];
        const exposureProp = ccd.CCD_EXPOSURE;
        if (exposureProp) {
            const state = exposureProp.attributes.state;
            if (state === 'Busy') {
                const exposureValue = exposureProp.elements['CCD_EXPOSURE_VALUE']?.text || '0';
                const formattedTime = parseFloat(exposureValue).toFixed(1);
                jobStatusText.textContent = `Exposing... (${formattedTime}s remaining)`;
                return;
            } else if (state === 'Ok') {
                // Only show this transitional message if we were just exposing.
                if (jobStatusText.textContent.startsWith("Exposing")) {
                    jobStatusText.textContent = 'Exposure complete. Awaiting image data...';
                    return;
                }
            }
        }
    }

    // Priority 3: Default to Idle if no other state applies.
    // We only set to Idle if the status isn't showing a final "Saved" message.
    if (!jobStatusText.textContent.startsWith("Image Saved")) {
        jobStatusText.textContent = 'Idle';
    }
}

function renderDevices(devices) {
    const openDevices = new Set();
    document.querySelectorAll('#devicesContainer .device-details[open]').forEach(detail => {
        const summary = detail.querySelector('.device-summary');
        if(summary) openDevices.add(summary.textContent);
    });

    let ccdDeviceName = null;
    const currentDeviceIds = new Set();

    devicesContainer.innerHTML = ''; // Clear and redraw - this is the source of the flicker but it's reliable

    for (const deviceName in devices) {
        if (deviceName.toUpperCase().includes('CCD')) {
            ccdDeviceName = deviceName;
        }
        const deviceData = devices[deviceName];
        const deviceId = `device-${deviceName.replace(/\s+/g, '-')}`;
        currentDeviceIds.add(deviceId);

        const details = document.createElement('details');
        details.id = deviceId;
        details.className = 'device-details';
        
        const summary = document.createElement('summary');
        summary.className = 'device-summary';
        summary.textContent = deviceName;
        details.appendChild(summary);

        const propertiesDiv = document.createElement('div');
        propertiesDiv.className = 'device-properties';
        details.appendChild(propertiesDiv);

        for (const propName in deviceData) {
            renderDeviceProperty(propertiesDiv, deviceName, propName, deviceData[propName]);
        }
        if (openDevices.has(deviceName)) {
            details.open = true;
        }
        devicesContainer.appendChild(details);
    }

    const imagingPanelContainer = document.getElementById('imagingJobContainer');
    if (ccdDeviceName) {
        if (!imagingPanelBuilt) {
            buildImagingJobPanel(ccdDeviceName);
            imagingPanelBuilt = true;
        }
        imagingPanelContainer.style.display = 'block';
    } else {
        imagingPanelContainer.style.display = 'none';
    }
}

function renderDeviceProperty(propertiesDiv, deviceName, propName, data) {
    const propContainer = document.createElement('div');
    const attr = data.attributes;
    let listHTML = '<ul>';
    for (const elemName in data.elements) {
        const elem = data.elements[elemName];
        listHTML += `<li>${elem.attributes.label}: <span>${elem.text}</span></li>`;
    }
    listHTML += '</ul>';
    propContainer.innerHTML = `<h4>${attr.label} (<span class="prop-state">${attr.state}</span>)</h4>${listHTML}`;
    propertiesDiv.appendChild(propContainer);
    
}

function buildImagingJobPanel(ccdName) {
    const container = document.getElementById('imagingJobContainer');
    container.innerHTML = `
        <div id="imaging-panel" class="imaging-panel">
            <h3>Imaging Job: <span class="ccd-name">${ccdName}</span></h3>
            <div class="job-controls">
                <div class="control-group">
                    <label for="saveSubfolder">Project Name (Subfolder)</label>
                    <input type="text" id="saveSubfolder" name="saveSubfolder" placeholder="e.g., M42_Project">
                </div>
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
                    <input type="number" id="exposureLength" name="exposureLength" value="10" min="0.001" step="1">
                </div>
                <div class="control-group">
                    <label for="isoSetting">ISO</label>
                    <input type="number" id="isoSetting" name="isoSetting" value="1600" step="100" min="100">
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

    document.getElementById('startJobBtn').addEventListener('click', () => {
		const jobStatusText = document.getElementById('jobStatusText');
        if (jobStatusText) jobStatusText.textContent = "Starting Job...";
        
		const ccdNameElement = document.querySelector('#imaging-panel .ccd-name');
        if (!ccdNameElement) return;
        const jobData = {
            ccdName: ccdNameElement.textContent,
            subfolder: document.getElementById('saveSubfolder').value,
            photoType: document.getElementById('photoType').value,
            count: document.getElementById('photoCount').value,
            exposure: document.getElementById('exposureLength').value,
            iso: document.getElementById('isoSetting').value
        };
        fetch('/start_imaging_job', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(jobData)
        }).then(res => res.json()).then(data => updateStatus(data.message, data.status));
    });

    // Add a listener for when an image is saved
    document.addEventListener('image_saved', (e) => {
        const jobStatusText = document.getElementById('jobStatusText');
        if (jobStatusText) {
            jobStatusText.textContent = `Image saved: ${e.detail.filepath}`;
        }
    });
}

// Add an event listener to the document to handle the custom event
document.addEventListener('image_saved_check', (e) => {
    const jobStatusText = document.getElementById('jobStatusText');
    if (jobStatusText) {
        jobStatusText.textContent = `Image saved: ${e.detail.filepath}`;
    }
});
