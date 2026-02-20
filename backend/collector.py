# backend/collector.py - Full Windows-focused system collector
# Pushes high-frequency metrics, handles on-demand speed tests, stores to Firestore
# CPU/GPU temps removed, network speeds corrected using scaling factor

import firebase_admin
from firebase_admin import credentials, firestore
import psutil
import subprocess
import os
import time
from datetime import datetime, timedelta
import platform
import re
import requests
import speedtest
import socket
# ================== CONFIGURATION ==================
SERVICE_ACCOUNT_KEY_PATH = 'intelligent-system-monitor-firebase-adminsdk-fbsvc-75c6041d28.json'

MONITORED_DEVICES = [
    {"device_id": "server_001", "ip_address": "127.0.0.1", "type": "local_hardware"}
]

SPEED_SCALING_FACTOR = 0.5
PUBLIC_IP_CACHE_TTL = 3600  # seconds

# ================== FIREBASE INIT ==================
try:
    try:
        app = firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        app = firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Admin SDK initialized successfully.")
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")
    exit()

# ================== GLOBAL STATE ==================
_prev_net_io = None
_prev_net_time = None
_prev_disk_io = None
_prev_disk_time = None
_public_ip_cache = {"value": None, "timestamp": None}

# ================== UTILITY FUNCTIONS ==================

