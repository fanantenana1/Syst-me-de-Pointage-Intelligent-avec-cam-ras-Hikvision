import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
import json

class HikvisionPeopleManager:
    """
    Classe pour gérer les employés/personnes dans le système de contrôle d'accès Hikvision
    Compatible avec différents modèles via analyse des capabilities
    """
    
    def __init__(self, ip: str, username: str, password: str, port: int = 80):
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.base_url = f"http://{ip}:{port}/ISAPI"
        self.auth = HTTPDigestAuth(username, password)
        
    def get_capabilities(self) -> Dict:
        """Récupère les capacités du dispositif"""
        try:
            url = f"{self.base_url}/AccessControl/UserInfo/capabilities"
            response = requests.get(url, auth=self.auth, timeout=10)
            
            if response.status_code == 200:
                print("[INFO] Capabilities XML:")
                print(response.text[:500])
                return {'xml': response.text, 'available': True}
            return {'available': False}
        except Exception as e:
            print(f"Erreur capabilities: {e}")
            return {'available': False}
    
    def discover_api_structure(self) -> Dict[str, bool]:
        """Découvre la structure de l'API disponible"""
        endpoints_to_test = [
            # Gestion des utilisateurs
            '/ISAPI/AccessControl/UserInfo/Search',
            '/ISAPI/AccessControl/UserInfo/Record',
            '/ISAPI/AccessControl/UserInfo/Detail',
            '/ISAPI/AccessControl/UserInfoRecord',
            
            # Contrôle d'accès
            '/ISAPI/AccessControl/UserInfoEx/Search',
            '/ISAPI/AccessControl/UserInfoEx/Record',
            
            # Gestion des cartes
            '/ISAPI/AccessControl/CardInfo/Search',
            '/ISAPI/AccessControl/CardInfo/Record',
            
            # Événements
            '/ISAPI/AccessControl/AcsEvent',
            '/ISAPI/Event/notification/httpHosts',
            
            # Smart PSS / iVMS
            '/ISAPI/ContentMgmt/PersonInfo/capabilities',
            '/ISAPI/Intelligent/FDLib/capabilities',
        ]
        
        results = {}
        print("\n[DECOUVERTE DE L'API]")
        print("-" * 80)
        
        for endpoint in endpoints_to_test:
            url = f"http://{self.ip}:{self.port}{endpoint}"
            try:
                response = requests.get(url, auth=self.auth, timeout=3)
                available = response.status_code in [200, 401]  # 401 = besoin d'auth mais existe
                if available:
                    results[endpoint] = True
                    print(f"[OK] {endpoint}")
            except:
                pass
        
        print("-" * 80)
        print(f"[INFO] {len(results)} endpoints disponibles")
        return results
    
    def get_people_via_cgi(self) -> List[Dict]:
        """Essaie d'utiliser l'ancienne API CGI"""
        try:
            # Certains dispositifs utilisent CGI au lieu d'ISAPI
            url = f"http://{self.ip}:{self.port}/cgi-bin/AccessUser.cgi?action=list"
            response = requests.get(url, auth=self.auth, timeout=10)
            
            if response.status_code == 200:
                print("[OK] API CGI disponible")
                return self._parse_cgi_response(response.text)
            return []
        except Exception as e:
            print(f"[INFO] CGI non disponible: {e}")
            return []
    
    def _parse_cgi_response(self, text: str) -> List[Dict]:
        """Parse la réponse CGI"""
        people = []
        try:
            lines = text.strip().split('\n')
            for line in lines:
                if '=' in line:
                    parts = line.split('=')
                    if len(parts) == 2:
                        people.append({'data': line})
        except:
            pass
        return people
    
    def get_system_info(self) -> Dict:
        """Récupère les informations système"""
        try:
            url = f"{self.base_url}/System/deviceInfo"
            response = requests.get(url, auth=self.auth, timeout=10)
            
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                info = {}
                for child in root:
                    tag = child.tag.split('}')[-1]
                    info[tag] = child.text
                return info
            return {}
        except Exception as e:
            print(f"Erreur system info: {e}")
            return {}
    
    def try_all_methods(self) -> List[Dict]:
        """Essaie toutes les méthodes possibles pour récupérer les personnes"""
        
        methods = [
            ('ISAPI/AccessControl/UserInfo/Search POST', self._method1),
            ('ISAPI/AccessControl/UserInfo/Record GET', self._method2),
            ('ISAPI/AccessControl/UserInfoEx/Search POST', self._method3),
            ('ISAPI/ContentMgmt/PersonInfo/Search POST', self._method4),
            ('CGI API', self.get_people_via_cgi),
        ]
        
        for method_name, method_func in methods:
            print(f"\n[ESSAI] {method_name}")
            try:
                result = method_func()
                if result:
                    print(f"[SUCCESS] {method_name} fonctionne!")
                    return result
            except Exception as e:
                print(f"[ECHEC] {str(e)[:50]}")
        
        return []
    
    def _method1(self) -> List[Dict]:
        """UserInfo/Search avec POST - DS-K1T343EFWX compatible (JSON)"""
        # Le DS-K1T343EFWX accepte max 30 résultats par requête et veut du JSON
        all_people = []
        position = 0
        
        while True:
            search_data = {
                "UserInfoSearchCond": {
                    "searchID": "1",
                    "searchResultPosition": position,
                    "maxResults": 30
                }
            }
            
            url = f"{self.base_url}/AccessControl/UserInfo/Search?format=json"
            headers = {'Content-Type': 'application/json'}
            
            print(f"[DEBUG] Envoi requete position={position}")
            print(f"[DEBUG] URL: {url}")
            print(f"[DEBUG] JSON: {json.dumps(search_data, indent=2)}")
            
            response = requests.post(url, json=search_data, auth=self.auth, headers=headers, timeout=10)
            
            print(f"[DEBUG] Status: {response.status_code}")
            print(f"[DEBUG] Response: {response.text[:500]}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"[DEBUG] JSON parse OK")
                    
                    # Extraire les UserInfo
                    people = []
                    if 'UserInfoSearch' in data:
                        user_info_list = data['UserInfoSearch'].get('UserInfo', [])
                        if isinstance(user_info_list, dict):
                            people = [user_info_list]
                        elif isinstance(user_info_list, list):
                            people = user_info_list
                    
                    print(f"[DEBUG] Trouve {len(people)} personnes")
                    
                    if not people:
                        break
                    
                    all_people.extend(people)
                    position += len(people)
                    
                    # Si on a reçu moins de 30, c'est la dernière page
                    if len(people) < 30:
                        break
                        
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] Erreur JSON decode: {e}")
                    break
            else:
                if position == 0:
                    raise Exception(f"Status {response.status_code}: {response.text[:200]}")
                break
        
        return all_people
    
    def _method2(self) -> List[Dict]:
        """UserInfo/Record avec GET"""
        url = f"{self.base_url}/AccessControl/UserInfo/Record?format=json"
        response = requests.get(url, auth=self.auth, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'UserInfo' in data:
                return data['UserInfo'] if isinstance(data['UserInfo'], list) else [data['UserInfo']]
        raise Exception(f"Status {response.status_code}")
    
    def _method3(self) -> List[Dict]:
        """UserInfoEx/Search avec POST"""
        search_xml = """<?xml version="1.0" encoding="UTF-8"?>
<UserInfoExSearchCond>
    <searchID>1</searchID>
    <maxResults>1000</maxResults>
    <searchResultPosition>0</searchResultPosition>
</UserInfoExSearchCond>"""
        
        url = f"{self.base_url}/AccessControl/UserInfoEx/Search"
        headers = {'Content-Type': 'application/xml'}
        response = requests.post(url, data=search_xml, auth=self.auth, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return self._parse_people_xml(response.text)
        else:
            raise Exception(f"Status {response.status_code}")
    
    def _method4(self) -> List[Dict]:
        """ContentMgmt/PersonInfo/Search"""
        search_xml = """<?xml version="1.0" encoding="UTF-8"?>
<PersonInfoSearchCond>
    <searchID>1</searchID>
    <maxResults>1000</maxResults>
    <searchResultPosition>0</searchResultPosition>
</PersonInfoSearchCond>"""
        
        url = f"{self.base_url}/ContentMgmt/PersonInfo/Search"
        headers = {'Content-Type': 'application/xml'}
        response = requests.post(url, data=search_xml, auth=self.auth, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return self._parse_people_xml(response.text)
        else:
            raise Exception(f"Status {response.status_code}")
    
    def _parse_people_xml(self, xml_text: str) -> List[Dict]:
        """Parse la réponse XML du DS-K1T343EFWX"""
        people = []
        try:
            root = ET.fromstring(xml_text)
            
            # Pour le DS-K1T343EFWX, chercher UserInfoSearch/UserInfo
            search_result = root.find('.//{*}UserInfoSearch')
            if search_result is not None:
                for user_info in search_result.findall('.//{*}UserInfo'):
                    person = self._parse_user_info_element(user_info)
                    if person:
                        people.append(person)
            
            # Essayer aussi directement les UserInfo
            if not people:
                for user_info in root.findall('.//{*}UserInfo'):
                    person = self._parse_user_info_element(user_info)
                    if person:
                        people.append(person)
                        
        except Exception as e:
            print(f"Erreur parsing: {e}")
        
        return people
    
    def _parse_user_info_element(self, user_info) -> Dict:
        """Parse un élément UserInfo"""
        person = {}
        for child in user_info:
            tag = child.tag.split('}')[-1]
            if len(child) > 0:
                person[tag] = {}
                for subchild in child:
                    subtag = subchild.tag.split('}')[-1]
                    person[tag][subtag] = subchild.text
            else:
                person[tag] = child.text
        return person
    
    def print_people_table(self, people: List[Dict]):
        """Affiche les personnes"""
        if not people:
            print("Aucune personne trouvee")
            return
        
        print(f"\n{'ID':<10} {'Nom':<20} {'Informations'}")
        print("-" * 60)
        
        for person in people:
            emp_id = person.get('employeeNo', person.get('ID', 'N/A'))
            name = person.get('name', person.get('personName', 'N/A'))
            extra = f"Type: {person.get('userType', 'N/A')}"
            print(f"{emp_id:<10} {name:<20} {extra}")


# ====== PROGRAMME PRINCIPAL ======
if __name__ == "__main__":
    DEVICE_IP = "192.168.101.24"
    ADMIN_USER = "admin"
    ADMIN_PASS = "Eni20230"
    
    manager = HikvisionPeopleManager(DEVICE_IP, ADMIN_USER, ADMIN_PASS)
    
    print("=" * 80)
    print("DIAGNOSTIC API HIKVISION")
    print("=" * 80)
    
    # 1. Info système
    print("\n[1. INFORMATIONS SYSTEME]")
    print("-" * 80)
    system_info = manager.get_system_info()
    if system_info:
        for key, value in system_info.items():
            print(f"{key:20}: {value}")
    else:
        print("Non disponible")
    
    # 2. Capabilities
    print("\n[2. CAPABILITIES]")
    print("-" * 80)
    caps = manager.get_capabilities()
    
    # 3. Découverte API
    print("\n[3. ENDPOINTS DISPONIBLES]")
    available_endpoints = manager.discover_api_structure()
    
    # 4. Essayer toutes les méthodes
    print("\n[4. RECUPERATION DES PERSONNES]")
    print("=" * 80)
    people = manager.try_all_methods()
    
    if people:
        print(f"\n[SUCCESS] {len(people)} personnes trouvees!")
        manager.print_people_table(people)
        
        # Afficher le détail de la première personne
        print("\n[DETAILS PREMIERE PERSONNE]")
        print("-" * 80)
        print(json.dumps(people[0], indent=2, ensure_ascii=False))
        
        # Export
        with open("hikvision_backup.json", 'w', encoding='utf-8') as f:
            json.dump(people, f, indent=2, ensure_ascii=False)
        print("\n[OK] Donnees exportees vers hikvision_backup.json")
        
    else:
        print("\n[ECHEC] Impossible de recuperer les personnes avec les methodes testees")
        print("\nVotre dispositif utilise peut-etre une API personnalisee.")
        print("Verifiez la documentation de votre modele specifique.")
    
    print("\n" + "=" * 80)
    print("Diagnostic termine")
    print("=" * 80)
