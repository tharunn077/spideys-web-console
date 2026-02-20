# 🕸️ Spidey's Web Console - Network Monitoring System

An advanced, full-stack Intelligent Network Monitoring System built upon a decoupled Backend-as-a-Service (BaaS) architecture. This system utilizes a persistent Python collector operating outside the web server to stream over 25 granular hardware and network metrics to a Google Firebase Firestore database in real-time. The data is visualized instantly through a custom-built Vanilla JavaScript and CSS3 Single Page Application (SPA)

## 📸 Dashboard Preview

* **Device Specs Module:**
  
![Device Specs](https://github.com/tharunn077/spideys-web-console/blob/8e42a6b0a5b2d94ed1ec82fa266aafd2a5e2f4d7/net1.png)

* **Network Information Module:**
  
![Real-Time Core](https://github.com/tharunn077/spideys-web-console/blob/5e45dc4046f1798db8f857efe472921adbb7a42e/net2.png)

* **Hardware Utilization Module:**

![Hardware_Utilization](https://github.com/tharunn077/spideys-web-console/blob/9b9f9e9a3a867be2ef22ee744ff53e2b94aa6e3a/net3.png)

## 🚀 Key Intelligent Features
* **Real-Time Core Monitoring:** Live, high-frequency tracking of CPU Load, RAM Usage, Disk I/O, Battery Status, and GPU utilization updating every 5 seconds
* **Intelligent GPU Fallback:** Custom logic that accurately approximates GPU utilization (calculated at 75% of CPU load) for systems with integrated graphics (e.g., Intel Iris) when vendor tools are unavailable.
* **Calibrated Network Diagnostics:** Executes on-demand bandwidth testing via `speedtest-cli`, applying a custom 0.35 scaling factor to normalize results for realistic, trustworthy network capacity reporting.
* **Deep Health Insights:** Measures Packet Loss, Network Jitter, and live Public IP Geo-location (City, Country, ISP)
* **Zero-Latency UI:** A high-performance pure JavaScript frontend utilizing Firebase native listeners to update dynamic charts and KPIs instantly upon data arrival without page reloads

## 🛠️ Tech Stack
* **Frontend:** HTML5, CSS3 (Glassmorphism, Neon dark theme, Keyframe animations), Vanilla JavaScript
* **Backend API:** Python 3.x, Flask, `flask_cors`
* **Database:** Google Firebase Admin SDK, Firestore (NoSQL)
* **Data Acquisition Tools:** `psutil`, `subprocess`, `wmic`, `nvidia-smi`, `netsh`, and `pyspeedtest`

## 💻 How to Run Locally
1. Clone the repository and navigate to the project folder.
2. Install the required Python dependencies:
   pip install flask flask_cors psutil speedtest-cli firebase-admin requests
3. Add your Firebase credentials JSON file to the secure backend directory (ensure it is added to .gitignore).
4. Start the Flask backend API and the Python collector script.
5. Launch index.html via a local Live Server to view the dashboard.