def run_wmic_command(parts, parse_key='Name'):
    if os.name != 'nt':
        return "N/A (Non-Windows)"
    try:
        cmd = ['wmic'] + parts + ['get', parse_key, '/value']
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            match = re.search(f'{re.escape(parse_key)}=(.*)', res.stdout, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "N/A"
    except Exception:
        return "N/A"

def run_nvidia_smi(query):
    try:
        cmd = ['nvidia-smi', f'--query-gpu={query}', '--format=csv,noheader,nounits']
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except Exception:
        return "N/A"

def get_ping_latency(ip):
    try:
        count = '1'
        cmd = ['ping', '-n', count, '-w', '1000', ip] if os.name=='nt' else ['ping','-c',count,'-W','1',ip]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            out = res.stdout
            if os.name=='nt':
                match = re.search(r'Average = (\d+(?:\.\d+)?)ms', out)
                if match:
                    val = match.group(1)
                    return 0.05 if val in ['0','<1'] else float(val)
            else:
                match = re.search(r'min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/', out)
                if match:
                    return float(match.group(2))
        return None
    except Exception:
        return None

def get_latest_speed_test():
    try:
        # Always set region/country from ipinfo.io, ISP from org
        ipinfo = None
        try:
            res = requests.get("https://ipinfo.io/json", timeout=5)
            if res.status_code == 200:
                ipinfo = res.json()
        except Exception as e:
            print(f"❌ ipinfo.io fetch failed: {e}")
            ipinfo = None

        isp_name = ipinfo.get('org', 'N/A') if ipinfo else 'N/A'
        region = ipinfo.get('city', 'N/A') if ipinfo else 'Chennai'
        country = ipinfo.get('country', 'N/A') if ipinfo else 'India'

        latest = db.collection('network_tests')\
            .where('device_id', '==', MONITORED_DEVICES[0]['device_id'])\
            .order_by('timestamp', direction=firestore.Query.DESCENDING)\
            .limit(1).get()
        if latest and latest[0].to_dict().get('isp_name','N/A') not in ['N/A','FAILURE','Unknown ISP']:
            data = latest[0].to_dict()
            return {
                'download_speed_mbps': round(data.get('download_mbps',0.0)*SPEED_SCALING_FACTOR,2),
                'upload_speed_mbps': round(data.get('upload_mbps',0.0)*SPEED_SCALING_FACTOR,2),
                'isp_name': isp_name,
                'region': region,
                'country': country
            }
        # If no valid result, run a speed test live
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        dl = (st.download()/1024/1024)*8
        ul = (st.upload()/1024/1024)*8
        return {
            'download_speed_mbps': round(dl*SPEED_SCALING_FACTOR,2),
            'upload_speed_mbps': round(ul*SPEED_SCALING_FACTOR,2),
            'isp_name': isp_name,
            'region': region,
            'country': country
        }
    except Exception as e:
        print(f"❌ Live speed test failed: {e}")
        return {'download_speed_mbps':0.0,'upload_speed_mbps':0.0,'isp_name':'N/A','region':'N/A','country':'N/A'}

def collect_static_specs():
    specs = {}
    specs['device_model'] = run_wmic_command(['computersystem'], 'Model')
    specs['processor_model'] = run_wmic_command(['cpu'])
    specs['cpu_cores'] = psutil.cpu_count(logical=False)
    specs['cpu_threads'] = psutil.cpu_count(logical=True)
    specs['gpu_model'] = run_wmic_command(['path','Win32_VideoController'])
    try:
        vram = subprocess.run(['wmic','path','Win32_VideoController','get','AdapterRAM','/value'],
                              capture_output=True, text=True, timeout=5).stdout
        match = re.search(r'AdapterRAM=(.*)', vram)
        specs['gpu_total_memory_gb'] = round(int(match.group(1))/1024**3,2) if match else 0.0
    except Exception:
        specs['gpu_total_memory_gb'] = 0.0
    specs['ram_total_gb'] = round(psutil.virtual_memory().total/1024**3,2)

    net_addrs = psutil.net_if_addrs()
    primary_interface = next((n for n,a in net_addrs.items()
                              if not n.lower().startswith('lo') and
                              any(addr.family == socket.AF_INET for addr in a)), 'Unknown')
    specs['network_interface_name'] = primary_interface
    specs['private_ip_address'] = 'N/A'
    specs['mac_address'] = 'N/A'

    if primary_interface in net_addrs:
        for addr in net_addrs[primary_interface]:
            if addr.family == socket.AF_INET:
                specs['private_ip_address'] = addr.address
            elif addr.family == getattr(psutil, 'AF_LINK', 17) or getattr(addr, 'family', None) == getattr(socket, 'AF_LINK', 17):
                specs['mac_address'] = addr.address

    specs['cpu_tdp_watts'] = 65
    specs.update(get_os_bios_info())
    return specs
def _get_counter_deltas():
    global _prev_net_io,_prev_net_time,_prev_disk_io,_prev_disk_time
    now = time.time()
    net = psutil.net_io_counters()
    down_mbps=0.0; up_mbps=0.0
    if _prev_net_io and _prev_net_time:
        elapsed = now-_prev_net_time
        if elapsed>0:
            down_mbps = (((net.bytes_recv-_prev_net_io.bytes_recv)*8)/(elapsed*1024*1024))*SPEED_SCALING_FACTOR
            up_mbps = (((net.bytes_sent-_prev_net_io.bytes_sent)*8)/(elapsed*1024*1024))*SPEED_SCALING_FACTOR
            speed_data = get_latest_speed_test()
            down_mbps = min(down_mbps, speed_data['download_speed_mbps']*1.5)
            up_mbps = min(up_mbps, speed_data['upload_speed_mbps']*1.5)
    _prev_net_io=net; _prev_net_time=now
    disk=psutil.disk_io_counters(); read=0.0; write=0.0
    if _prev_disk_io and _prev_disk_time:
        elapsed=now-_prev_disk_time
        if elapsed>0:
            read=((disk.read_bytes-_prev_disk_io.read_bytes)/1024/1024)/elapsed
            write=((disk.write_bytes-_prev_disk_io.write_bytes)/1024/1024)/elapsed
    _prev_disk_io=disk; _prev_disk_time=now
    return round(down_mbps,2), round(up_mbps,2), round(read,2), round(write,2)

def get_battery_info():
    try:
        bat=psutil.sensors_battery()
        if bat: return round(bat.percent,1), bool(bat.power_plugged)
    except Exception: pass
    return None,None

def get_packet_loss_jitter(ip="8.8.8.8", count=5):
    try:
        cmd = ["ping","-n",str(count),ip] if os.name=='nt' else ["ping","-c",str(count),ip]
        res=subprocess.run(cmd,capture_output=True,text=True,timeout=6)
        out=res.stdout
        loss_pct=0.0
        match_loss=re.search(r'Lost = \d+ \((\d+)% loss\)',out)
        if match_loss: loss_pct=float(match_loss.group(1))
        else:
            match_unix=re.search(r'(\d+(?:\.\d+)?)% packet loss',out)
            if match_unix: loss_pct=float(match_unix.group(1))
        times=[float(m.group(1)) for m in re.finditer(r'time[=<]?(\d+)',out)]
        jitter = round(max(times)-min(times),2) if len(times)>=2 else 0.0
        return loss_pct,jitter
    except Exception: return 0.0,0.0

def get_public_ip_and_geo():
    global _public_ip_cache
    try:
        now=datetime.utcnow(); cached_ts=_public_ip_cache.get("timestamp")
        if cached_ts and (now-cached_ts).total_seconds()<PUBLIC_IP_CACHE_TTL:
            return _public_ip_cache.get("value",("N/A","N/A","N/A"))
        res=requests.get("https://ipinfo.io/json",timeout=5)
        if res.status_code==200:
            data=res.json()
            val=(data.get("ip","N/A"),data.get("city","N/A"),data.get("country","N/A"))
            _public_ip_cache["value"]=val; _public_ip_cache["timestamp"]=datetime.utcnow()
            return val
    except Exception: pass
    return "N/A","N/A","N/A"

def get_gpu_memory_usage_percent():
    try:
        used=run_nvidia_smi("memory.used")
        total=run_nvidia_smi("memory.total")
        if used!="N/A" and total!="N/A":
            used_f=float(used); total_f=float(total)
            if total_f>0: return round((used_f/total_f)*100,2)
    except Exception: pass
    return None

def get_wifi_info():
    if os.name!="nt": return "N/A",0,0
    try:
        out=subprocess.check_output(["netsh","wlan","show","interfaces"],text=True,timeout=5,stderr=subprocess.DEVNULL)
        ssid = re.search(r"\s+SSID\s*:\s*(.+)",out); ssid=ssid.group(1).strip() if ssid else "N/A"
        signal=re.search(r"\s+Signal\s*:\s*(\d+)%",out); signal=int(signal.group(1)) if signal else 0
        rate=re.search(r"\s+Receive rate \(Mbps\)\s*:\s*(\d+)",out)
        rate=int(rate.group(1)) if rate else 0
        return ssid,signal,rate
    except Exception: return "N/A",0,0

def get_os_bios_info():
    info={"os_name":platform.system(),"os_version":platform.platform(),"bios_vendor":"N/A","bios_version":"N/A"}
    if os.name=='nt':
        try:
            info["bios_vendor"]=run_wmic_command(["bios"],"Manufacturer")
            info["bios_version"]=run_wmic_command(["bios"],"SMBIOSBIOSVersion")
        except Exception: pass
    return info

# ================== CORE METRICS ==================
def get_system_metrics(interval_s=1.0):
    results={}
    try: results['cpu_load_percent']=psutil.cpu_percent(interval=interval_s)
    except Exception: results['cpu_load_percent']=0.0
    try: results['ram_used_percent']=psutil.virtual_memory().percent
    except Exception: results['ram_used_percent']=0.0
    try:
        path = os.path.splitdrive(os.path.abspath(__file__))[0]+'\\' if os.name=='nt' else '/'
        results['disk_usage_percent']=psutil.disk_usage(path).percent
    except Exception: results['disk_usage_percent']=0.0
    gpu_raw=run_nvidia_smi('utilization.gpu')
    try: results['gpu_utilization_percent']=float(gpu_raw) if gpu_raw!="N/A" else round(results['cpu_load_percent']*0.6,1)
    except Exception: results['gpu_utilization_percent']=0.0
    speed_data=get_latest_speed_test()
    results['speedtest_download_mbps']=speed_data.get('download_speed_mbps',0.0)
    results['speedtest_upload_mbps']=speed_data.get('upload_speed_mbps',0.0)
    results['isp_name']=speed_data.get('isp_name','N/A')
    results['region']=speed_data.get('region','N/A')
    results['country']=speed_data.get('country','N/A')
    down,up,read,write=_get_counter_deltas()
    results['actual_download_mbps']=down; results['actual_upload_mbps']=up
    results['disk_read_mb_s']=read; results['disk_write_mb_s']=write
    bat_pct,plugged=get_battery_info()
    results['battery_percent']=bat_pct; results['power_plugged']=plugged
    loss,jitter=get_packet_loss_jitter()
    results['packet_loss_percent']=loss; results['network_jitter_ms']=jitter
    pub_ip,city,country=get_public_ip_and_geo()
    results['public_ip']=pub_ip; results['geo_city']=city; results['geo_country']=country
    gpu_mem=get_gpu_memory_usage_percent()
    results['gpu_memory_used_percent']=gpu_mem
    ssid,signal,link=get_wifi_info()
    results['wifi_ssid']=ssid; results['wifi_signal_percent']=signal; results['wifi_link_speed_mbps']=link
    results['collected_at']=datetime.utcnow()
    return results

# ================== SPEEDTEST ==================
def run_full_speed_test_logic(device_id):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Running full speed test...")
    try:
        st=speedtest.Speedtest()
        st.get_best_server()
        isp=st.results.client.get('isp','Unknown ISP') if st.results else 'Unknown ISP'
        dl=(st.download()/1024/1024)*8
        ul=(st.upload()/1024/1024)*8
        data={'download_mbps':round(dl,2),'upload_mbps':round(ul,2),
              'ping_latency_ms':getattr(st.results,'ping',None) if hasattr(st,'results') else None,
              'server_name':st.results.server.get('name') if hasattr(st,'results') and st.results.server else 'Unknown',
              'isp_name':isp}
    except Exception as e:
        print(f"❌ Speed Test Failed: {e}")
        data={'download_mbps':0.0,'upload_mbps':0.0,'ping_latency_ms':9999.0,'server_name':'FAILURE','isp_name':'FAILURE'}
    try:
        db.collection('network_tests').add({
            'device_id':device_id,
            'download_mbps':data['download_mbps'],
            'upload_mbps':data['upload_mbps'],
            'ping_latency_ms':data['ping_latency_ms'],
            'test_server':data['server_name'],
            'isp_name':data['isp_name'],
            'timestamp':datetime.now()
        })
        db.collection('commands').document('speed_test_trigger').set({'status':'complete','timestamp':datetime.now()},merge=True)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Speed Test Logged.")
    except Exception as e:
        print(f"❌ Database Push Failed after Speed Test: {e}")

def check_and_run_command():
    try:
        doc=db.collection('commands').document('speed_test_trigger').get()
        if doc.exists and doc.to_dict().get('status')=='pending':
            db.collection('commands').document('speed_test_trigger').set({'status':'running','timestamp':datetime.now()},merge=True)
            run_full_speed_test_logic(MONITORED_DEVICES[0]['device_id'])
            return True
    except Exception as e:
        print(f"❌ Error checking command: {e}")
    return False

# ================== MAIN PUSH LOOP ==================
def push_metrics_to_firestore():
    specs_ref=db.collection('devices').document(MONITORED_DEVICES[0]['device_id'])
    try:
        if not specs_ref.get().exists:
            specs_ref.set(collect_static_specs())
            print(f"⚙️ Pushed static specs.")
    except Exception as e: print(f"❌ Failed to push specs: {e}")
    # Only push device specs if not present
    # No metrics are pushed to Firestore. Metrics are served live via API only.


# === Flask API for frontend integration ===
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/api/device-specs')
def api_device_specs():
    specs = collect_static_specs()
    bat_pct, plugged = get_battery_info()
    
    # ADDED: Get WiFi and GPU memory info here, as it's semi-static or useful for the specs view
    specs['wifi_ssid'], specs['wifi_signal_percent'], specs['wifi_link_speed_mbps'] = get_wifi_info()
    specs['gpu_memory_used_percent'] = get_gpu_memory_usage_percent()

    specs['battery_percent'] = bat_pct
    specs['power_plugged'] = plugged
    
    # Ensure all required static/semi-static fields are present for app.js
    # Only pop the internal device_id
    specs.pop('device_id', None) 
    return jsonify(specs)

# New endpoint: trigger speed test manually
@app.route('/api/run-speedtest', methods=['POST'])
def api_run_speedtest():
    try:
        run_full_speed_test_logic(MONITORED_DEVICES[0]['device_id'])
        return jsonify({'status': 'success', 'message': 'Speed test triggered.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/network-metrics')
def api_network_metrics():
    # Serve live metrics directly
    try:
        # Pass a minimal interval to get the most recent cached/computed values
        metrics = get_system_metrics(interval_s=0.1) 
        return jsonify(metrics)
    except Exception as e:
        print(f"❌ Error fetching live metrics: {e}")
        return jsonify({"error": "No metrics found"})

if __name__=="__main__":
    import threading
    def metrics_loop():
        while True:
            try:
                push_metrics_to_firestore()
                time.sleep(5)
            except KeyboardInterrupt:
                print("🛑 Stopped by user.")
                break
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                time.sleep(5)

    t = threading.Thread(target=metrics_loop, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5000, debug=True)