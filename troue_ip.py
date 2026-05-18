import socket
import requests
import netifaces
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import platform

class HikvisionFinder:
    """Classe pour scanner et trouver les appareils Hikvision sur le réseau"""
    
    def __init__(self):
        pass
        
    def get_local_network(self):
        """Détecte automatiquement le réseau local"""
        try:
            gateways = netifaces.gateways()
            default_gateway = gateways['default'][netifaces.AF_INET]
            interface = default_gateway[1]
            
            addrs = netifaces.ifaddresses(interface)
            ip_info = addrs[netifaces.AF_INET][0]
            ip_addr = ip_info['addr']
            netmask = ip_info['netmask']
            
            network = ipaddress.IPv4Network(f"{ip_addr}/{netmask}", strict=False)
            return str(network)
        except Exception:
            return "192.168.1.0/24"
    
    def ping_scan(self, target):
        """Scan par ping - NE NÉCESSITE PAS ROOT"""
        network = ipaddress.IPv4Network(target, strict=False)
        active_hosts = []
        
        def ping_host(ip):
            """Ping un hôte spécifique"""
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', '-W', '1', str(ip)]
            
            try:
                result = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2
                )
                if result.returncode == 0:
                    return {'ip': str(ip), 'mac': 'Unknown'}
            except:
                pass
            return None
        
        # Limiter le scan aux 254 premières IPs
        ips_to_scan = list(network.hosts())[:254]
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(ping_host, ip) for ip in ips_to_scan]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    active_hosts.append(result)
        
        return active_hosts
    
    def check_ports_fast(self, ip, ports=[80, 554, 8000]):
        """Vérification rapide des ports"""
        open_ports = []
        for port in ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            try:
                result = sock.connect_ex((str(ip), port))
                if result == 0:
                    open_ports.append(port)
                sock.close()
            except:
                pass
        return open_ports
    
    def check_http_banner(self, ip, timeout=1):
        """Vérifie la bannière HTTP pour Hikvision"""
        try:
            response = requests.get(
                f"http://{ip}", 
                timeout=timeout,
                allow_redirects=False,
                verify=False
            )
            content = response.text.lower()
            headers = str(response.headers).lower()
            keywords = ['hikvision', 'ipcamera', 'dvr', 'nvr', 'webs']
            return any(keyword in content or keyword in headers for keyword in keywords)
        except:
            return False
    
    def analyze_device(self, device):
        """Analyse un appareil pour déterminer s'il est Hikvision"""
        ip = device['ip']
        mac = device.get('mac', 'Unknown')
        
        confidence = 0
        reasons = []
        
        # Vérifier les ports
        ports = self.check_ports_fast(ip)
        
        if not ports:
            return None
        
        # Port RTSP (très caractéristique des caméras)
        if 554 in ports:
            confidence += 50
            reasons.append("Port RTSP 554")
        
        # Ports HTTP Hikvision typiques
        if 80 in ports:
            confidence += 20
            reasons.append("Port HTTP 80")
        
        if 8000 in ports:
            confidence += 30
            reasons.append("Port HTTP 8000")
        
        # Vérifier la bannière HTTP
        if 80 in ports or 8000 in ports:
            if self.check_http_banner(ip):
                confidence += 80
                reasons.append("Bannière Hikvision détectée")
        
        # Décision : considérer comme Hikvision si confidence >= 60
        if confidence >= 60:
            return {
                'ip': ip,
                'mac': mac,
                'ports': ports,
                'confidence': min(confidence, 100),
                'reasons': reasons,
                'model': 'Hikvision Device'
            }
        
        return None
    
    def scan_once(self, subnet):
        """Effectue un scan complet et retourne les appareils Hikvision trouvés"""
        print(f"🔍 Scanning network: {subnet}")
        
        # Utiliser ping au lieu d'ARP
        devices = self.ping_scan(subnet)
        
        print(f"📡 Found {len(devices)} active hosts")
        
        if not devices:
            return []
        
        hikvision_devices = []
        
        # Analyser chaque appareil trouvé
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(self.analyze_device, device): device for device in devices}
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                print(f"⏳ Analyzing devices: {completed}/{len(devices)}", end='\r')
                try:
                    result = future.result()
                    if result:
                        hikvision_devices.append(result)
                        print(f"\n✅ Found Hikvision: {result['ip']} ({result['confidence']}%)")
                except Exception as e:
                    pass
        
        print(f"\n🎯 Total Hikvision devices found: {len(hikvision_devices)}")
        return hikvision_devices
#sudo -E env "PATH=$PATH" python troue_ip.py
    