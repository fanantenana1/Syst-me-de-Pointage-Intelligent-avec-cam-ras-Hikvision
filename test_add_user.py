#!/usr/bin/env python3
"""
Test script to diagnose /api/users/add endpoint
"""
import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:8000"

# Test device configuration (adjust to your actual device)
device_ip = "192.168.101.18"
username = "admin"
password = "12345"
port = 80

def test_user_creation():
    """Test creating a new user via /api/users/add"""
    
    # Prepare form data
    data = {
        "device_ip": device_ip,
        "username": username,
        "password": password,
        "employee_no": "TEST002",
        "name": "Test User",
        "cin": "12345678",
        "email": "test@example.com",
        "telephone": "5551234567",
        "address": "Test Address",
        "carte_number": "CARD001",
        "fingerprint_id": "FP001",
        "user_type": "normal",
        "valid_days": 365,
        "door_rights": "1",
        "port": 80,
    }
    
    print("\n" + "="*60)
    print("🧪 Testing /api/users/add endpoint")
    print("="*60)
    print(f"\nRequest Data:")
    for key, value in data.items():
        if key == "password":
            print(f"  {key}: {'*'*len(value)}")
        else:
            print(f"  {key}: {value}")
    
    try:
        # Send POST request (without file first to test basic validation)
        response = requests.post(
            f"{BASE_URL}/api/users/add",
            data=data,
            timeout=30
        )
        
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"\nResponse Body:")
        
        try:
            json_response = response.json()
            print(json.dumps(json_response, indent=2, ensure_ascii=False))
        except:
            print(response.text[:500])
        
        if response.status_code == 200:
            print("\n✅ SUCCESS - User created!")
        else:
            print(f"\n❌ FAILED - Status {response.status_code}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")

def test_with_image():
    """Test with an actual image file"""
    print("\n" + "="*60)
    print("🧪 Testing /api/users/add with image")
    print("="*60)
    
    # Create a simple test image
    test_image_path = Path("/tmp/test_image.jpg")
    try:
        from PIL import Image
        img = Image.new('RGB', (200, 200), color='red')
        img.save(test_image_path)
        print(f"\n✅ Created test image: {test_image_path}")
    except Exception as e:
        print(f"\n⚠️ Could not create image: {e}")
        return
    
    # Prepare form data with image
    data = {
        "device_ip": device_ip,
        "username": username,
        "password": password,
        "employee_no": "TEST003",
        "name": "Test User With Image",
        "cin": "87654321",
        "email": "test2@example.com",
        "telephone": "5555555555",
        "address": "Test Address 2",
        "carte_number": "CARD002",
        "fingerprint_id": "FP002",
        "user_type": "normal",
        "valid_days": 365,
        "door_rights": "1",
        "port": 80,
    }
    
    try:
        with open(test_image_path, 'rb') as f:
            files = {'photos': (test_image_path.name, f, 'image/jpeg')}
            response = requests.post(
                f"{BASE_URL}/api/users/add",
                data=data,
                files=files,
                timeout=30
            )
        
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"\nResponse Body:")
        
        try:
            json_response = response.json()
            print(json.dumps(json_response, indent=2, ensure_ascii=False))
        except:
            print(response.text[:500])
            
        if response.status_code == 200:
            print("\n✅ SUCCESS - User created with image!")
        else:
            print(f"\n❌ FAILED - Status {response.status_code}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    print("\n🔍 /api/users/add Endpoint Diagnostic Test")
    test_user_creation()
    test_with_image()
    print("\n" + "="*60)
    print("✅ Tests completed - Check server logs for details")
    print("="*60 + "\n")
