#!/usr/bin/env python3
"""
Test script para verificar /api/save_ip_to_list endpoint
"""
import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:8000"
IP_LIST_FILE = Path("/home/fanantenana/Musique/WebReco_face pro_fin_anné/ip_list.txt")

def test_save_ip():
    """Test saving IP+port to ip_list.txt"""
    
    print("\n" + "="*60)
    print("🧪 Testing /api/save_ip_to_list endpoint")
    print("="*60 + "\n")
    
    # Test data
    test_cases = [
        {
            "device_ip": "192.168.101.22",
            "port": 8080,
            "device_name": None,  # Backend will auto-generate CAMx
            "description": "Test 1: Auto-generate CAM name"
        },
        {
            "device_ip": "192.168.101.25",
            "port": 80,
            "device_name": "CAM_MAIN",
            "description": "Test 2: Custom device name"
        },
        {
            "device_ip": "192.168.101.22",  # Duplicate IP
            "port": 8080,
            "device_name": "CAM_DUP",
            "description": "Test 3: Duplicate IP (should skip)"
        }
    ]
    
    for test in test_cases:
        print(f"📝 {test['description']}")
        
        data = {
            "device_ip": test["device_ip"],
            "port": test["port"]
        }
        if test["device_name"]:
            data["device_name"] = test["device_name"]
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/save_ip_to_list",
                data=data,
                timeout=5
            )
            
            result = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Response: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            if response.status_code == 200 and result.get("success"):
                print(f"   ✅ Entry: {result.get('entry')}\n")
            else:
                print(f"   ❌ Failed\n")
                
        except Exception as e:
            print(f"   ❌ Error: {e}\n")
    
    # Show updated ip_list.txt
    print("="*60)
    print("📄 Updated ip_list.txt content:")
    print("="*60)
    
    if IP_LIST_FILE.exists():
        with open(IP_LIST_FILE, "r") as f:
            content = f.read()
            print(content)
    else:
        print("❌ File not found")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    test_save_ip()
