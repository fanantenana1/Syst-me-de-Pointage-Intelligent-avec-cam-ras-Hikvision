import requests
from requests.auth import HTTPDigestAuth
import json
import csv
from datetime import datetime
from collections import Counter

# =================== CONFIGURATION ===================
HIKVISION_IP = "192.168.101.24"
USERNAME = "admin"
PASSWORD = "Eni20230"

auth = HTTPDigestAuth(USERNAME, PASSWORD)
base_url = f"http://{HIKVISION_IP}/ISAPI"

print("="*100)
print("🎯 RÉCUPÉRATION DES PRÉSENCES HIKVISION - VERSION CORRIGÉE")
print("="*100)

# =================== ÉVÉNEMENTS DE PRÉSENCE ===================
# Liste COMPLÈTE basée sur la documentation Hikvision et vos données
PRESENCE_EVENTS = {
    # ===== AUTHENTIFICATIONS RÉUSSIES =====
    (5, 1): ("Carte", True),
    (5, 2): ("Empreinte", True),
    (5, 3): ("Facial", True),
    (5, 4): ("Code PIN", True),
    (5, 5): ("Combiné", True),
    
    # NOUVEAUX CODES TROUVÉS DANS VOS DONNÉES (authentifications réussies)
    (5, 21): ("Ouverture porte", True),      # Porte ouverte (accès autorisé)
    (5, 38): ("Sortie validée", True),       # Sortie autorisée
    (5, 39): ("Entrée validée", True),       # Entrée autorisée
    (5, 104): ("Multi-vérification", True),  # Authentification multi-facteurs
    
    # ===== AUTHENTIFICATIONS ÉCHOUÉES =====
    (5, 22): ("Carte", False),         # Pas de permission
    (5, 75): ("Non spécifié", False),  # Auth échouée
    (5, 76): ("Carte", False),         # Carte expirée
    (5, 77): ("Carte", False),         # Hors période
    (5, 78): ("Carte", False),         # Porte verrouillée
    (5, 79): ("Code PIN", False),      # Code incorrect
}

def get_presence_info(major, minor):
    """Retourne (méthode, validé) ou None si pas un événement de présence"""
    return PRESENCE_EVENTS.get((major, minor))

# =================== RÉCUPÉRATION ===================
all_presences = []
all_events_debug = []
position = 0
max_per_request = 30

print("\n📡 Récupération des événements...\n")

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
                print(f"📊 Total d'événements d'authentification : {total_expected}")
                print("="*100)
            
            info_list = data.get("AcsEvent", {}).get("InfoList", [])
            num_matches = data.get("AcsEvent", {}).get("numOfMatches", 0)
            response_status = data.get("AcsEvent", {}).get("responseStatusStrg", "")
            
            if info_list:
                for evt in info_list:
                    major = evt.get("major", 0)
                    minor = evt.get("minor", 0)
                    
                    all_events_debug.append({
                        "major": major,
                        "minor": minor,
                        "employee_id": evt.get("employeeNoString", evt.get("employeeNo", "-")),
                        "name": evt.get("name", "-"),
                        "datetime": evt.get("time", "-"),
                        "card_no": evt.get("cardNo", "-"),
                        "door_no": evt.get("doorNo", "-")
                    })
                    
                    presence_info = get_presence_info(major, minor)
                    
                    if presence_info:
                        method, validated = presence_info
                        all_presences.append({
                            "employee_id": evt.get("employeeNoString", evt.get("employeeNo", "-")),
                            "name": evt.get("name", "-"),
                            "method": method,
                            "validated": "✅ Validé" if validated else "❌ Refusé",
                            "datetime": evt.get("time", "-"),
                            "card_no": evt.get("cardNo", "-"),
                            "door_no": evt.get("doorNo", "-"),
                            "major": major,
                            "minor": minor
                        })
                
                progress = position + num_matches
                percent = (progress / total_expected * 100) if total_expected else 0
                print(f"✅ Lot {batch_number}: {num_matches} événements | Présences trouvées: {len(all_presences)} | Progression: {progress}/{total_expected} ({percent:.1f}%)")
                
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

# =================== DIAGNOSTIC ===================
print("\n" + "="*100)
print("🔍 DIAGNOSTIC DES CODES D'ÉVÉNEMENTS")
print("="*100)

code_counter = Counter()
for evt in all_events_debug:
    code_counter[(evt['major'], evt['minor'])] += 1

print("\n📋 Codes (major, minor) trouvés:")
print(f"{'Code':<20} {'Occurrences':<15} {'Type':<20} {'Statut'}")
print("="*100)

for (major, minor), count in sorted(code_counter.items(), key=lambda x: x[1], reverse=True):
    presence_info = get_presence_info(major, minor)
    if presence_info:
        method, validated = presence_info
        status = "✅ VALIDÉ" if validated else "❌ REFUSÉ"
        type_auth = method
    else:
        status = "⚠️  NON RECONNU"
        type_auth = "Inconnu"
    
    print(f"({major}, {minor}){' ':<13} {count:<15} {type_auth:<20} {status}")

