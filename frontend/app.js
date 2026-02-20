// Utility to populate device specs
function populateDeviceSpecs(specs) {
    // Device Specs Tab
    document.getElementById('spec-device-model').textContent = specs.device_model || 'N/A';
    document.getElementById('spec-processor-model').textContent = specs.processor_model || 'N/A';
    document.getElementById('spec-cpu-cores').textContent = specs.cpu_cores || 'N/A';
    document.getElementById('spec-cpu-threads').textContent = specs.cpu_threads || 'N/A';
    document.getElementById('spec-gpu-model').textContent = specs.gpu_model || 'N/A';
    document.getElementById('spec-gpu-memory').textContent = specs.gpu_total_memory_gb || 'N/A';
    document.getElementById('spec-ram-total').textContent = specs.ram_total_gb || 'N/A';
    
    // New fields in Device Specs tab
    document.getElementById('spec-os-name').textContent = specs.os_name || 'N/A';
    document.getElementById('spec-os-version').textContent = specs.os_version || 'N/A';
    document.getElementById('spec-bios-vendor').textContent = specs.bios_vendor || 'N/A';
    document.getElementById('spec-bios-version').textContent = specs.bios_version || 'N/A';
    document.getElementById('spec-cpu-tdp').textContent = specs.cpu_tdp_watts || 'N/A';

    // Network Info fields (these come from the specs API but are displayed in the Network tab)
    document.getElementById('spec-network-interface').textContent = specs.network_interface_name || 'N/A';
    document.getElementById('spec-private-ip').textContent = specs.private_ip_address || 'N/A';
    document.getElementById('spec-mac-address').textContent = specs.mac_address || 'N/A';
}

// Utility to populate network metrics
function populateNetworkMetrics(metrics) {
    // Network Performance
    document.getElementById('metric-download').textContent = (metrics.speedtest_download_mbps || 'N/A') + ' Mbps';
    document.getElementById('metric-upload').textContent = (metrics.speedtest_upload_mbps || 'N/A') + ' Mbps';
    document.getElementById('metric-jitter').textContent = (metrics.network_jitter_ms || 'N/A') + 'ms';

    // ISP & Location
    document.getElementById('metric-public-ip').textContent = metrics.public_ip || 'N/A';
    document.getElementById('metric-region').textContent = metrics.geo_city || metrics.region || 'N/A';
    document.getElementById('metric-country').textContent = metrics.geo_country || metrics.country || 'N/A';
    document.getElementById('metric-isp-name').textContent = metrics.isp_name || 'N/A';

    // WiFi Details
    document.getElementById('metric-wifi-ssid').textContent = metrics.wifi_ssid || 'N/A';
    document.getElementById('metric-wifi-signal').textContent = (metrics.wifi_signal_percent !== undefined ? metrics.wifi_signal_percent : 'N/A') + '%';
    // Link speed removed
}


// Fetch and populate data from backend API
async function fetchAndPopulate() {
    try {
        const specsRes = await fetch('http://localhost:5000/api/device-specs');
        const specs = await specsRes.json();
        // The device specs API returns static/semi-static data, including OS/BIOS/Network Address info.
        populateDeviceSpecs(specs); 
    } catch (e) {
        console.error('Error fetching device specs:', e);
    }
    try {
        const metricsRes = await fetch('http://localhost:5000/api/network-metrics');
        const metrics = await metricsRes.json();
        // The network metrics API returns live performance/speedtest data.
        populateNetworkMetrics(metrics);
        // Also call the real-time function once to populate the third tab immediately
        populateRealtimeMetrics(metrics);
    } catch (e) {
        console.error('Error fetching network metrics:', e);
    }
}

// Tab switching logic
document.addEventListener('DOMContentLoaded', () => {
    const deviceSpecsTab = document.getElementById('deviceSpecsTab');
    const networkTab = document.getElementById('networkTab');
    const realtimeTab = document.getElementById('realtimeTab');
    const deviceSpecsSection = document.getElementById('deviceSpecsSection');
    const networkSection = document.getElementById('networkSection');
    const realtimeSection = document.getElementById('realtimeSection');

    // Add event listener for speed test button
    const runSpeedTestBtn = document.getElementById('runSpeedTestBtn');
    if (runSpeedTestBtn) {
        runSpeedTestBtn.addEventListener('click', async () => {
            runSpeedTestBtn.disabled = true;
            runSpeedTestBtn.textContent = 'Running...';
            try {
                const res = await fetch('http://localhost:5000/api/run-speedtest', { method: 'POST' });
                const result = await res.json();
                if (result.status === 'success') {
                    // Wait a moment for backend to update Firestore
                    setTimeout(fetchAndPopulate, 2000);
                }
            } catch (e) {
                console.error('Error triggering speed test:', e);
            }
            runSpeedTestBtn.disabled = false;
            runSpeedTestBtn.textContent = 'Run Speed Test';
        });
    }

    function activateTab(tab, section) {
        [deviceSpecsTab, networkTab, realtimeTab].forEach(t => t.classList.remove('active'));
        [deviceSpecsSection, networkSection, realtimeSection].forEach(s => s.classList.remove('active'));
        tab.classList.add('active');
        section.classList.add('active');
    }

    deviceSpecsTab.addEventListener('click', () => {
        activateTab(deviceSpecsTab, deviceSpecsSection);
    });
    networkTab.addEventListener('click', () => {
        activateTab(networkTab, networkSection);
    });
    realtimeTab.addEventListener('click', () => {
        activateTab(realtimeTab, realtimeSection);
    });

    // Initialize with first tab active
    activateTab(deviceSpecsTab, deviceSpecsSection);

    fetchAndPopulate();
    // Auto-refresh real-time metrics every 5 seconds
    setInterval(fetchRealtimeMetrics, 5000);
});

// Helper function to populate Real-Time metrics (extracted from the main interval function)
function populateRealtimeMetrics(metrics) {
    document.getElementById('realtime-cpu-load').textContent = (metrics.cpu_load_percent || 'N/A') + '%';
    document.getElementById('realtime-ram-usage').textContent = (metrics.ram_used_percent || 'N/A') + '%';
    document.getElementById('realtime-disk-usage').textContent = (metrics.disk_usage_percent || 'N/A') + '%';
    document.getElementById('realtime-gpu-utilization').textContent = (metrics.gpu_utilization_percent || 'N/A') + '%';
    
    document.getElementById('realtime-download').textContent = (metrics.actual_download_mbps || 'N/A') + ' Mbps';
    document.getElementById('realtime-upload').textContent = (metrics.actual_upload_mbps || 'N/A') + ' Mbps';
    
    document.getElementById('realtime-disk-read').textContent = (metrics.disk_read_mb_s || 'N/A') + ' MB/s';
    document.getElementById('realtime-disk-write').textContent = (metrics.disk_write_mb_s || 'N/A') + ' MB/s';
    
    document.getElementById('realtime-battery').textContent = (metrics.battery_percent !== undefined ? metrics.battery_percent : 'N/A') + '%';
    document.getElementById('realtime-power-plugged').textContent = metrics.power_plugged !== undefined ? (metrics.power_plugged ? 'Yes' : 'No') : 'N/A';
}

// Fetch and populate real-time metrics for the third tab
async function fetchRealtimeMetrics() {
    try {
        const metricsRes = await fetch('http://localhost:5000/api/network-metrics');
        const metrics = await metricsRes.json();
        populateRealtimeMetrics(metrics);
    } catch (e) {
        console.error('Error fetching real-time metrics:', e);
    }
}