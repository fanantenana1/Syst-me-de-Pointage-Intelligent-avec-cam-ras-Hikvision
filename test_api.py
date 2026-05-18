#!/usr/bin/env python3
"""
Script de test de l'API /api/users/add
Simule l'ajout d'un utilisateur depuis le formulaire frontend
"""
import requests
import time
from pathlib import Path
from PIL import Image
import io

# Configuration de test
BASE_URL = "http://127.0.0.1:8888"
DEVICE_IP = "10.0.124.55"
USERNAME = "admin"
PASSWORD = "Eni20230"
PORT = 80

def create_test_image():
    """Crée une image de test (petite)"""
    img = Image.new('RGB', (400, 300), color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf

def test_add_user():
    """Test l'endpoint /api/users/add"""
    
    print("=" * 60)
    print("🧪 TEST: Ajout d'un utilisateur")
    print("=" * 60)
    
    # Préparer les données du formulaire
    form_data = {
        'device_ip': DEVICE_IP,
        'username': USERNAME,
        'password': PASSWORD,
        'port': str(PORT),
        'employee_no': 'TEST_USER_001',
        'name': 'Test User',
        'cin': '123456789',
        'email': 'test@example.com',
        'telephone': '+261 32 00 00 00',
        'address': 'Test Address',
        'carte_number': 'CARD001',
        'fingerprint_id': 'FP001',
        'user_type': 'normal',
        'valid_days': '365',
        'door_rights': '1'
    }
    
    # Créer une image de test
    test_img = create_test_image()
    
    # Préparer les fichiers
    files = {
        'photos': ('test_photo.jpg', test_img, 'image/jpeg')
    }
    
    url = f"{BASE_URL}/api/users/add"
    
    print(f"\n📍 URL: {url}")
    print(f"📦 Formulaire:")
    for key, val in form_data.items():
        if key != 'password':
            print(f"   {key}: {val}")
    print(f"   photos: test_photo.jpg (test image)")
    
    try:
        print("\n⏳ Envoi de la requête...")
        start_time = time.time()
        
        response = requests.post(
            url,
            data=form_data,
            files=files,
            timeout=30
        )
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Réponse reçue en {elapsed:.2f}s")
        print(f"Status Code: {response.status_code}")
        print(f"\nRéponse JSON:")
        try:
            data = response.json()
            import json
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except:
            print(response.text[:500])
        
        return response.status_code in (200, 201)
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ ERREUR: Impossible de se connecter au serveur")
        print(f"   {e}")
        print(f"\n💡 Assurez-vous que le serveur est lancé:")
        print(f"   cd '/home/fanantenana/Musique/WebReco_face pro_fin_anné'")
        print(f"   uvicorn main6:app --host 0.0.0.0 --port 8000 --reload")
        return False
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        return False

def test_connection():
    """Test la connexion au serveur"""
    print("=" * 60)
    print("🔌 TEST: Connexion au serveur")
    print("=" * 60)
    
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"✅ Serveur accessible: {response.status_code}")
        return True
    except:
        print(f"❌ Serveur non accessible à {BASE_URL}")
        return False

if __name__ == "__main__":
    print("\n🚀 Démarrage des tests...\n")
    
    if test_connection():
        test_add_user()
    else:
        print("\n⚠️ Les tests ne peuvent pas continuer sans serveur")
        exit(1)