# =================== RÉSULTATS ===================
print("\n" + "="*100)
print(f"🎉 TOTAL DES PRÉSENCES: {len(all_presences)}")
print("="*100)

if all_presences:
    # Sauvegarder en JSON
    with open("presences_completes.json", "w", encoding="utf-8") as f:
        json.dump(all_presences, f, indent=2, ensure_ascii=False)
    print("\n✅ Présences sauvegardées: presences_completes.json")
    
    # Sauvegarder debug
    with open("events_debug.json", "w", encoding="utf-8") as f:
        json.dump(all_events_debug, f, indent=2, ensure_ascii=False)
    print("✅ Debug sauvegardé: events_debug.json")
    
    # CSV
    try:
        with open("presences_completes.csv", "w", newline='', encoding='utf-8-sig') as f:
            fieldnames = ['employee_id', 'name', 'method', 'validated', 'datetime', 'card_no', 'door_no', 'major', 'minor']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_presences)
        print("✅ Export CSV: presences_completes.csv")
    except Exception as e:
        print(f"❌ Erreur CSV: {e}")
    
    # Aperçu des dernières présences VALIDÉES
    validated_presences = [p for p in all_presences if "Validé" in p['validated']]
    
    if validated_presences:
        print("\n" + "="*100)
        print(f"📋 DERNIÈRES PRÉSENCES VALIDÉES (sur {len(validated_presences)} au total):")
        print("="*100)
        print(f"{'ID':<10} {'Nom':<25} {'Méthode':<20} {'Date/Heure':<25} {'Code':<10}")
        print("="*100)
        
        for p in validated_presences[-30:]:
            emp_id = str(p['employee_id'])[:9]
            name = str(p['name'])[:24]
            method = str(p['method'])[:19]
            dt = str(p['datetime'])[:24]
            code = f"({p['major']},{p['minor']})"
            
            print(f"{emp_id:<10} {name:<25} {method:<20} {dt:<25} {code:<10}")
    
    print("\n" + "="*100)
    print("📊 STATISTIQUES FINALES")
    print("="*100)
    
    # Validées vs Refusées
    validated_count = sum(1 for p in all_presences if "Validé" in p['validated'])
    refused_count = len(all_presences) - validated_count
    
    print(f"\n✅ Présences VALIDÉES  : {validated_count} ({validated_count/len(all_presences)*100:.1f}%)")
    print(f"❌ Présences REFUSÉES  : {refused_count} ({refused_count/len(all_presences)*100:.1f}%)")
    
    # Par méthode (validées uniquement)
    if validated_count > 0:
        method_counts = {}
        for p in all_presences:
            if "Validé" in p['validated']:
                method = p['method']
                method_counts[method] = method_counts.get(method, 0) + 1
        
        print("\n🔐 Méthodes d'authentification (validées):")
        for method, count in sorted(method_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {method:<20} : {count:>5} fois")
    
    # Par employé (validées uniquement)
    employees = {}
    employee_names = {}
    for p in all_presences:
        if "Validé" in p['validated'] and p['employee_id'] != "-":
            emp_id = p['employee_id']
            employees[emp_id] = employees.get(emp_id, 0) + 1
            if p['name'] != "-":
                employee_names[emp_id] = p['name']
    
    if employees:
        print(f"\n👥 Nombre d'employés avec présences validées: {len(employees)}")
        sorted_employees = sorted(employees.items(), key=lambda x: x[1], reverse=True)
        
        print("\n🏆 Top 15 des employés les plus présents:")
        for emp_id, count in sorted_employees[:15]:
            name = employee_names.get(emp_id, "Inconnu")
            print(f"   {emp_id:<10} {name:<25} : {count:>5} présences")
    
    # Par code
    print("\n🔢 Répartition par code d'événement:")
    code_stats = {}
    for p in all_presences:
        code = f"({p['major']}, {p['minor']})"
        validated = "Validé" in p['validated']
        key = (code, validated)
        code_stats[key] = code_stats.get(key, 0) + 1
    
    for (code, validated), count in sorted(code_stats.items(), key=lambda x: x[1], reverse=True):
        status = "✅ Validé" if validated else "❌ Refusé"
        print(f"   {code:<15} {status:<12} : {count:>5} fois")

print("\n" + "="*100)
print("✅ SCRIPT TERMINÉ!")
print("="*100)
print("\n📁 Fichiers générés:")
print("   1. presences_completes.json  (toutes les présences)")
print("   2. presences_completes.csv   (format Excel)")
print("   3. events_debug.json         (données brutes)")
print("\n💡 Vous devriez maintenant voir des présences VALIDÉES !")
print("\n")