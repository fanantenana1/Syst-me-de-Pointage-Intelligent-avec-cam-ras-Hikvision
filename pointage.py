import requests
from requests.auth import HTTPDigestAuth
import json
import csv
from datetime import datetime
from collections import Counter
import xml.etree.ElementTree as ET
from typing import List, Dict
from pathlib import Path

# =================== CONFIGURATION ===================
HIKVISION_IP = "192.168.101.24"
USERNAME = "admin"
PASSWORD = "Eni20230"

auth = HTTPDigestAuth(USERNAME, PASSWORD)
base_url = f"http://{HIKVISION_IP}/ISAPI"

# =================== ÉVÉNEMENTS DE PRÉSENCE ===================
PRESENCE_EVENTS = {
    # Authentifications réussies
    (5, 1): ("Carte", True),
    (5, 2): ("Empreinte", True),
    (5, 3): ("Facial", True),
    (5, 4): ("Code PIN", True),
    (5, 5): ("Combiné", True),
    (5, 21): ("Ouverture porte", True),
    (5, 38): ("Sortie validée", True),
    (5, 39): ("Entrée validée", True),
    (5, 104): ("Multi-vérification", True),
    
    # Authentifications échouées
    (5, 22): ("Carte", False),
    (5, 75): ("Non spécifié", False),
    (5, 76): ("Carte", False),
    (5, 77): ("Carte", False),
    (5, 78): ("Carte", False),
    (5, 79): ("Code PIN", False),
}

def get_presence_info(major, minor):
    """Retourne (méthode, validé) ou None"""
    return PRESENCE_EVENTS.get((major, minor))

def get_period_of_day(hour):
    """Détermine la période de la journée"""
    if 6 <= hour < 12:
        return "Matin"
    elif 12 <= hour < 18:
        return "Après-midi"
    elif 18 <= hour < 22:
        return "Soir"
    else:
        return "Nuit"

# =================== RÉCUPÉRATION UTILISATEURS ===================
def get_all_users():
    """Récupère tous les utilisateurs du système Hikvision"""
    print("\n" + "="*100)
    print("📋 RÉCUPÉRATION DE LA LISTE DES UTILISATEURS")
    print("="*100)
    
    all_users = []
    position = 0
    
    while True:
        search_data = {
            "UserInfoSearchCond": {
                "searchID": "1",
                "searchResultPosition": position,
                "maxResults": 30
            }
        }
        
        url = f"{base_url}/AccessControl/UserInfo/Search?format=json"
        headers = {'Content-Type': 'application/json'}
        
        try:
            response = requests.post(url, json=search_data, auth=auth, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                people = []
                if 'UserInfoSearch' in data:
                    user_info_list = data['UserInfoSearch'].get('UserInfo', [])
                    if isinstance(user_info_list, dict):
                        people = [user_info_list]
                    elif isinstance(user_info_list, list):
                        people = user_info_list
                
                if not people:
                    break
                
                all_users.extend(people)
                position += len(people)
                
                print(f"✅ Récupéré {len(all_users)} utilisateurs...")
                
                if len(people) < 30:
                    break
            else:
                if position == 0:
                    print(f"❌ Erreur HTTP {response.status_code}")
                break
                
        except Exception as e:
            print(f"❌ Erreur: {e}")
            break
    
    print(f"\n🎉 Total: {len(all_users)} utilisateurs récupérés")
    return all_users

# =================== RÉCUPÉRATION ÉVÉNEMENTS ===================
def get_all_events():
    """Récupère tous les événements de présence"""
    print("\n" + "="*100)
    print("🎯 RÉCUPÉRATION DES ÉVÉNEMENTS DE PRÉSENCE")
    print("="*100)
    
    all_presences = []
    position = 0
    max_per_request = 30
    batch_number = 1
    total_expected = None
    
    while True:
        json_payload = {
            "ACSEventCond": {
                "searchID": "1",
                "searchResultPosition": position,
                "maxResults": max_per_request,
                "major": 5,
                "minor": 0
            }
        }
        
        try:
            response = requests.post(
                f"{base_url}/AccessControl/ACSEvent?format=json",
                json=json_payload,
                auth=auth,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if total_expected is None:
                    total_expected = data.get("AcsEvent", {}).get("totalMatches", 0)
                    print(f"📊 Total d'événements: {total_expected}")
                    print("="*100)
                
                info_list = data.get("AcsEvent", {}).get("InfoList", [])
                num_matches = data.get("AcsEvent", {}).get("numOfMatches", 0)
                response_status = data.get("AcsEvent", {}).get("responseStatusStrg", "")
                
                if info_list:
                    for evt in info_list:
                        major = evt.get("major", 0)
                        minor = evt.get("minor", 0)
                        presence_info = get_presence_info(major, minor)
                        
                        if presence_info:
                            method, validated = presence_info
                            datetime_str = evt.get("time", "-")
                            
                            # Parser la date/heure
                            date_val = "-"
                            time_val = "-"
                            day_name = "-"
                            period = "-"
                            
                            if datetime_str != "-":
                                try:
                                    dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                                    date_val = dt.strftime("%Y-%m-%d")
                                    time_val = dt.strftime("%H:%M:%S")
                                    day_name = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][dt.weekday()]
                                    period = get_period_of_day(dt.hour)
                                except:
                                    pass
                            
                            all_presences.append({
                                "employee_id": evt.get("employeeNoString", evt.get("employeeNo", "-")),
                                "name": evt.get("name", "-"),
                                "method": method,
                                "validated": "Validé" if validated else "Refusé",
                                "date": date_val,
                                "time": time_val,
                                "day": day_name,
                                "period": period,
                                "datetime": datetime_str,
                                "card_no": evt.get("cardNo", "-"),
                                "door_no": evt.get("doorNo", "-"),
                                "major": major,
                                "minor": minor
                            })
                    
                    progress = position + num_matches
                    percent = (progress / total_expected * 100) if total_expected else 0
                    print(f"✅ Lot {batch_number}: {num_matches} événements | Présences: {len(all_presences)} | Progression: {progress}/{total_expected} ({percent:.1f}%)")
                    
                    if response_status != "MORE" or num_matches < max_per_request:
                        print("\n🎉 Récupération terminée!")
                        break
                    
                    position += max_per_request
                    batch_number += 1
                else:
                    break
            else:
                print(f"❌ Erreur HTTP {response.status_code}")
                break
        
        except Exception as e:
            print(f"❌ Erreur: {e}")
            break
    
    return all_presences

# =================== SAUVEGARDE CSV ===================
def save_to_csv(presences, filename="presences_completes.csv"):
    """Sauvegarde les présences dans un fichier CSV"""
    if not presences:
        print("❌ Aucune présence à sauvegarder")
        return
    
    try:
        with open(filename, "w", newline='', encoding='utf-8-sig') as f:
            fieldnames = ['employee_id', 'name', 'method', 'validated', 'date', 'time', 'day', 'period', 'datetime', 'card_no', 'door_no', 'major', 'minor']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(presences)
        print(f"✅ Export CSV: {filename}")
        return True
    except Exception as e:
        print(f"❌ Erreur CSV: {e}")
        return False

# =================== FILTRAGE ET AFFICHAGE ===================
def filter_and_display(presences, users):
    """Filtre et affiche les présences des utilisateurs trouvés"""
    print("\n" + "="*100)
    print("🔍 FILTRAGE DES PRÉSENCES PAR UTILISATEUR")
    print("="*100)
    
    # Créer un dictionnaire des utilisateurs par ID et nom
    user_dict_by_id = {}
    user_dict_by_name = {}
    
    for user in users:
        emp_id = user.get('employeeNo', '')
        name = user.get('name', '')
        
        if emp_id:
            user_dict_by_id[str(emp_id)] = user
        if name:
            user_dict_by_name[name.upper()] = user
    
    print(f"\n📋 Utilisateurs dans la base de données: {len(users)}")
    print(f"   - Par ID: {len(user_dict_by_id)} utilisateurs")
    print(f"   - Par nom: {len(user_dict_by_name)} noms uniques")
    
    # Filtrer les présences
    filtered_presences = []
    unique_found_ids = set()
    unique_found_names = set()
    
    for presence in presences:
        emp_id = str(presence.get('employee_id', '-'))
        name = presence.get('name', '-')
        
        # Vérifier si l'utilisateur existe dans la base
        found = False
        
        if emp_id != '-' and emp_id in user_dict_by_id:
            found = True
            unique_found_ids.add(emp_id)
        
        if name != '-' and name.upper() in user_dict_by_name:
            found = True
            unique_found_names.add(name.upper())
        
        if found:
            filtered_presences.append(presence)
    
    print(f"\n✅ Présences filtrées: {len(filtered_presences)} sur {len(presences)}")
    print(f"   - {len(unique_found_ids)} utilisateurs uniques (par ID)")
    print(f"   - {len(unique_found_names)} utilisateurs uniques (par nom)")
    
    # Afficher le tableau
    if filtered_presences:
        print("\n" + "="*150)
        print("📊 TABLEAU DES PRÉSENCES FILTRÉES")
        print("="*150)
        print(f"{'ID':<10} {'Nom':<15} {'Type':<20} {'Statut':<10} {'Date':<12} {'Heure':<10} {'Jour':<10} {'Période':<12} {'Code':<10}")
        print("="*150)
        
        for p in filtered_presences:
            emp_id = str(p['employee_id'])[:9]
            name = str(p['name'])[:14]
            method = str(p['method'])[:19]
            validated = str(p['validated'])[:9]
            date = str(p['date'])[:11]
            time = str(p['time'])[:9]
            day = str(p['day'])[:9]
            period = str(p['period'])[:11]
            code = f"({p['major']},{p['minor']})"
            
            print(f"{emp_id:<10} {name:<15} {method:<20} {validated:<10} {date:<12} {time:<10} {day:<10} {period:<12} {code:<10}")
        
        # Sauvegarder les résultats filtrés
        save_to_csv(filtered_presences, "presences_filtrees.csv")
        
        # Statistiques par utilisateur
        print("\n" + "="*100)
        print("📈 STATISTIQUES PAR UTILISATEUR")
        print("="*100)
        
        user_stats = {}
        for p in filtered_presences:
            key = f"{p['employee_id']} - {p['name']}"
            if key not in user_stats:
                user_stats[key] = {'total': 0, 'valide': 0, 'refuse': 0}
            
            user_stats[key]['total'] += 1
            if p['validated'] == 'Validé':
                user_stats[key]['valide'] += 1
            else:
                user_stats[key]['refuse'] += 1
        
        print(f"\n{'Utilisateur':<30} {'Total':<10} {'Validé':<10} {'Refusé':<10}")
        print("="*100)
        for user, stats in sorted(user_stats.items(), key=lambda x: x[1]['total'], reverse=True):
            print(f"{user:<30} {stats['total']:<10} {stats['valide']:<10} {stats['refuse']:<10}")
    
    return filtered_presences

# =================== PROGRAMME PRINCIPAL ===================
def main():
    print("="*100)
    print("🎯 SYSTÈME DE FILTRAGE DES PRÉSENCES HIKVISION")
    print("="*100)
    
    # 1. Récupérer tous les utilisateurs
    users = get_all_users()
    
    if not users:
        print("\n❌ Impossible de récupérer les utilisateurs. Vérifiez la connexion.")
        return
    
    # Afficher les utilisateurs
    print("\n" + "="*100)
    print("👥 LISTE DES UTILISATEURS ENREGISTRÉS")
    print("="*100)
    print(f"{'ID':<15} {'Nom':<25} {'Type':<15}")
    print("="*100)
    for user in users[:50]:  # Afficher les 50 premiers
        emp_id = str(user.get('employeeNo', '-'))[:14]
        name = str(user.get('name', '-'))[:24]
        user_type = str(user.get('userType', '-'))[:14]
        print(f"{emp_id:<15} {name:<25} {user_type:<15}")
    
    if len(users) > 50:
        print(f"... et {len(users) - 50} autres utilisateurs")
    
    # Sauvegarder les utilisateurs
    with open("users_list.json", "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
    print("\n✅ Liste des utilisateurs sauvegardée: users_list.json")
    
    # 2. Récupérer tous les événements
    presences = get_all_events()
    
    if not presences:
        print("\n❌ Aucun événement de présence trouvé.")
        return
    
    # 3. Sauvegarder tous les événements
    save_to_csv(presences)
    
    with open("presences_completes.json", "w", encoding="utf-8") as f:
        json.dump(presences, f, indent=2, ensure_ascii=False)
    print("✅ Présences complètes sauvegardées: presences_completes.json")
    
    # 4. Filtrer et afficher
    filtered = filter_and_display(presences, users)
    
    # 5. Résumé final
    print("\n" + "="*100)
    print("✅ TRAITEMENT TERMINÉ")
    print("="*100)
    print("\n📁 Fichiers générés:")
    print("   1. users_list.json          - Liste de tous les utilisateurs")
    print("   2. presences_completes.csv  - Tous les événements de présence")
    print("   3. presences_completes.json - Tous les événements (format JSON)")
    print("   4. presences_filtrees.csv   - Présences des utilisateurs enregistrés uniquement")
    print("\n💡 Les présences sont filtrées pour n'afficher que les utilisateurs présents dans la base de données!")

if __name__ == "__main__":
    main()