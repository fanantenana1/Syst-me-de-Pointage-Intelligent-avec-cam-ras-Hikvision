from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import shutil, base64, os, time, secrets, subprocess, uuid
import face_recognition
import requests
from requests.auth import HTTPDigestAuth
from requests.exceptions import ConnectionError, RequestException
import numpy as np
import cv2
import threading
import queue
import uvicorn
import asyncio
import io
from PIL import Image
from bson import ObjectId
from pathlib import Path
from db import users_collection, videos_collection, images_collection, evenements2_collection
from cloudinary_config import cloudinary
import cloudinary.uploader
from collections import Counter
import csv
import json
from functools import lru_cache
from troue_ip import HikvisionFinder  # Importer votre class scanner externe
import traceback
from pymongo.errors import BulkWriteError

app = FastAPI(title="Hikvision Surveillance System")
# Configuration des chemins
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Static files and templates
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory="templates")
# =================== Variables globales ===================
CAM_URL = ""
last_recognized_name = "Aucun"
os.makedirs("SARY", exist_ok=True)
FILE_PATH = "ips.txt"
MAX_IPS_PER_PORT = 5
ip_file = "ip_list.txt"
FFMPEG_PROCS: Dict[str, subprocess.Popen] = {}

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

bn ="photos"
PHOTO_CACHE = {}
PHOTO_CACHE_DURATION = timedelta(minutes=5)

# =================== Configuration ===================
# Fonction pour détecter automatiquement l'IP locale

@app.middleware("http")
async def add_ngrok_header(request, call_next):
    response: Response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response
def get_local_ip():
    """Détecte automatiquement l'IP locale du serveur"""
    try:
        import socket
        # Se connecte à un serveur externe pour obtenir l'IP locale
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# Configuration de l'IP publique pour les uploads
# Option 1: IP fixe (à décommenter et modifier)
# PUBLIC_IP = "192.168.101.26"

# Option 2: Détection automatique (recommandé)
PUBLIC_IP = get_local_ip()
PUBLIC_PORT = 8000

print(f"🌐 Public IP for Hikvision photo uploads: {PUBLIC_IP}:{PUBLIC_PORT}")

# =================== Configuration Vidéo RTSP ===================
# Note: Removed hardcoded RTSP_URL to ensure the app uses the
# dynamic `SELECTED_DEVICE_CONFIG` via `get_rtsp_url()`.
# RTSP_URL will be generated with `get_rtsp_url()` so that when the
# frontend saves a selected device (via /api/save_device_config),
# the RTSP thread can be restarted with the correct IP/credentials.
#RTSP_URL = "rtsp://admin:Eni20230@192.168.101.24:554/Streaming/Channels/101" #ip pour le connection
frame_queue = queue.Queue(maxsize=1)
streaming_active = False
connection_lock = threading.Lock()

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
# Ajouter cette route après les autres routes API
# Ajouter après les imports
SELECTED_DEVICE_CONFIG = {
    "ip": "192.168.101.18",
    "username": "admin", 
    "password": "Eni20230",
    "port": 80
}
# Liste des IPs scannées (persistée)
SCANNED_IPS_LIST = ["192.168.101.18"]  # IP par défaut

# RTSP URL dynamique
def get_rtsp_url():
    """Génère l'URL RTSP basée sur la config actuelle"""
    config = SELECTED_DEVICE_CONFIG
    return f"rtsp://{config['username']}:{config['password']}@{config['ip']}:554/Streaming/Channels/101"

RTSP_URL = get_rtsp_url()    
#RTSP_URL = "rtsp://admin:Eni20230@192.168.101.18:554/Streaming/Channels/101"
#////////// PAGE DE CONNECTION
# =================== Routes principales ===================
# Routes d'authentification à ajouter/remplacer dans main6.py
# =================== PAGE D'ACCUEIL (Landing Page) ===================
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """
    Page d'accueil publique avec formulaire de connexion/inscription
    """
    return templates.TemplateResponse("page_accueil.html", {"request": request})


# =================== PAGE ADMIN (Dashboard) ===================
@app.get("/home", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """
    Page d'administration (page_ajour.html)
    Nécessite une authentification
    """
    # Vérifier si l'utilisateur est connecté
    if not request.cookies.get("logged"):
        return RedirectResponse("/", status_code=302)
    
    # Récupérer les informations utilisateur depuis le cookie
    username = request.cookies.get("username", "admin")
    user_type = request.cookies.get("user_type", "admin")
    
    ip_dict = read_ip_list()
    
    return templates.TemplateResponse("admin/page_ajour.html", {
        "request": request, 
        "ports": ip_dict, 
        "cam_url": CAM_URL,
        "username": username,
        "user_type": user_type
    })


# =================== CONNEXION ===================
@app.post("/login")
async def login_action(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...),
    userType: str = Form(...)
):
    """
    Traitement de la connexion
    Supporte admin et employé
    """
    try:
        print(f"🔐 Tentative de connexion: {username} ({userType})")
        
        # Authentification selon le type d'utilisateur
        if userType == "admin":
            # Vérifier les credentials admin
            # Option 1: Credentials hardcodés (simple)
            if username == "admin" and password == "admin123":
                response = RedirectResponse("/home", status_code=302)
                response.set_cookie("logged", "1", httponly=True)
                response.set_cookie("username", username, httponly=True)
                response.set_cookie("user_type", "admin", httponly=True)
                print(f"✅ Admin connecté: {username}")
                return response
            
            # Option 2: Vérifier dans MongoDB (si vous avez une collection admin_users)
            # admin_user = await admin_users_collection.find_one({
            #     "username": username,
            #     "password": hashlib.sha256(password.encode()).hexdigest()
            # })
            # if admin_user:
            #     response = RedirectResponse("/home", status_code=302)
            #     response.set_cookie("logged", "1", httponly=True)
            #     response.set_cookie("username", username, httponly=True)
            #     response.set_cookie("user_type", "admin", httponly=True)
            #     return response
        
        elif userType == "employee":
            # Vérifier si l'employé existe dans la collection users
            employee = await users_collection.find_one({
                "$or": [
                    {"name": username,
                     "employee_no": password},  # Utiliser employee_no comme mot de passe
                    {"email": username,
                     "employee_no": password}   # Ou email + employee_no
                ]
            })            
            if employee:
                # Option 1: Pas de mot de passe pour les employés (juste employee_no)
                response = RedirectResponse("/employee_dashboard", status_code=302)
                response.set_cookie("logged", "1", httponly=True)
                response.set_cookie("username", employee.get("name", username), httponly=True)
                response.set_cookie("user_type", "employee", httponly=True)
                response.set_cookie("employee_no", employee.get("employee_no"), httponly=True)
                print(f"✅ Employé connecté: {employee.get('name')}")
                return response
                
                # Option 2: Vérifier mot de passe si vous en avez
                # if employee.get("password") == hashlib.sha256(password.encode()).hexdigest():
                #     response = RedirectResponse("/employee_dashboard", status_code=302)
                #     ...
        
        # Échec d'authentification
        print(f"❌ Échec de connexion pour {username}")
        return templates.TemplateResponse("page_accueil.html", {
            "request": request,
            "error": "Identifiants incorrects",
            "username": username,
            "userType": userType
        })
        
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("page_accueil.html", {
            "request": request,
            "error": f"Erreur de connexion: {str(e)}"
        })


# =================== INSCRIPTION (Nouveau compte) ===================
@app.post("/signup")
async def signup_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(...),
    userType: str = Form("employee")
):
    """
    Création de nouveau compte
    Redirige vers /inscription pour les employés
    """
    try:
        print(f"📝 Tentative d'inscription: {username} ({userType})")
        
        if userType == "employee":
            # Rediriger vers la page d'inscription externe complète
            return RedirectResponse("/inscription", status_code=302)
        
        elif userType == "admin":
            # Les admins doivent être créés manuellement
            return templates.TemplateResponse("page_accueil.html", {
                "request": request,
                "error": "Les comptes administrateurs doivent être créés par un super admin",
                "info": "Contactez votre administrateur système"
            })
        
    except Exception as e:
        print(f"❌ Erreur d'inscription: {e}")
        return templates.TemplateResponse("page_accueil.html", {
            "request": request,
            "error": f"Erreur d'inscription: {str(e)}"
        })


# =================== DASHBOARD EMPLOYÉ ===================
@app.get("/employee_dashboard", response_class=HTMLResponse)
async def employee_dashboard(request: Request):
    """
    Dashboard pour les employés
    """
    # Vérifier si l'utilisateur est connecté
    if not request.cookies.get("logged"):
        return RedirectResponse("/", status_code=302)
    
    # Vérifier que c'est bien un employé
    if request.cookies.get("user_type") != "employee":
        return RedirectResponse("/home", status_code=302)
    
    employee_no = request.cookies.get("employee_no")
    username = request.cookies.get("username", "Employé")
    #print("EMP= ",employee_no,"USER= ",username)
    # Récupérer les informations de l'employé
    try:
        employee = await users_collection.find_one({"name":username,"employee_no": employee_no})    
        #print("EMP2= ",employee)   
        if not employee:
            return RedirectResponse("/logout", status_code=302)
        
        # Récupérer les événements de présence de l'employé
        # (à adapter selon votre structure)
        
        return templates.TemplateResponse("employee_dashboard_html", {
            "request": request,
            "employee": employee,
            "username": username
        })
        
    except Exception as e:
        print(f"❌ Erreur dashboard employé: {e}")
        return RedirectResponse("/", status_code=302)


# =================== DÉCONNEXION ===================
@app.get("/logout")
async def logout(request: Request):
    """
    Déconnexion et suppression des cookies
    """
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("logged")
    response.delete_cookie("username")
    response.delete_cookie("user_type")
    response.delete_cookie("employee_no")
    
    print("👋 Utilisateur déconnecté")
    return response


# =================== PAGE DE LOGIN DÉDIÉE (Optionnel) ===================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Page de connexion dédiée (alternative)
    """
    # Si déjà connecté, rediriger
    if request.cookies.get("logged"):
        user_type = request.cookies.get("user_type", "admin")
        if user_type == "admin":
            return RedirectResponse("/home", status_code=302)
        else:
            return RedirectResponse("/employee_dashboard", status_code=302)
    
    return templates.TemplateResponse("page_accueil.html", {"request": request})

@app.post("/set_ip")
async def set_ip(ip: str = Form(...)):
    global CAM_URL
    ip_dict = read_ip_list()

    found = False
    for port, ips in ip_dict.items():
        if ip in ips:
            found = True
            break

    if not found:
        next_port = f"CAM{len(ip_dict)+1}"
        ip_dict.setdefault(next_port, []).append(ip)
        write_ip_list(ip_dict)

    CAM_URL = ip
    return RedirectResponse("/home", status_code=303)
# Route pour récupérer la configuration actuelle
@app.get("/api/get_device_config")
async def get_device_config():
    """Récupère la configuration de l'appareil actuel"""
    return JSONResponse({
        "success": True,
        "config": SELECTED_DEVICE_CONFIG
    })

# Modifier la route de scan pour inclure dans la liste
# Modifier la route de scan pour persister les IPs
@app.get("/api/scan_hikvision_devices")
async def scan_hikvision_devices():
    """Scanne le réseau local pour trouver les appareils Hikvision"""
    global SCANNED_IPS_LIST
    
    try:
        print("🔍 Starting Hikvision device scan...")
        finder = HikvisionFinder()
        subnet = finder.get_local_network()
        
        print(f"📡 Network detected: {subnet}")
        devices = finder.scan_once(subnet)
        
        found_devices = []
        new_ips = []
        
        for device in devices:
            device_info = {
                "ip": device["ip"],
                "mac": device.get("mac", "Unknown"),
                "model": device.get("model", "Hikvision Device"),
                "ports": device.get("ports", []),
                "confidence": device.get("confidence", 0),
                "reasons": ", ".join(device.get("reasons", []))
            }
            found_devices.append(device_info)
            
            # Ajouter à la liste persistée si pas déjà présent
            if device["ip"] not in SCANNED_IPS_LIST:
                SCANNED_IPS_LIST.append(device["ip"])
                new_ips.append(device["ip"])
        
        print(f"✅ Scan complete. Found {len(found_devices)} Hikvision devices")
        if new_ips:
            print(f"📝 Added {len(new_ips)} new IPs to list: {new_ips}")
        
        return JSONResponse({
            "success": True,
            "devices": found_devices,
            "total": len(found_devices),
            "network": subnet,
            "current_config": SELECTED_DEVICE_CONFIG,
            "all_ips": SCANNED_IPS_LIST  # Retourner toutes les IPs
        })
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"❌ Scan error: {error_detail}")
        
        return JSONResponse({
            "success": False,
            "error": str(e),
            "devices": [],
            "all_ips": SCANNED_IPS_LIST  # Retourner quand même la liste
        }, status_code=500)
# Route pour ajouter une IP manuellement
@app.post("/api/add_manual_ip")
async def add_manual_ip(ip: str = Form(...)):
    """Ajoute une IP manuellement à la liste"""
    global SCANNED_IPS_LIST
    
    if ip not in SCANNED_IPS_LIST:
        SCANNED_IPS_LIST.append(ip)
        print(f"📝 Added manual IP: {ip}")
        return JSONResponse({
            "success": True,
            "message": "IP ajoutée",
            "all_ips": SCANNED_IPS_LIST
        })
    else:
        return JSONResponse({
            "success": True,
            "message": "IP déjà présente",
            "all_ips": SCANNED_IPS_LIST
        })

# Route pour obtenir le statut RTSP actuel
@app.get("/api/rtsp_status")
async def rtsp_status():
    """Retourne le statut du flux RTSP"""
    return JSONResponse({
        "streaming": streaming_active,
        "rtsp_url": RTSP_URL.replace(SELECTED_DEVICE_CONFIG['password'], '***'),
        "device_ip": SELECTED_DEVICE_CONFIG['ip'],
        "thread_alive": stream_thread.is_alive() if stream_thread else False
    })    
################### configuration device #######################""    
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
# =================== Classes HikvisionManager ===================
class HikvisionManager:
    """Gestion utilisateurs + photos faciales via ISAPI"""

    def __init__(self, ip: str, username: str, password: str, port: int = 80):
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.base_url = f"http://{ip}:{port}/ISAPI"
        self.auth = HTTPDigestAuth(username, password)

    def _is_method_not_allowed(self, text: str, status_code: int) -> bool:
        if status_code in (405, 400):
            return True
        if not text:
            return False
        low = text.lower()
        return "methodnotallowed" in low or "invalid operation" in low

    def add_user(self, employee_no: str, name: str, user_type: str = "normal",
                 valid_days: int = 365, door_rights: str = "1") -> Dict:
        now = datetime.now()
        begin_time = now.strftime("%Y-%m-%dT00:00:00")
        end_time = (now + timedelta(days=valid_days)).strftime("%Y-%m-%dT23:59:59")

        user_data = {
            "UserInfo": {
                "employeeNo": employee_no,
                "name": name,
                "userType": user_type,
                "Valid": {
                    "enable": True,
                    "beginTime": begin_time,
                    "endTime": end_time,
                    "timeType": "local"
                },
                "doorRight": door_rights,
                "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]
            }
        }

        url = f"{self.base_url}/AccessControl/UserInfo/Record?format=json"
        headers = {"Content-Type": "application/json"}
        try:
            r = requests.post(url, json=user_data, auth=self.auth, headers=headers, timeout=10)
            return {"success": r.status_code in (200, 201), "status_code": r.status_code, "response": r.text}
        except RequestException as e:
            return {"success": False, "error": str(e)}

    def update_user(self, employee_no: str, name: Optional[str] = None,
                    user_type: Optional[str] = None, valid_days: Optional[int] = None,
                    door_rights: Optional[str] = None) -> Dict:
        """Mise à jour d'utilisateur avec stratégies multiples"""
        current_user = self._get_user_info(employee_no)
        if not current_user:
            return {"success": False, "error": f"Utilisateur {employee_no} introuvable"}

        now = datetime.now()
        begin_time = now.strftime("%Y-%m-%dT00:00:00")
        end_time = (now + timedelta(days=valid_days or 365)).strftime("%Y-%m-%dT23:59:59")

        final_name = name if name is not None else current_user.get("name", "")
        final_user_type = user_type if user_type is not None else current_user.get("userType", "normal")
        final_door_rights = door_rights if door_rights is not None else current_user.get("doorRight", "1")

        json_body = {
            "UserInfo": {
                "employeeNo": employee_no,
                "name": final_name,
                "userType": final_user_type,
                "Valid": {
                    "enable": True,
                    "beginTime": begin_time,
                    "endTime": end_time,
                    "timeType": "local"
                },
                "doorRight": final_door_rights,
                "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]
            }
        }

        xml_body = (
            f"<?xml version='1.0' encoding='UTF-8'?>"
            f"<UserInfo>"
            f"<employeeNo>{employee_no}</employeeNo>"
            f"<name>{final_name}</name>"
            f"<userType>{final_user_type}</userType>"
            f"<Valid><enable>true</enable><beginTime>{begin_time}</beginTime><endTime>{end_time}</endTime><timeType>local</timeType></Valid>"
            f"<doorRight>{final_door_rights}</doorRight>"
            f"<RightPlan><doorNo>1</doorNo><planTemplateNo>1</planTemplateNo></RightPlan>"
            f"</UserInfo>"
        ).encode("utf-8")

        urls = [
            f"{self.base_url}/AccessControl/UserInfo/Modify?format=json",
            f"{self.base_url}/AccessControl/UserInfo/Record?format=json&employeeNo={employee_no}",
            f"{self.base_url}/AccessControl/UserInfo/Record?employeeNo={employee_no}",
        ]

        strategies = [
            ("PUT", "application/json", json_body, None),
            ("PUT", "application/xml", xml_body, None),
            ("POST", "application/json", json_body, None),
            ("POST", "application/xml", xml_body, None),
            ("POST", "application/json", json_body, "PUT"),
            ("POST", "application/xml", xml_body, "PUT"),
        ]

        last_err = {"success": False, "error": "Aucune stratégie n'a fonctionné"}

        for url in urls:
            for method, content_type, body, override in strategies:
                try:
                    headers = {"Content-Type": content_type}
                    if override:
                        headers["X-HTTP-Method-Override"] = override

                    if content_type == "application/json":
                        if method == "PUT":
                            r = requests.put(url, json=json_body, auth=self.auth, headers=headers, timeout=10)
                        else:
                            r = requests.post(url, json=json_body, auth=self.auth, headers=headers, timeout=10)
                    else:
                        if method == "PUT":
                            r = requests.put(url, data=body, auth=self.auth, headers=headers, timeout=10)
                        else:
                            r = requests.post(url, data=body, auth=self.auth, headers=headers, timeout=10)

                    if r.status_code in (200, 201, 204):
                        return {
                            "success": True,
                            "status_code": r.status_code,
                            "response": r.text,
                            "method": f"{method}-{content_type.split('/')[-1]}" + (f"-override-{override}" if override else ""),
                            "url": url
                        }

                    last_err = {
                        "success": False,
                        "status_code": r.status_code,
                        "response": r.text,
                        "url": url,
                        "method": f"{method}-{content_type.split('/')[-1]}" + (f"-override-{override}" if override else "")
                    }

                except RequestException as e:
                    last_err = {"success": False, "error": str(e), "url": url}
                    continue

        return last_err

    def delete_user(self, employee_no: str) -> Dict:
        """Suppression d'utilisateur avec stratégies multiples"""
        xml_body = f"<?xml version='1.0' encoding='UTF-8'?><UserInfoDelCond><EmployeeNoList><employeeNo>{employee_no}</employeeNo></EmployeeNoList></UserInfoDelCond>".encode("utf-8")
        
        json_body = {"UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": employee_no}]}}

        urls = [
            f"{self.base_url}/AccessControl/UserInfo/Delete?format=json",
            f"{self.base_url}/AccessControl/UserInfo/Record?format=json&employeeNo={employee_no}",
            f"{self.base_url}/AccessControl/UserInfo/Record?employeeNo={employee_no}",
        ]

        strategies = [
            ("DELETE", None, None, None),
            ("PUT", "application/json", json_body, "DELETE"),
            ("PUT", "application/xml", xml_body, "DELETE"),
            ("POST", "application/json", json_body, "DELETE"),
            ("POST", "application/xml", xml_body, "DELETE"),
        ]

        last_err = {"success": False, "error": "Aucune stratégie n'a fonctionné"}

        for url in urls:
            for method, content_type, body, override in strategies:
                try:
                    headers = {}
                    if content_type:
                        headers["Content-Type"] = content_type
                    if override:
                        headers["X-HTTP-Method-Override"] = override

                    if method == "DELETE":
                        r = requests.delete(url, auth=self.auth, timeout=10)
                    elif method == "PUT":
                        if content_type == "application/json":
                            r = requests.put(url, json=body, auth=self.auth, headers=headers, timeout=10)
                        else:
                            r = requests.put(url, data=body, auth=self.auth, headers=headers, timeout=10)
                    else:
                        if content_type == "application/json":
                            r = requests.post(url, json=body, auth=self.auth, headers=headers, timeout=10)
                        else:
                            r = requests.post(url, data=body, auth=self.auth, headers=headers, timeout=10)

                    if r.status_code in (200, 201, 204):
                        return {
                            "success": True,
                            "status_code": r.status_code,
                            "response": r.text,
                            "method": f"{method}" + (f"-{content_type.split('/')[-1]}" if content_type else "") + (f"-override" if override else ""),
                            "url": url
                        }

                    last_err = {
                        "success": False,
                        "status_code": r.status_code,
                        "response": r.text,
                        "url": url,
                        "method": f"{method}" + (f"-{content_type.split('/')[-1]}" if content_type else "")
                    }

                except RequestException as e:
                    last_err = {"success": False, "error": str(e), "url": url}
                    continue

        return last_err

    def _get_user_info(self, employee_no: str) -> Optional[Dict]:
        """Récupère les informations d'un utilisateur spécifique"""
        try:
            users = self.get_all_users()
            for user in users:
                if user.get("employeeNo") == employee_no:
                    return user
            return None
        except Exception:
            return None

    def upload_face_photo(self, employee_no: str, photo_url: str) -> Dict:
        """Upload face photo using faceURL method"""
        endpoints = [
            f"{self.base_url}/Intelligent/FDLib/FaceDataRecord?format=json",
            f"{self.base_url}/Intelligent/FDLib/FDSetUp?format=json",
        ]
        
        for url in endpoints:
            payload = {
                "faceLibType": "blackFD",
                "FDID": "1",
                "FPID": employee_no,
                "name": employee_no,
                "faceURL": photo_url
            }
            headers = {"Content-Type": "application/json"}
            try:
                r = requests.post(url, json=payload, auth=self.auth, headers=headers, timeout=20)
                if r.status_code in (200, 201):
                    return {"success": True, "status_code": r.status_code, "response": r.text, "method": "faceURL", "url": url}
            except ConnectionError as e:
                if "RemoteDisconnected" in str(e) or "Unexpected EOF" in str(e):
                    return {"success": True, "status_code": 200, "response": "Connection closed by device (likely success)", "method": "faceURL", "url": url}
                continue
            except RequestException:
                continue
        
        return {"success": False, "error": "Tous les endpoints ont échoué", "method": "faceURL"}

    def upload_face_photo_base64(self, employee_no: str, image_path: str) -> Dict:
        """Upload face photo using base64 encoding - essaie plusieurs méthodes"""
        import base64
        try:
            with open(image_path, "rb") as img_file:
                img_data = base64.b64encode(img_file.read()).decode("utf-8")

            print(f"Base64 image size: {len(img_data)} characters")

            # Essayer plusieurs endpoints et formats
            attempts = [
                # Format 1: FaceDataRecord avec faceData
                {
                    "url": f"{self.base_url}/Intelligent/FDLib/FaceDataRecord?format=json",
                    "payload": {
                        "faceLibType": "blackFD",
                        "FDID": "1",
                        "FPID": employee_no,
                        "name": employee_no,
                        "faceData": img_data
                    },
                    "name": "FaceDataRecord-basic"
                },
                # Format 2: Sans faceLibType
                {
                    "url": f"{self.base_url}/Intelligent/FDLib/FaceDataRecord?format=json",
                    "payload": {
                        "FDID": "1",
                        "FPID": employee_no,
                        "name": employee_no,
                        "faceData": img_data
                    },
                    "name": "FaceDataRecord-simple"
                },
                # Format 3: FDSetUp
                {
                    "url": f"{self.base_url}/Intelligent/FDLib/FDSetUp?format=json",
                    "payload": {
                        "faceLibType": "blackFD",
                        "FDID": "1",
                        "FPID": employee_no,
                        "name": employee_no,
                        "faceData": img_data
                    },
                    "name": "FDSetUp"
                },
                # Format 4: Avec champs additionnels
                {
                    "url": f"{self.base_url}/Intelligent/FDLib/FaceDataRecord?format=json",
                    "payload": {
                        "faceLibType": "blackFD",
                        "FDID": "1",
                        "FPID": employee_no,
                        "name": employee_no,
                        "bornTime": "1990-01-01",
                        "sex": "male",
                        "faceData": img_data
                    },
                    "name": "FaceDataRecord-extended"
                },
                # Format 5: AccessControl/faces (certains terminaux)
                {
                    "url": f"{self.base_url}/AccessControl/FaceDataRecord?format=json",
                    "payload": {
                        "FaceDataRecord": {
                            "employeeNo": employee_no,
                            "faceData": img_data
                        }
                    },
                    "name": "AccessControl-FaceDataRecord"
                }
            ]

            headers = {"Content-Type": "application/json"}
            last_error = None
            
            for attempt in attempts:
                try:
                    print(f"Trying {attempt['name']} on {attempt['url']}")
                    r = requests.post(attempt["url"], json=attempt["payload"], auth=self.auth, headers=headers, timeout=30)
                    print(f"  Status: {r.status_code}, Response: {r.text[:200]}")
                    
                    if r.status_code in (200, 201):
                        print(f"✅ Success with {attempt['name']}")
                        return {
                            "success": True, 
                            "status_code": r.status_code, 
                            "response": r.text, 
                            "method": f"base64-{attempt['name']}",
                            "url": attempt["url"]
                        }
                    last_error = {
                        "status_code": r.status_code,
                        "response": r.text,
                        "method": attempt['name']
                    }
                except ConnectionError as e:
                    if "RemoteDisconnected" in str(e) or "Unexpected EOF" in str(e):
                        print(f"⚠️ Connection closed (may be success) for {attempt['name']}")
                        return {
                            "success": True, 
                            "status_code": 200, 
                            "response": "Connection closed by device (likely success)", 
                            "method": f"base64-{attempt['name']}",
                            "url": attempt["url"]
                        }
                    print(f"  Connection error: {e}")
                    last_error = {"error": str(e), "method": attempt['name']}
                except RequestException as e:
                    print(f"  Request error: {e}")
                    last_error = {"error": str(e), "method": attempt['name']}
                    continue
            
            print(f"❌ All base64 methods failed")
            return {"success": False, "error": "Tous les formats base64 ont échoué", "method": "base64", "last_error": last_error}
            
        except Exception as e:
            print(f"❌ Global base64 error: {e}")
            return {"success": False, "error": str(e), "method": "base64"}

    def verify_face(self, employee_no: str) -> bool:
        """Vérifie si une photo faciale existe pour cet employé"""
        try:
            url = f"{self.base_url}/Intelligent/FDLib/FaceDataRecord?format=json&FDID=1&FPID={employee_no}"
            r = requests.get(url, auth=self.auth, timeout=10)
            if r.status_code == 200 and employee_no in r.text:
                return True
            
            url2 = f"{self.base_url}/Intelligent/FDLib/FDSearch?format=json"
            payload = {
                "FDSearchCond": {
                    "searchID": "1",
                    "FDID": "1",
                    "searchResultPosition": 0,
                    "maxResults": 100
                }
            }
            r2 = requests.post(url2, json=payload, auth=self.auth, timeout=10)
            if r2.status_code == 200 and employee_no in r2.text:
                return True
                
            return False
        except Exception:
            return False

    def get_face_lib_capability(self) -> Dict:
        """Obtient les capacités de la bibliothèque faciale"""
        try:
            url = f"{self.base_url}/Intelligent/FDLib/capabilities?format=json"
            r = requests.get(url, auth=self.auth, timeout=10)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "response": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_users(self, max_results: int = 1000) -> List[Dict]:
        url = f"{self.base_url}/AccessControl/UserInfo/Search?format=json"
        headers = {"Content-Type": "application/json"}
        payload = {"UserInfoSearchCond": {"searchID": "1", "searchResultPosition": 0, "maxResults": max_results}}
        try:
            r = requests.post(url, json=payload, auth=self.auth, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            users = data.get("UserInfoSearch", {}).get("UserInfo", [])
            if isinstance(users, dict):
                return [users]
            return users or []
        except RequestException:
            return []
        except Exception:
            return []
    ############### NOUVELLE FONCTION POUR RÉCUPÉRER LES ÉVÉNEMENTS DE PRÉSENCE ###############    
    def get_all_events(self, max_results: int = 30) -> List[Dict]:
        """Récupère tous les événements de présence avec pagination"""
        all_presences = []
        position = 0
        
        while True:
            json_payload = {
                "ACSEventCond": {
                    "searchID": "1",
                    "searchResultPosition": position,
                    "maxResults": max_results,
                    "major": 5,
                    "minor": 0
                }
            }
            
            try:
                response = requests.post(
                    f"{self.base_url}/AccessControl/ACSEvent?format=json",
                    json=json_payload,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
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
                        
                        if response_status != "MORE" or num_matches < max_results:
                            break
                        
                        position += max_results
                    else:
                        break
                else:
                    break
            
            except Exception as e:
                print(f"Erreur récupération événements: {e}")
                break
        
        return all_presences
# À ajouter après la classe HikvisionManager

async def sync_mongodb_to_hikvision(device_ip: str, username: str, password: str, port: int = 80):
    """
    Synchronise tous les utilisateurs MongoDB vers Hikvision
    """
    try:
        manager = HikvisionManager(device_ip, username, password, port)
        
        # Récupérer tous les utilisateurs MongoDB pour ce device
        mongo_users_cursor = users_collection.find({"hikvision_device_ip": device_ip})
        synced = 0
        errors = []
        
        async for mongo_user in mongo_users_cursor:
            try:
                emp_no = mongo_user.get("employee_no")
                name = mongo_user.get("name")
                
                if not emp_no or not name:
                    continue
                
                # Vérifier si existe dans Hikvision
                hik_users = manager.get_all_users()
                exists_in_hik = any(
                    u.get("employeeNo") == emp_no or u.get("employeeid") == emp_no 
                    for u in hik_users
                )
                
                if not exists_in_hik:
                    # Créer dans Hikvision
                    result = manager.add_user(
                        emp_no, 
                        name,
                        mongo_user.get("user_type", "normal"),
                        mongo_user.get("valid_days", 365),
                        "1"
                    )
                    
                    if result.get("success"):
                        # Upload photo si existe
                        photo_url = mongo_user.get("photo_url")
                        if photo_url:
                            time.sleep(1)
                            manager.upload_face_photo(emp_no, photo_url)
                        
                        synced += 1
                        
                        # Mettre à jour le statut de sync
                        await users_collection.update_one(
                            {"_id": mongo_user["_id"]},
                            {"$set": {"synced_with_hikvision": True, "last_sync": datetime.utcnow()}}
                        )
                    else:
                        errors.append(f"{emp_no}: {result.get('error', 'Unknown error')}")
                        
            except Exception as e:
                errors.append(f"{emp_no}: {str(e)}")
                continue
        
        return {
            "success": True,
            "synced": synced,
            "errors": errors
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_hikvision_to_mongodb(device_ip: str, username: str, password: str, port: int = 80):
    """
    Synchronise tous les utilisateurs Hikvision vers MongoDB
    """
    try:
        manager = HikvisionManager(device_ip, username, password, port)
        hik_users = manager.get_all_users()
        
        synced = 0
        errors = []
        
        for hik_user in hik_users:
            try:
                emp_no = hik_user.get("employeeNo") or hik_user.get("employeeid")
                name = hik_user.get("name") or hik_user.get("userName")
                
                if not emp_no:
                    continue
                
                # Vérifier si existe dans MongoDB (par employee_no globalement)
                existing = await users_collection.find_one({
                    "employee_no": emp_no
                })

                if not existing:
                    # Créer dans MongoDB (nouvel utilisateur pour ce device)
                    user_doc = {
                        "employee_no": emp_no,
                        "name": name or "",
                        "cin": "",
                        "email": "",
                        "telephone": "",
                        "address": "",
                        "carte_number": "",
                        "fingerprint_id": "",
                        "user_type": hik_user.get("userType", "normal"),
                        "valid_days": 365,
                        "photo_url": "",
                        "hikvision_device_ip": device_ip,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "synced_with_hikvision": True,
                        "sync_source": "hikvision"
                    }

                    await users_collection.insert_one(user_doc)
                    synced += 1
                else:
                    # Document existant trouvé (même employee_no) — mettre à jour au lieu de créer un doublon
                    update_data = {"last_sync": datetime.utcnow(), "updated_at": datetime.utcnow()}

                    # Compléter le nom si manquant
                    if not existing.get("name") and name:
                        update_data["name"] = name

                    # Si l'enregistrement existant n'a pas de photo mais Hikvision en fournit, on peut laisser tel quel
                    # Mettre à jour l'IP du device si différent (on overwrite par la dernière source)
                    if existing.get("hikvision_device_ip") != device_ip:
                        update_data["hikvision_device_ip"] = device_ip

                    await users_collection.update_one(
                        {"_id": existing["_id"]},
                        {"$set": update_data}
                    )
                    
            except Exception as e:
                errors.append(f"{emp_no}: {str(e)}")
                continue
        
        return {
            "success": True,
            "synced": synced,
            "errors": errors
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}
    
######################## ================== Thread RTSP Hikvision ===================
class HikvisionStreamThread(threading.Thread):
    """Thread optimisé pour flux RTSP continu"""
    def __init__(self, rtsp_url: str = None):
        super().__init__(daemon=True)
        self.running = True
        self.cap = None
        self.rtsp_url = rtsp_url or get_rtsp_url()  # Utiliser URL dynamique
        self.reconnect_delay = 1
        self.max_reconnect_delay = 10
    
    def update_rtsp_url(self, new_url: str):
        """Met à jour l'URL RTSP et reconnecte"""
        self.rtsp_url = new_url
        if self.cap:
            with connection_lock:
                self.cap.release()
                self.cap = None    

    def create_capture(self):
        """Créé une capture OpenCV avec paramètres optimaux"""
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 25)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)    # 5 secondes timeout
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)    # 5 secondes timeout
        return cap
        
    def run(self):
        global streaming_active
        consecutive_errors = 0
        
        while self.running:
            try:
                with connection_lock:
                    print(f"🔄 Connexion caméra RTSP...")
                    self.cap = self.create_capture()
                    
                    if not self.cap.isOpened():
                        raise Exception("Impossible d'ouvrir le flux RTSP")
                    
                    print("✅ RTSP connecté!")
                    streaming_active = True
                    consecutive_errors = 0
                    self.reconnect_delay = 1
                
                while self.running and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    
                    if not ret or frame is None:
                        consecutive_errors += 1
                        if consecutive_errors > 10:
                            print("⚠️ Reconnexion RTSP...")
                            break
                        time.sleep(0.01)
                        continue
                    
                    consecutive_errors = 0
                    
                    try:
                        frame_resized = cv2.resize(frame, (640, 360), 
                                                   interpolation=cv2.INTER_LINEAR)
                        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 65]
                        _, buffer = cv2.imencode('.jpg', frame_resized, encode_param)
                        frame_bytes = buffer.tobytes()
                        
                        if not frame_queue.empty():
                            try:
                                frame_queue.get_nowait()
                            except queue.Empty:
                                pass
                        
                        try:
                            frame_queue.put(frame_bytes, block=False)
                        except queue.Full:
                            pass
                            
                    except Exception as e:
                        print(f"⚠️ Erreur encodage: {e}")
                        continue
                
            except Exception as e:
                print(f"❌ Erreur RTSP: {e}")
                streaming_active = False
                time.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, self.max_reconnect_delay)
                
            finally:
                with connection_lock:
                    if self.cap:
                        self.cap.release()
                        self.cap = None
                    streaming_active = False
                    
    def stop(self):
        self.running = False
        with connection_lock:
            if self.cap:
                self.cap.release()
# Instance globale du thread
stream_thread = None

def start_rtsp_thread():
    """Démarre ou redémarre le thread RTSP"""
    global stream_thread, streaming_active
    
    if stream_thread and stream_thread.is_alive():
        stream_thread.stop()
        stream_thread.join(timeout=2)
    
    stream_thread = HikvisionStreamThread(get_rtsp_url())
    stream_thread.start()
    print(f"📹 RTSP Thread started with URL: {get_rtsp_url().replace(SELECTED_DEVICE_CONFIG['password'], '***')}")

# Démarrer le thread au démarrage (use dynamic config)
start_rtsp_thread()
# Route pour sauvegarder la configuration avec mise à jour RTSP
@app.post("/api/save_device_config")
async def save_device_config(
    ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    port: int = Form(80)
):
    """Sauvegarde la configuration de l'appareil sélectionné"""
    global SELECTED_DEVICE_CONFIG, RTSP_URL
    
    SELECTED_DEVICE_CONFIG = {
        "ip": ip,
        "username": username,
        "password": password,
        "port": port
    }
    
    # Mettre à jour l'URL RTSP
    RTSP_URL = get_rtsp_url()
    
    # Redémarrer le thread RTSP avec la nouvelle URL
    start_rtsp_thread()
    
    print(f"✅ Configuration updated: {ip}")
    print(f"📹 RTSP URL updated: {RTSP_URL.replace(password, '***')}")
    
    return JSONResponse({
        "success": True,
        "message": "Configuration sauvegardée et RTSP mis à jour",
        "config": SELECTED_DEVICE_CONFIG,
        "rtsp_updated": True
    })

# Route pour sauvegarder l'IP+port dans ip_list.txt
@app.post("/api/save_ip_to_list")
async def save_ip_to_list(
    device_ip: str = Form(...),
    port: int = Form(80),
    device_name: Optional[str] = Form(None)
):
    """Sauvegarde IP:port dans ip_list.txt au format CAM_NAME:ip:port"""
    global SCANNED_IPS_LIST
    
    ip_file_path = BASE_DIR / "ip_list.txt"
    
    try:
        # Générer un nom de device s'il n'est pas fourni
        if not device_name or device_name.strip() == "":
            # Utiliser le numéro de CAM suivant
            existing_names = []
            if ip_file_path.exists():
                with open(ip_file_path, "r") as f:
                    for line in f:
                        if ":" in line:
                            parts = line.split(":")
                            if parts[0].startswith("CAM"):
                                try:
                                    existing_names.append(int(parts[0][3:]))
                                except:
                                    pass
            next_num = max(existing_names) + 1 if existing_names else 1
            device_name = f"CAM{next_num}"
        
        entry = f"{device_name}:{device_ip}:{port}"
        
        # Lire le fichier existant
        existing_entries = []
        if ip_file_path.exists():
            with open(ip_file_path, "r") as f:
                existing_entries = [line.strip() for line in f if line.strip()]
        
        # Vérifier si cette IP:port existe déjà
        ip_port_str = f"{device_ip}:{port}"
        entry_exists = any(ip_port_str in e for e in existing_entries)
        
        if not entry_exists:
            # Ajouter la nouvelle entrée
            existing_entries.append(entry)
            
            # Écrire le fichier
            with open(ip_file_path, "w") as f:
                for e in existing_entries:
                    f.write(e + "\n")
            
            print(f"✅ IP sauvegardée dans ip_list.txt: {entry}")
        else:
            print(f"⚠️ IP {ip_port_str} déjà présente dans ip_list.txt")
        
        # Ajouter à la liste globale SCANNED_IPS_LIST
        if device_ip not in SCANNED_IPS_LIST:
            SCANNED_IPS_LIST.append(device_ip)
        
        return JSONResponse({
            "success": True,
            "message": f"IP sauvegardée: {entry}",
            "device_name": device_name,
            "entry": entry,
            "already_exists": entry_exists
        })
        
    except Exception as e:
        print(f"❌ Erreur sauvegarde IP: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

# Route pour récupérer la liste des IPs scannées
@app.get("/api/get_scanned_ips")
async def get_scanned_ips():
    """Récupère la liste des IPs scannées"""
    return JSONResponse({
        "success": True,
        "ips": SCANNED_IPS_LIST,
        "current_config": SELECTED_DEVICE_CONFIG
    })


# Route pour récupérer le contenu de ip_list.txt
@app.get("/api/get_ip_list")
async def get_ip_list():
    """Lit le fichier ip_list.txt et retourne une liste d'entrées structurées
    Format supporté en fichier:
      CAM1:192.168.1.10:8080
      192.168.1.11:8080
    Retourne: [{"name":"CAM1","ip":"192.168.1.10","port":8080,"raw":"..."}, ...]
    """
    ip_file_path = BASE_DIR / "ip_list.txt"
    entries = []
    try:
        if not ip_file_path.exists():
            return JSONResponse({"success": True, "entries": entries})

        with open(ip_file_path, "r") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                parts = raw.split(":")
                if len(parts) == 3:
                    name, ip, port = parts
                elif len(parts) == 2:
                    name = None
                    ip, port = parts
                else:
                    # fallback: whole line as ip, no port
                    name = None
                    ip = raw
                    port = None

                try:
                    port_int = int(port) if port else None
                except Exception:
                    port_int = None

                entries.append({
                    "name": name,
                    "ip": ip,
                    "port": port_int,
                    "raw": raw
                })

        return JSONResponse({"success": True, "entries": entries})

    except Exception as e:
        print(f"❌ Erreur lecture ip_list.txt: {e}")
        return JSONResponse({"success": False, "error": str(e), "entries": []}, status_code=500)

# NOTE: Removed duplicate direct start of `HikvisionStreamThread()` here.
# `start_rtsp_thread()` is the canonical way to (re)start the RTSP thread
# and will stop any existing thread before creating a new one. Leaving
# a second direct start here caused multiple threads to run with stale
# configuration. If the frontend updates the selected device it must
# call `/api/save_device_config` which calls `start_rtsp_thread()`.

async def generate_rtsp_frames():
    """Générateur de frames RTSP pour streaming HTTP"""
    no_frame_count = 0
    
    while True:
        try:
            frame_bytes = frame_queue.get(timeout=1.0)
            no_frame_count = 0
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            await asyncio.sleep(0.01)
                   
        except queue.Empty:
            no_frame_count += 1
            
            if no_frame_count > 3:
                status_msg = "⏳ Connexion RTSP en cours..." if not streaming_active else "📡 Attente frames..."
                yield (b'--frame\r\n'
                       b'Content-Type: text/plain\r\n\r\n' + 
                       status_msg.encode() + b'\r\n')
            
            await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"❌ Erreur génération: {e}")
            await asyncio.sleep(1)

class ImageData(BaseModel):
    image: str

class CameraURL(BaseModel):
    url: str

def read_ip_list() -> Dict[str, List[str]]:
    ip_dict = {}
    if not os.path.exists(ip_file):
        return ip_dict
    with open(ip_file, "r") as f:
        for line in f:
            line = line.strip()
            if ":" in line:
                port, ips = line.split(":", 1)
                ip_list = [ip.strip() for ip in ips.split(",") if ip.strip()]
                ip_dict[port] = ip_list
    return ip_dict

def write_ip_list(ip_dict: Dict[str, List[str]]):
    with open(ip_file, "w") as f:
        for port, ips in ip_dict.items():
            f.write(f"{port}:{','.join(ips)}\n")

def get_selected_ip():
    if os.path.exists("selected_ip.txt"):
        with open("selected_ip.txt", "r") as f:
            return f.read().strip()
    return ""

def set_selected_ip(ip):
    with open("selected_ip.txt", "w") as f:
        f.write(ip)

# =================== Routes Hikvision Manager ===================
@app.post("/add_user_with_photo")
async def add_user_with_photo(
    request: Request,
    device_ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    employee_no: str = Form(...),
    name: str = Form(...),
    cin: str = Form(""),            # NOUVEAU
    email: str = Form(""),
    telephone: str = Form(""),
    address: str = Form(""),
    carte_number: str = Form(""),   # NOUVEAU
    fingerprint_id: str = Form(""), # NOUVEAU
    user_type: str = Form("normal"),
    valid_days: int = Form(365),
    door_rights: str = Form("1"),
    public_base_url: Optional[str] = Form(None),
    photo: UploadFile = File(...)
):
    results = {
        "employee_no": employee_no, 
        "name": name,
        "user_created_hikvision": False,
        "user_created_mongodb": False,
        "photo_uploaded": False, 
        "photo_verified": False
    }
    
    try:
        manager = HikvisionManager(device_ip, username, password)
        
        # 1. Créer dans Hikvision
        print(f"[1/4] Creating user in Hikvision: {employee_no} - {name}")
        user_result = manager.add_user(employee_no, name, user_type, valid_days, door_rights)
        results["user_created_hikvision"] = user_result.get("success", False)
        results["hikvision_response"] = user_result
        
        if not results["user_created_hikvision"]:
            return JSONResponse({
                "status": "error", 
                "message": "Échec création utilisateur dans Hikvision", 
                "details": results
            }, status_code=400)

        # 2. Sauvegarder et optimiser la photo
        print(f"[2/4] Saving photo for {employee_no}")
        ext = os.path.splitext(photo.filename)[1] or ".jpg"
        filename = f"{employee_no}_{int(time.time())}_{secrets.token_hex(4)}{ext}"
        filepath = UPLOAD_DIR / filename
        
        content = await photo.read()
        
        try:
            img = Image.open(io.BytesIO(content))
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            max_size = 800
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            img.save(filepath, 'JPEG', quality=85, optimize=True)
        except Exception as e:
            print(f"Error optimizing photo: {e}")
            with filepath.open("wb") as f:
                f.write(content)

        # 3. Upload photo vers Hikvision
        if public_base_url:
            base = public_base_url.rstrip("/")
        else:
            base = f"http://{PUBLIC_IP}:{PUBLIC_PORT}"
        
        photo_url = f"{base}/static/uploads/{filename}"
        results["photo_url"] = photo_url
        
        print(f"[3/4] Uploading photo to Hikvision...")
        time.sleep(2)
        
        photo_result = manager.upload_face_photo(employee_no, photo_url)
        results["photo_uploaded"] = photo_result.get("success", False)
        
        if not results["photo_uploaded"]:
            print(f"URL upload failed, trying base64...")
            time.sleep(2)
            photo_result_b64 = manager.upload_face_photo_base64(employee_no, str(filepath))
            results["photo_uploaded"] = photo_result_b64.get("success", False)
        
        time.sleep(3)
        results["photo_verified"] = manager.verify_face(employee_no)

        # 4. SYNCHRONISER AVEC MONGODB
        print(f"[4/4] Synchronizing with MongoDB...")
        try:
            user_document = {
                "employee_no": employee_no,
                "name": name,
                "cin": cin,                     # NOUVEAU
                "email": email,
                "telephone": telephone,
                "address": address,
                "carte_number": carte_number,   # NOUVEAU
                "fingerprint_id": fingerprint_id, # NOUVEAU
                "user_type": user_type,
                "valid_days": valid_days,
                "photo_url": photo_url,
                "photo_local_path": str(filepath),
                "hikvision_device_ip": device_ip,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "synced_with_hikvision": results["user_created_hikvision"],
                "has_face_photo": results["photo_verified"]
            }
            
            mongo_result = await users_collection.insert_one(user_document)
            results["user_created_mongodb"] = True
            results["mongodb_id"] = str(mongo_result.inserted_id)
            print(f"✅ MongoDB sync successful: {results['mongodb_id']}")
            
        except Exception as mongo_error:
            print(f"❌ MongoDB sync error: {mongo_error}")
            results["user_created_mongodb"] = False
            results["mongodb_error"] = str(mongo_error)

        # 5. Retourner le résultat
        if results["user_created_hikvision"] and results["user_created_mongodb"]:
            return JSONResponse({
                "status": "success", 
                "message": f"✅ User {name} created in both Hikvision and MongoDB", 
                "details": results
            })
        elif results["user_created_hikvision"]:
            return JSONResponse({
                "status": "partial_success", 
                "message": f"⚠️ User {name} created in Hikvision but MongoDB sync failed", 
                "details": results
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": "Failed to create user",
                "details": results
            }, status_code=500)
            
    except Exception as e:
        import traceback
        print(f"Error in add_user_with_photo: {e}")
        traceback.print_exc()
        return JSONResponse({
            "status": "error", 
            "message": str(e), 
            "details": results
        }, status_code=500)
@app.get("/api/hik_users_with_mongo")
async def api_hik_users_with_mongo(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    port: int = Query(80)
):
    if not device_ip or not username or not password:
        return JSONResponse({
            "error": "device_ip, username and password are required"
        }, status_code=400)

    try:
        # Récupérer depuis Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        hik_users = manager.get_all_users()
        
        # Récupérer depuis MongoDB
        mongo_users_cursor = users_collection.find({
            "hikvision_device_ip": device_ip
        })
        mongo_users = {}
        async for mu in mongo_users_cursor:
            employee_no = mu.get("employee_no")
            if employee_no:
                mongo_users[employee_no] = {
                    "cin": mu.get("cin", ""),               # NOUVEAU
                    "email": mu.get("email", ""),
                    "telephone": mu.get("telephone", ""),
                    "address": mu.get("address", ""),
                    "carte_number": mu.get("carte_number", ""),    # NOUVEAU
                    "fingerprint_id": mu.get("fingerprint_id", ""), # NOUVEAU
                    "photo_url": mu.get("photo_url", ""),
                    "mongodb_id": str(mu.get("_id", ""))
                }
        
        # Fusionner les données
        enriched_users = []
        for hik_user in hik_users:
            emp_no = hik_user.get("employeeNo") or hik_user.get("employeeid") or hik_user.get("id")
            
            if emp_no and emp_no in mongo_users:
                mongo_data = mongo_users[emp_no]
                hik_user["cin"] = mongo_data.get("cin", "")              # NOUVEAU
                hik_user["email"] = mongo_data.get("email", "")
                hik_user["telephone"] = mongo_data.get("telephone", "")
                hik_user["address"] = mongo_data.get("address", "")
                hik_user["carte_number"] = mongo_data.get("carte_number", "")    # NOUVEAU
                hik_user["fingerprint_id"] = mongo_data.get("fingerprint_id", "") # NOUVEAU
                hik_user["has_mongo_data"] = True
            else:
                hik_user["has_mongo_data"] = False
            
            enriched_users.append(hik_user)
        
        return {"users": enriched_users}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "error": "request failed", 
            "detail": str(e)
        }, status_code=500)

# 3. ROUTE POUR METTRE À JOUR (SYNC HIKVISION + MONGODB)
# =======================================================

@app.put("/api/hik_user")
async def api_update_hik_user(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    employee_no: str = Query(...),
    name: Optional[str] = Query(None),
    cin: Optional[str] = Query(None),            # NOUVEAU
    email: Optional[str] = Query(None),
    telephone: Optional[str] = Query(None),
    address: Optional[str] = Query(None),
    carte_number: Optional[str] = Query(None),   # NOUVEAU
    fingerprint_id: Optional[str] = Query(None), # NOUVEAU
    user_type: Optional[str] = Query(None),
    valid_days: Optional[int] = Query(None),
    door_rights: Optional[str] = Query(None),
    port: int = Query(80)
):
    if not device_ip or not username or not password or not employee_no:
        return JSONResponse({
            "error": "device_ip, username, password and employee_no required"
        }, status_code=400)
    
    try:
        # 1. Mettre à jour Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        result = manager.update_user(employee_no, name, user_type, valid_days, door_rights)
        
        # 2. Mettre à jour MongoDB
        update_data = {"updated_at": datetime.utcnow()}
        if name is not None:
            update_data["name"] = name
        if cin is not None:                     # NOUVEAU
            update_data["cin"] = cin
        if email is not None:
            update_data["email"] = email
        if telephone is not None:
            update_data["telephone"] = telephone
        if address is not None:
            update_data["address"] = address
        if carte_number is not None:           # NOUVEAU
            update_data["carte_number"] = carte_number
        if fingerprint_id is not None:         # NOUVEAU
            update_data["fingerprint_id"] = fingerprint_id
        if user_type is not None:
            update_data["user_type"] = user_type
        
        mongo_result = await users_collection.update_one(
            {"employee_no": employee_no, "hikvision_device_ip": device_ip},
            {"$set": update_data}
        )
        
        result["mongodb_updated"] = mongo_result.modified_count > 0
        
        status = 200 if result.get("success") else 400
        return JSONResponse(result, status_code=status)
        
    except Exception as e:
        return JSONResponse({
            "error": "update failed", 
            "detail": str(e)
        }, status_code=500)

# 4. ROUTE POUR SUPPRIMER (SYNC HIKVISION + MONGODB)
# ===================================================

@app.delete("/api/hik_user_with_mongo")
async def api_delete_hik_user_with_mongo(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    employee_no: str = Query(...),
    port: int = Query(80)
):
    """
    Suppression avec synchronisation Hikvision + MongoDB
    """
    if not device_ip or not username or not password or not employee_no:
        return JSONResponse({
            "error": "All parameters required"
        }, status_code=400)
    
    try:
        results = {
            "hikvision_deleted": False,
            "mongodb_deleted": False
        }
        
        # Supprimer de Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        hik_result = manager.delete_user(employee_no)
        results["hikvision_deleted"] = hik_result.get("success", False)
        
        # Supprimer de MongoDB
        mongo_result = await users_collection.delete_one({
            "employee_no": employee_no,
            "hikvision_device_ip": device_ip
        })
        results["mongodb_deleted"] = mongo_result.deleted_count > 0
        
        status_code = 200 if results["hikvision_deleted"] else 400
        return JSONResponse(results, status_code=status_code)
        
    except Exception as e:
        return JSONResponse({
            "error": "delete failed", 
            "detail": str(e)
        }, status_code=500)
@app.post("/register_with_sync", response_class=HTMLResponse)
async def register_user_with_sync(
    request: Request,
    employee_no: str = Form(...),
    name: str = Form(...),
    cin: str = Form(...),
    telephone: str = Form(...),
    email: str = Form(...),
    address: str = Form(""),
    user_type: str = Form("normal"),
    photos: List[UploadFile] = File(...)
):
    try:
        # 🆕 Configuration FLEXIBLE
        form_data = await request.form()
        device_ip = form_data.get("device_ip", "0.0.0.0")  # IP par défaut
        username = form_data.get("username", "admin")
        password = form_data.get("password", "Eni20230")
        port = int(form_data.get("port", 80))
        
        # 1. Upload photos vers Cloudinary
        folder_name = f"faces/{name}_{cin}"
        photo_urls = []
        
        for photo in photos:
            contents = await photo.read()
            result = cloudinary.uploader.upload(
                contents,
                folder=folder_name,
                public_id=os.path.splitext(photo.filename)[0],
                overwrite=True
            )
            photo_urls.append(result["secure_url"])
        
        # 2. Créer dans Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        
        # 🆕 Essayer plusieurs fois si échec
        hik_result = None
        for attempt in range(2):
            hik_result = manager.add_user(employee_no, name, user_type, 365, "1")
            if hik_result.get("success"):
                break
            time.sleep(1)
        
        hikvision_created = hik_result.get("success", False) if hik_result else False
        
        # 3. Upload photo vers Hikvision
        photo_uploaded = False
        if hikvision_created and photo_urls:
            time.sleep(2)  # Attendre que l'utilisateur soit bien créé
            photo_result = manager.upload_face_photo(employee_no, photo_urls[0])
            if not photo_result.get("success"):
                # Essayer base64
                # Télécharger la photo depuis Cloudinary
                img_response = requests.get(photo_urls[0])
                temp_path = UPLOAD_DIR / f"temp_{employee_no}.jpg"
                with open(temp_path, "wb") as f:
                    f.write(img_response.content)
                
                photo_result = manager.upload_face_photo_base64(employee_no, str(temp_path))
                temp_path.unlink(missing_ok=True)
            
            photo_uploaded = photo_result.get("success", False)
        
        # 4. Insérer dans MongoDB
        user_doc = {
            "employee_no": employee_no,
            "name": name,
            "cin": cin,
            "telephone": telephone,
            "email": email,
            "address": address,
            "carte_number": "",
            "fingerprint_id": "",
            "user_type": user_type,
            "valid_days": 365,
            "photos": photo_urls,
            "photo_url": photo_urls[0] if photo_urls else "",
            "hikvision_device_ip": device_ip,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "synced_with_hikvision": hikvision_created,
            "has_face_photo": photo_uploaded
        }
        
        mongo_result = await users_collection.insert_one(user_doc)
        
        # Message détaillé
        status_parts = []
        if hikvision_created:
            status_parts.append("✅ Hikvision")
        else:
            status_parts.append(f"❌ Hikvision: {hik_result.get('error', 'Unknown error')}")
            
        status_parts.append("✅ MongoDB")
        
        if photo_uploaded:
            status_parts.append("✅ Photo")
        
        message = f"User {name} | {' | '.join(status_parts)}"
        
        return templates.TemplateResponse(
            "ajout_user7.html",
            {"request": request, "message": message}
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse(
            "ajout_user7.html",
            {"request": request, "error": f"❌ {str(e)}"}
        )
@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse("ajout_user7.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
async def register_user(request: Request, name: str = Form(...), cin: str = Form(...), telephone: str = Form(...), email: str = Form(...), photos: List[UploadFile] = File(...)):
    folder_name = f"faces/{name}_{cin}"
    photo_urls = []
    for photo in photos:
        contents = await photo.read()
        result = cloudinary.uploader.upload(contents, folder=folder_name, public_id=os.path.splitext(photo.filename)[0], overwrite=True)
        photo_urls.append(result["secure_url"])
    await users_collection.insert_one({"name": name, "cin": cin, "telephone": telephone, "email": email, "photos": photo_urls, "created_at": datetime.utcnow()})
    return templates.TemplateResponse("ajout_user7.html", {"request": request, "message": f"{len(photo_urls)} photo(s) enregistrée(s) pour {name} (CIN: {cin})"})
    
@app.post("/upload_face_only")
async def upload_face_only(
    request: Request,
    device_ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    employee_no: str = Form(...),
    public_base_url: Optional[str] = Form(None),
    photo: UploadFile = File(...)
):
    try:
        ext = os.path.splitext(photo.filename)[1] or ".jpg"
        filename = f"{employee_no}_{int(time.time())}_{secrets.token_hex(4)}{ext}"
        filepath = UPLOAD_DIR / filename
        
        content = await photo.read()
        try:
            img = Image.open(io.BytesIO(content))
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            max_size = 800
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            img.save(filepath, 'JPEG', quality=85, optimize=True)
        except Exception as e:
            print(f"Error optimizing photo: {e}, saving original")
            with filepath.open("wb") as f:
                f.write(content)

        # Utiliser l'IP publique configurée
        if public_base_url:
            base = public_base_url.rstrip("/")
        else:
            base = f"http://{PUBLIC_IP}:{PUBLIC_PORT}"
        
        photo_url = f"{base}/static/uploads/{filename}"

        manager = HikvisionManager(device_ip, username, password)
        result = manager.upload_face_photo(employee_no, photo_url)
        
        if not result.get("success"):
            time.sleep(2)
            result = manager.upload_face_photo_base64(employee_no, str(filepath))
        
        time.sleep(2)
        verified = manager.verify_face(employee_no)

        return JSONResponse({"status": "success", "photo_url": photo_url, "upload_result": result, "verified": verified})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/add_user")
async def api_add_user(
    device_ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    employee_no: str = Form(...),
    name: str = Form(...),
    user_type: str = Form("normal"),
    valid_days: int = Form(365),
    door_rights: str = Form("1"),
    port: int = Form(80)
):
    if not device_ip or not username or not password or not employee_no:
        return JSONResponse({"error": "device_ip, username, password and employee_no are required"}, status_code=400)
    try:
        manager = HikvisionManager(device_ip, username, password, port)
        result = manager.add_user(employee_no, name, user_type, valid_days, door_rights)
        status = 200 if result.get("success") else 400
        return JSONResponse(result, status_code=status)
    except Exception as e:
        return JSONResponse({"error": "add failed", "detail": str(e)}, status_code=500)

@app.get("/api/hik_users")
async def api_hik_users(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    port: int = Query(80)
):
    if not device_ip or not username or not password:
        return JSONResponse({"error": "device_ip, username and password are required"}, status_code=400)

    try:
        manager = HikvisionManager(device_ip, username, password, port)
        users = manager.get_all_users()
        return {"users": users}
    except Exception as e:
        return JSONResponse({"error": "request failed", "detail": str(e)}, status_code=500)

@app.delete("/api/hik_user")
async def api_delete_hik_user(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    employee_no: str = Query(...),
    port: int = Query(80)
):
    if not device_ip or not username or not password or not employee_no:
        return JSONResponse({"error": "device_ip, username, password and employee_no are required"}, status_code=400)
    try:
        results = {
            "employee_no": employee_no,
            "hikvision_deleted": False,
            "mongodb_deleted": False
        }
        
        # 1. Supprimer de Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        hik_result = manager.delete_user(employee_no)
        results["hikvision_deleted"] = hik_result.get("success", False)
        
        # 2. 🆕 SUPPRIMER DE MONGODB AUSSI
        mongo_result = await users_collection.delete_one({
            "employee_no": employee_no,
            "hikvision_device_ip": device_ip
        })
        results["mongodb_deleted"] = mongo_result.deleted_count > 0
        
        # Considérer comme succès si au moins l'un est supprimé
        status = 200 if (results["hikvision_deleted"] or results["mongodb_deleted"]) else 400
        
        return JSONResponse(results, status_code=status)
        
    except Exception as e:
        return JSONResponse({"error": "delete failed", "detail": str(e)}, status_code=500)
"""
@app.get("/api/user_photo")
async def api_user_photo(
    employee_no: str,
    request: Request,
    public_base_url: Optional[str] = None
):
    try:
        for f in UPLOAD_DIR.glob(f"{employee_no}_*"):
            # Utiliser l'IP publique configurée
            if public_base_url:
                base = public_base_url.rstrip("/")
            else:
                base = f"http://{PUBLIC_IP}:{PUBLIC_PORT}"
            return {"photo_url": f"{base}/static/uploads/{f.name}"}
        return {"photo_url": None}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
"""
@app.get("/api/user_photo")
async def api_user_photo(
    employee_no: str,
    request: Request,
    public_base_url: Optional[str] = None
):
    try:
        # 🆕 Vérifier le cache d'abord
        cache_key = employee_no
        if cache_key in PHOTO_CACHE:
            cached_data, cached_time = PHOTO_CACHE[cache_key]
            if datetime.now() - cached_time < PHOTO_CACHE_DURATION:
                return cached_data
        
        # Chercher dans les fichiers locaux
        for f in UPLOAD_DIR.glob(f"{employee_no}_*"):
            if public_base_url:
                base = public_base_url.rstrip("/")
            else:
                base = f"http://{PUBLIC_IP}:{PUBLIC_PORT}"
            
            result = {"photo_url": f"{base}/static/uploads/{f.name}"}
            PHOTO_CACHE[cache_key] = (result, datetime.now())
            return result
        
        result = {"photo_url": None}
        PHOTO_CACHE[cache_key] = (result, datetime.now())
        return result
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)  
@app.get("/api/diagnostic")
async def api_diagnostic(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    employee_no: Optional[str] = Query(None)
):
    try:
        manager = HikvisionManager(device_ip, username, password)
        
        results = {
            "device_info": {
                "ip": device_ip,
                "base_url": manager.base_url
            },
            "capabilities": manager.get_face_lib_capability(),
            "tests": []
        }
        
        if employee_no:
            users = manager.get_all_users()
            user_exists = any(u.get("employeeNo") == employee_no for u in users)
            results["user_exists"] = user_exists
            results["face_verified"] = manager.verify_face(employee_no) if user_exists else False
        
        return JSONResponse(results)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/select_ip")
async def select_ip(request: Request):
    global CAM_URL
    form = await request.form()
    selected_ip = form.get("selected_ip")
    if selected_ip:
        CAM_URL = selected_ip
        set_selected_ip(selected_ip)
        return {"message": "IP enregistrée avec succès"}
    return {"error": "Aucune IP fournie"}

@app.get("/get_ip")
async def get_ip(request: Request):
    global CAM_URL
    ip = get_selected_ip()
    CAM_URL = ip
    return JSONResponse({'ip': ip})    

# =================== Routes Vidéo ===================
@app.get("/video_feed_rtsp")
def video_feed_rtsp():
    """Endpoint pour le flux RTSP Hikvision"""
    return StreamingResponse(
        generate_rtsp_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@app.get("/video_status")
async def video_status():
    """Statut du flux RTSP"""
    return {
        "streaming": streaming_active,
        "queue_size": frame_queue.qsize(),
        "camera_url": RTSP_URL.replace("Eni20230", "***"),
        "thread_alive": stream_thread.is_alive()
    }

@app.get("/get_camera_url")
def get_camera_url():
    global CAM_URL
    return {"url": CAM_URL}

@app.get("/modifier_user/{user_id}", response_class=HTMLResponse)
async def get_modifier_user(request: Request, user_id: str):
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    return templates.TemplateResponse("modifier_user.html", {"request": request, "user": user})

@app.post("/modifier_user/{user_id}")
async def post_modifier_user(user_id: str, name: str = Form(...),cin: str = Form(...), email: str = Form(...), telephone: str = Form(...)):
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"name": name, "cin": cin, "email": email, "telephone": telephone}}
    )
    return RedirectResponse("/liste_user", status_code=302)

@app.get("/supprimer_user/{user_id}")
async def supprimer_user(user_id: str):
    await users_collection.delete_one({"_id": ObjectId(user_id)})
    return RedirectResponse("/liste_user", status_code=302)

# =================== Reconnaissance faciale ===================
known_face_encodings = []
known_face_names = []
known_faces_dir = "known_faces"

if os.path.exists(known_faces_dir):
    for person_name in os.listdir(known_faces_dir):
        person_dir = os.path.join(known_faces_dir, person_name)
        if os.path.isdir(person_dir):
            for filename in os.listdir(person_dir):
                if filename.endswith((".jpg", ".png")):
                    image = face_recognition.load_image_file(os.path.join(person_dir, filename))
                    encodings = face_recognition.face_encodings(image)
                    if encodings:
                        known_face_encodings.append(encodings[0])
                        known_face_names.append(person_name)

@app.post("/capture-image")
async def save_captured_image(data: ImageData):
    try:
        image_data = data.image.split("base64,")[-1]
        decoded_image = base64.b64decode(image_data)
        file_name = f"SARY/Image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        with open(file_name, "wb") as f:
            f.write(decoded_image)
        result = cloudinary.uploader.upload(file_name, folder="images")
        url = result["secure_url"]
        await images_collection.insert_one({"image_url": url, "created_at": datetime.utcnow()})
        return {"message": "Image enregistrée", "url": url}
    except Exception as e:
        return {"error": str(e)}

@app.get("/face_status")
def get_face_status():
    return {"name": last_recognized_name}

def gen_frames():
    """Générateur de frames pour caméra IP (ESP32/webcam)"""
    global last_recognized_name, CAM_URL
    frame_count = 0
    process_frame_interval = 3

    while True:
        try:
            url = CAM_URL
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"http://{CAM_URL}/shot.jpg"

            response = requests.get(url, timeout=2)

            if response.status_code != 200 or not response.content:
                continue

            img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                continue

            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            name = "Aucun"

            if frame_count % process_frame_interval == 0:
                face_locations = face_recognition.face_locations(rgb_small_frame)
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                    matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                    name = "Inconnu"
                    face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)

                    if face_distances.size > 0:
                        best_match_index = np.argmin(face_distances)
                        if matches[best_match_index]:
                            name = known_face_names[best_match_index]

                    top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.putText(frame, name, (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

                last_recognized_name = name

            frame_count += 1
            ret, buffer = cv2.imencode('.jpg', frame)

            if not ret:
                continue

            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.05)

        except Exception:
            continue

@app.get("/video_feed")
def video_feed():
    """Endpoint pour caméra IP/ESP32 avec reconnaissance faciale"""
    return StreamingResponse(gen_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/record")
async def record_short_video():
    try:
        filename = f"SARY/record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'XVID'), 10.0, (640, 480))
        for _ in range(30):
            response = requests.get(CAM_URL, timeout=1)
            img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            out.write(frame)
        out.release()
        result = cloudinary.uploader.upload(filename, resource_type="video", folder="videos")
        await videos_collection.insert_one({"video_url": result["secure_url"], "created_at": datetime.utcnow()})
        return {"message": f"Vidéo envoyée : {result['secure_url']}"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/liste_user", response_class=HTMLResponse)
async def user_list(request: Request):
    users_cursor = users_collection.find()
    users = []
    async for user in users_cursor:
        user["_id"] = str(user["_id"])
        users.append(user)
    return templates.TemplateResponse("user_detail7.html", {"request": request, "users": users})

@app.get("/controle", response_class=HTMLResponse)
async def control_view(request: Request):
    ip_dict = read_ip_list()
    return templates.TemplateResponse("c4_2.html", {"request": request,"ports": ip_dict, "cam_url": CAM_URL})

@app.get("/historique", response_class=HTMLResponse)
async def historique(request: Request, date: str = Query(None)):
    images, videos = [], []
    if date:
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            start = datetime(date_obj.year, date_obj.month, date_obj.day)
            end = start.replace(hour=23, minute=59, second=59)
            image_cursor = images_collection.find({"created_at": {"$gte": start, "$lte": end}}).sort("created_at", -1)
            video_cursor = videos_collection.find({"created_at": {"$gte": start, "$lte": end}}).sort("created_at", -1)
        except:
            image_cursor = images_collection.find().sort("created_at", -1)
            video_cursor = videos_collection.find().sort("created_at", -1)
    else:
        image_cursor = images_collection.find().sort("created_at", -1)
        video_cursor = videos_collection.find().sort("created_at", -1)
    async for img in image_cursor:
        img["_id"] = str(img["_id"])
        images.append(img)
    async for vid in video_cursor:
        vid["_id"] = str(vid["_id"])
        videos.append(vid)
    return templates.TemplateResponse("historique.html", {"request": request, "images": images, "videos": videos, "selected_date": date or ""})

@app.get("/live", response_class=HTMLResponse)
async def live_view(request: Request):
    return templates.TemplateResponse("live_view.html", {"request": request})

# =================== RTSP Streaming Proxy ===================
@app.post("/api/guess_stream")
async def api_guess_stream(
    device_ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    channel: int = Form(1)
):
    if not device_ip or not username or not password:
        return JSONResponse({"error": "device_ip, username, password required"}, status_code=400)

    ip = device_ip.strip()
    user = username.strip()
    pwd = password.strip()
    ch = int(channel or 1)

    candidates = []
    candidates.append({
        "type": "rtsp",
        "url": f"rtsp://{user}:{pwd}@{ip}/Streaming/Channels/{ch:02d}01"
    })
    candidates.append({
        "type": "rtsp",
        "url": f"rtsp://{user}:{pwd}@{ip}/Streaming/Channels/{ch:02d}02"
    })
    candidates.append({
        "type": "rtsp",
        "url": f"rtsp://{user}:{pwd}@{ip}/cam/realmonitor?channel={ch}&subtype=0"
    })
    candidates.append({
        "type": "hls",
        "url": f"http://{ip}/ISAPI/Streaming/channels/{ch:02d}01/hls" 
    })

    return {"candidates": candidates}

@app.post("/proxy_stream")
async def proxy_stream(
    device_ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    rtsp_url: Optional[str] = Form(None),
    channel: int = Form(1),
    ffmpeg_path: Optional[str] = Form(None)
):
    if not device_ip and not rtsp_url:
        return JSONResponse({"error": "device_ip or rtsp_url required"}, status_code=400)

    if not rtsp_url:
        ip = device_ip.strip()
        user = username.strip()
        pwd = password.strip()
        ch = int(channel or 1)
        rtsp_url = f"rtsp://{user}:{pwd}@{ip}/Streaming/Channels/{ch:02d}01"

    token = uuid.uuid4().hex[:12]
    out_dir = UPLOAD_DIR.parent / "hls" / token
    out_dir.mkdir(parents=True, exist_ok=True)
    playlist = out_dir / "index.m3u8"

    ffmpeg_exec = ffmpeg_path or "ffmpeg"
    cmd = [
        ffmpeg_exec,
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-c:v", "copy",
        "-c:a", "aac",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments+append_list",
        "-hls_segment_filename", str(out_dir / "seg_%03d.ts"),
        str(playlist)
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return JSONResponse({"error": "ffmpeg not found"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    FFMPEG_PROCS[token] = proc
    hls_url = f"/static/hls/{token}/index.m3u8"
    return {"hls_url": hls_url, "token": token, "rtsp": rtsp_url}

@app.post("/proxy_stop")
async def proxy_stop(token: str = Form(...)):
    proc = FFMPEG_PROCS.get(token)
    if proc:
        try:
            proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        del FFMPEG_PROCS[token]
    return {"stopped": True, "token": token}

# =================== Arrêt propre ===================
@app.on_event("shutdown")
async def shutdown():
    print("🛑 Arrêt du serveur...")
    stream_thread.stop()
    for proc in FFMPEG_PROCS.values():
        try:
            proc.terminate()
        except:
            pass
# =================== Routes API presences ===================        
# =================== NOUVELLES ROUTES API presences ===================        
@app.get("/api/presences", response_class=JSONResponse)
async def api_get_presences(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    validated_only: bool = Query(False)
):
    """
    Récupère les événements de présence avec filtrage
    """
    try:
        manager = HikvisionManager(device_ip, username, password)      
        # Récupérer tous les événements
        all_events = manager.get_all_events()
        
        # Récupérer les utilisateurs de MongoDB pour enrichir les données
        mongo_users = {}
        users_cursor = users_collection.find({"hikvision_device_ip": device_ip})
        async for user in users_cursor:
            emp_id = user.get("employee_no")
            if emp_id:
                mongo_users[emp_id] = {
                    "cin": user.get("cin", ""),
                    "email": user.get("email", ""),
                    "telephone": user.get("telephone", ""),
                    "address": user.get("address", ""),
                    "carte_number": user.get("carte_number", ""),
                    "fingerprint_id": user.get("fingerprint_id", "")
                }
        
        # Filtrer les événements
        filtered_events = []
        for event in all_events:
            # Filtrer par date si spécifié
            if start_date and event["date"] < start_date:
                continue
            if end_date and event["date"] > end_date:
                continue
            
            # Filtrer par employé si spécifié
            if employee_id and event["employee_id"] != employee_id:
                continue
            
            # Filtrer uniquement les validés si demandé
            if validated_only and event["validated"] != "Validé":
                continue
            
            # Enrichir avec les données MongoDB
            emp_id = event["employee_id"]
            if emp_id in mongo_users:
                event.update(mongo_users[emp_id])
                event["has_mongo_data"] = True
            else:
                event["has_mongo_data"] = False
            
            filtered_events.append(event)
        
        # Statistiques
        stats = {
            "total": len(filtered_events),
            "validated": sum(1 for e in filtered_events if e["validated"] == "Validé"),
            "refused": sum(1 for e in filtered_events if e["validated"] == "Refusé"),
            "unique_employees": len(set(e["employee_id"] for e in filtered_events if e["employee_id"] != "-"))
        }
        
        return JSONResponse({
            "success": True,
            "events": filtered_events,
            "stats": stats
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/api/presences/filtered", response_class=JSONResponse)
async def api_get_filtered_presences(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...)
):
    """
    Récupère uniquement les présences des utilisateurs enregistrés dans MongoDB
    """
    try:
        manager = HikvisionManager(device_ip, username, password)
        
        # Récupérer tous les utilisateurs de MongoDB
        mongo_users_dict = {}
        users_cursor = users_collection.find({"hikvision_device_ip": device_ip})
        async for user in users_cursor:
            emp_id = user.get("employee_no")
            name = user.get("name", "")
            if emp_id:
                mongo_users_dict[emp_id] = user
            if name:
                mongo_users_dict[name.upper()] = user
        
        # Récupérer tous les événements
        all_events = manager.get_all_events()
        
        # Filtrer uniquement les utilisateurs présents dans MongoDB
        filtered_events = []
        for event in all_events:
            emp_id = str(event.get("employee_id", "-"))
            name = event.get("name", "-")
            
            found_user = None
            if emp_id in mongo_users_dict:
                found_user = mongo_users_dict[emp_id]
            elif name.upper() in mongo_users_dict:
                found_user = mongo_users_dict[name.upper()]
            
            if found_user:
                # Enrichir avec les données MongoDB
                event["cin"] = found_user.get("cin", "")
                event["email"] = found_user.get("email", "")
                event["telephone"] = found_user.get("telephone", "")
                event["address"] = found_user.get("address", "")
                event["carte_number"] = found_user.get("carte_number", "")
                event["fingerprint_id"] = found_user.get("fingerprint_id", "")
                event["mongodb_id"] = str(found_user.get("_id", ""))
                filtered_events.append(event)
        
        # Statistiques par utilisateur
        user_stats = {}
        for event in filtered_events:
            key = f"{event['employee_id']} - {event['name']}"
            if key not in user_stats:
                user_stats[key] = {
                    "employee_id": event["employee_id"],
                    "name": event["name"],
                    "total": 0,
                    "validated": 0,
                    "refused": 0
                }
            
            user_stats[key]["total"] += 1
            if event["validated"] == "Validé":
                user_stats[key]["validated"] += 1
            else:
                user_stats[key]["refused"] += 1
        
        return JSONResponse({
            "success": True,
            "events": filtered_events,
            "user_stats": list(user_stats.values()),
            "total_events": len(filtered_events),
            "unique_users": len(user_stats)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/presences", response_class=HTMLResponse)
async def presences_page(request: Request):
    """Page d'affichage des présences"""
    return templates.TemplateResponse("presences2.html", {"request": request})

@app.get("/api/presences/export")
async def export_presences_csv(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    filtered_only: bool = Query(True)
):
    """
    Exporte les présences en CSV
    """
    try:
        manager = HikvisionManager(device_ip, username, password)
        all_events = manager.get_all_events()
        
        if filtered_only:
            # Filtrer par utilisateurs MongoDB
            mongo_users = set()
            users_cursor = users_collection.find({"hikvision_device_ip": device_ip})
            async for user in users_cursor:
                emp_id = user.get("employee_no")
                name = user.get("name", "")
                if emp_id:
                    mongo_users.add(emp_id)
                if name:
                    mongo_users.add(name.upper())
            
            filtered = []
            for event in all_events:
                emp_id = str(event.get("employee_id", "-"))
                name = event.get("name", "-").upper()
                if emp_id in mongo_users or name in mongo_users:
                    filtered.append(event)
            
            all_events = filtered
        
        # Créer le CSV
        import io
        output = io.StringIO()
        fieldnames = ['employee_id', 'name', 'method', 'validated', 'date', 'time', 'day', 'period', 'datetime', 'card_no', 'door_no', 'major', 'minor']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_events)
        
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=presences_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

# =================== NOUVELLES ROUTES POUR ÉDITION/SUPPRESSION ===================

@app.put("/api/presence/event")
async def update_presence_event(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    event_datetime: str = Query(...),
    employee_id: str = Query(...),
    new_status: Optional[str] = Query(None),  # "Validé" ou "Refusé"
    new_method: Optional[str] = Query(None),
    notes: Optional[str] = Query(None)
):
    """
    Modifie un événement de présence
    Note: Les événements Hikvision ne peuvent pas être modifiés directement.
    Cette route sauvegarde les modifications dans MongoDB pour suivi.
    """
    try:
        modification_data = {
            "device_ip": device_ip,
            "employee_id": employee_id,
            "original_datetime": event_datetime,
            "modifications": {},
            "modified_at": datetime.utcnow(),
            "modified_by": username
        }
        
        if new_status:
            modification_data["modifications"]["status"] = new_status
        if new_method:
            modification_data["modifications"]["method"] = new_method
        if notes:
            modification_data["modifications"]["notes"] = notes
        
        # Vérifier si une modification existe déjà
        existing = await users_collection.find_one({
            "type": "event_modification",
            "device_ip": device_ip,
            "employee_id": employee_id,
            "original_datetime": event_datetime
        })
        
        if existing:
            # Mettre à jour
            await users_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": modification_data}
            )
        else:
            # Créer nouveau
            modification_data["type"] = "event_modification"
            await users_collection.insert_one(modification_data)
        
        return JSONResponse({
            "success": True,
            "message": "Modification enregistrée",
            "data": modification_data
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.delete("/api/presence/event")
async def delete_presence_event(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    event_datetime: str = Query(...),
    employee_id: str = Query(...)
):
    """
    Marque un événement comme supprimé
    Note: Les événements Hikvision ne peuvent pas être supprimés.
    Cette route les marque comme "supprimés" dans MongoDB.
    """
    try:
        deletion_data = {
            "type": "event_deletion",
            "device_ip": device_ip,
            "employee_id": employee_id,
            "event_datetime": event_datetime,
            "deleted_at": datetime.utcnow(),
            "deleted_by": username,
            "reason": "Supprimé manuellement"
        }
        
        await users_collection.insert_one(deletion_data)
        
        return JSONResponse({
            "success": True,
            "message": "Événement marqué comme supprimé",
            "data": deletion_data
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/api/presence/modifications")
async def get_event_modifications(
    device_ip: str = Query(...),
    employee_id: Optional[str] = Query(None)
):
    """
    Récupère toutes les modifications et suppressions d'événements
    """
    try:
        query = {
            "device_ip": device_ip,
            "type": {"$in": ["event_modification", "event_deletion"]}
        }
        
        if employee_id:
            query["employee_id"] = employee_id
        
        modifications_cursor = users_collection.find(query)
        modifications = []
        
        async for mod in modifications_cursor:
            mod["_id"] = str(mod["_id"])
            modifications.append(mod)
        
        return JSONResponse({
            "success": True,
            "modifications": modifications
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/api/user/photo")
async def get_user_photo_url(
    employee_id: str = Query(...),
    device_ip: str = Query(...)
):
    """
    Récupère l'URL de la photo d'un utilisateur depuis MongoDB
    """
    try:
        user = await users_collection.find_one({
            "employee_no": employee_id,
            "hikvision_device_ip": device_ip
        })
        
        if user and user.get("photo_url"):
            return JSONResponse({
                "success": True,
                "photo_url": user["photo_url"],
                "has_photo": True
            })
        else:
            # Chercher dans le dossier uploads
            photo_files = list(UPLOAD_DIR.glob(f"{employee_id}_*"))
            if photo_files:
                photo_url = f"http://{PUBLIC_IP}:{PUBLIC_PORT}/static/uploads/{photo_files[0].name}"
                return JSONResponse({
                    "success": True,
                    "photo_url": photo_url,
                    "has_photo": True
                })
        
        return JSONResponse({
            "success": True,
            "photo_url": None,
            "has_photo": False
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

# =================== ROUTES CRUD COMPLÈTES (MONGODB + HIKVISION) ===================

# 1. AJOUTER UN UTILISATEUR (CREATE) - Synchronisation automatique
@app.post("/api/users/add")
async def create_user_endpoint(
    device_ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    employee_no: str = Form(...),
    name: str = Form(...),
    cin: str = Form(""),
    email: str = Form(""),
    telephone: str = Form(""),
    address: str = Form(""),
    carte_number: str = Form(""),
    fingerprint_id: str = Form(""),
    user_type: str = Form("normal"),
    valid_days: int = Form(365),
    door_rights: str = Form("1"),
    port: int = Form(80),
    photos: List[UploadFile] = File(None)
):
    """
    Crée un utilisateur dans Hikvision ET MongoDB
    Sauvegarde automatiquement les photos dans known_faces/{nom_utilisateur}/
    """
    import traceback
    from pathlib import Path
    
    print(f"\n{'='*60}")
    print(f"🔧 [/api/users/add] Paramètres reçus:")
    print(f"  - employee_no: {employee_no}")
    print(f"  - name: {name}")
    print(f"  - photos: {len(photos) if photos else 0} fichier(s)")
    print(f"{'='*60}\n")
    
    results = {
        "employee_no": employee_no,
        "name": name,
        "hikvision_created": False,
        "mongodb_created": False,
        "photo_uploaded": False,
        "known_faces_saved": False
    }
    
    try:
        # 1. Créer dans Hikvision
        print(f"🔗 Création Hikvision pour {employee_no} ({name})...")
        manager = HikvisionManager(device_ip, username, password, port)
        hik_result = manager.add_user(employee_no, name, user_type, valid_days, door_rights)
        print(f"   ✅ Résultat Hikvision: {hik_result}")
        results["hikvision_created"] = hik_result.get("success", False)
        
        if not results["hikvision_created"]:
            print(f"   ❌ Hikvision creation failed: {hik_result}")
            return JSONResponse({
                "status": "error",
                "message": "Création échouée dans Hikvision",
                "details": results
            }, status_code=400)
        
        # 2. Traitement des photos
        photo_url = ""
        known_faces_paths = []
        
        if photos and len(photos) > 0 and photos[0].filename:
            print(f"📸 Processing {len(photos)} photo(s)...")
            
            # 2.1 Créer le dossier known_faces/{nom_utilisateur}
            # Nettoyer le nom pour le système de fichiers (supprimer caractères spéciaux)
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name.replace(' ', '_')
            
            known_faces_dir = BASE_DIR / "known_faces" / safe_name
            known_faces_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 Dossier known_faces créé: {known_faces_dir}")
            
            try:
                for idx, photo in enumerate(photos):
                    if not photo.filename:
                        continue
                    
                    # Lire le contenu de la photo
                    content = await photo.read()
                    
                    # 2.2 Sauvegarder dans uploads/ (pour Hikvision)
                    ext = os.path.splitext(photo.filename)[1] or ".jpg"
                    timestamp = int(time.time())
                    filename_upload = f"{employee_no}_{timestamp}_{secrets.token_hex(4)}{ext}"
                    filepath_upload = UPLOAD_DIR / filename_upload
                    
                    # 2.3 Sauvegarder dans known_faces/{nom}/ (pour reconnaissance faciale)
                    filename_known = f"{safe_name}_{idx+1}{ext}"
                    filepath_known = known_faces_dir / filename_known
                    
                    # Optimiser et sauvegarder l'imag
                    
                    try:
                        img = Image.open(io.BytesIO(content))
                        if img.mode in ('RGBA', 'LA', 'P'):
                            img = img.convert('RGB')
                        
                        max_size = 800
                        if img.width > max_size or img.height > max_size:
                            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                        
                        # Sauvegarder dans uploads/
                        img.save(filepath_upload, 'JPEG', quality=85, optimize=True)
                        print(f"   ✅ Photo uploads sauvegardée: {filename_upload}")
                        
                        # Sauvegarder dans known_faces/
                        img.save(filepath_known, 'JPEG', quality=95, optimize=True)
                        known_faces_paths.append(str(filepath_known))
                        print(f"   ✅ Photo known_faces sauvegardée: {filepath_known}")
                        
                    except Exception as img_error:
                        print(f"   ⚠️ Image processing error, saving raw: {img_error}")
                        # Sauvegarder brut si erreur
                        with filepath_upload.open("wb") as f:
                            f.write(content)
                        with filepath_known.open("wb") as f:
                            f.write(content)
                        known_faces_paths.append(str(filepath_known))
                    
                    # URL pour Hikvision (première photo uniquement)
                    if idx == 0:
                        photo_url = f"http://{PUBLIC_IP}:{PUBLIC_PORT}/static/uploads/{filename_upload}"
                
                results["known_faces_saved"] = len(known_faces_paths) > 0
                results["known_faces_paths"] = known_faces_paths
                print(f"   ✅ {len(known_faces_paths)} photo(s) sauvegardée(s) dans known_faces")
                
                # 2.4 Upload vers Hikvision (première photo)
                if photo_url:
                    time.sleep(1)
                    photo_result = manager.upload_face_photo(employee_no, photo_url)
                    
                    if not photo_result.get("success"):
                        print(f"   ⚠️ Photo upload failed, trying base64...")
                        time.sleep(1)
                        photo_result = manager.upload_face_photo_base64(employee_no, str(filepath_upload))
                    
                    results["photo_uploaded"] = photo_result.get("success", False)
                    results["photo_url"] = photo_url
                    print(f"   {'✅' if results['photo_uploaded'] else '❌'} Photo upload Hikvision: {results['photo_uploaded']}")
                
            except Exception as photo_error:
                print(f"   ❌ Photo processing error: {photo_error}")
                traceback.print_exc()
        
        # 3. Créer dans MongoDB
        print(f"💾 Création MongoDB pour {employee_no}...")
        mongo_result = await users_collection.insert_one({
            "employee_no": employee_no,
            "name": name,
            "cin": cin,
            "email": email,
            "telephone": telephone,
            "address": address,
            "carte_number": carte_number,
            "fingerprint_id": fingerprint_id,
            "user_type": user_type,
            "valid_days": valid_days,
            "photo_url": photo_url,
            "known_faces_dir": str(known_faces_dir) if known_faces_paths else "",
            "known_faces_photos": known_faces_paths,
            "hikvision_device_ip": device_ip,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "synced_with_hikvision": True,
            "has_face_photo": results.get("photo_uploaded", False)
        })
        
        results["mongodb_created"] = True
        results["mongodb_id"] = str(mongo_result.inserted_id)
        print(f"   ✅ MongoDB ID: {results['mongodb_id']}")
        
        # 4. Recharger les encodages face_recognition
        print(f"🔄 Rechargement des encodages face_recognition...")
        reload_known_faces()
        
        print(f"\n✅ [/api/users/add] SUCCÈS - {name} créé avec ID {employee_no}")
        print(f"   📁 Photos known_faces: {len(known_faces_paths)}")
        print(f"   📁 Dossier: {known_faces_dir if known_faces_paths else 'N/A'}\n")
        
        return JSONResponse({
            "status": "success",
            "message": f"Utilisateur {name} créé avec succès",
            "details": results
        })
        
    except Exception as e:
        print(f"\n❌ [/api/users/add] ERREUR:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        traceback.print_exc()
        print(f"   Results so far: {results}\n")
        
        return JSONResponse({
            "status": "error",
            "message": f"Erreur lors de la création: {str(e)}",
            "error_type": type(e).__name__,
            "details": results
        }, status_code=500)


# Fonction pour recharger les visages connus
def reload_known_faces():
    """
    Recharge tous les encodages de visages depuis known_faces/
    """
    global known_face_encodings, known_face_names
    
    known_face_encodings.clear()
    known_face_names.clear()
    
    known_faces_dir = BASE_DIR / "known_faces"
    
    if not known_faces_dir.exists():
        print("⚠️ Dossier known_faces n'existe pas")
        return
    
    print(f"🔄 Rechargement des visages depuis {known_faces_dir}...")
    
    for person_dir in known_faces_dir.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_name = person_dir.name
        print(f"   📂 Chargement: {person_name}")
        
        for img_file in person_dir.glob("*"):
            if img_file.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
                continue
            
            try:
                image = face_recognition.load_image_file(str(img_file))
                encodings = face_recognition.face_encodings(image)
                
                if encodings:
                    known_face_encodings.append(encodings[0])
                    known_face_names.append(person_name)
                    print(f"      ✅ {img_file.name}")
                else:
                    print(f"      ⚠️ Aucun visage détecté: {img_file.name}")
                    
            except Exception as e:
                print(f"      ❌ Erreur: {img_file.name} - {e}")
    
    print(f"✅ {len(known_face_encodings)} visages chargés")


# Route pour recharger manuellement les visages
@app.post("/api/reload_faces")
async def api_reload_faces():
    """
    Recharge les encodages de visages depuis known_faces/
    """
    try:
        reload_known_faces()
        return JSONResponse({
            "status": "success",
            "message": f"{len(known_face_encodings)} visages rechargés",
            "total": len(known_face_encodings)
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

# 2. LIRE/LISTER LES UTILISATEURS (READ)
# Ajoutez ce helper pour la sérialisation JSON
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Modifiez la fonction list_users dans main6.py
@app.get("/api/users/list")
async def list_users(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    port: int = Query(80),
    search: Optional[str] = Query(None)
):
    """
    Liste tous les utilisateurs avec fusion des données Hikvision + MongoDB
    """
    try:
        # Récupérer depuis Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        hik_users = manager.get_all_users()
        
        # Récupérer depuis MongoDB
        mongo_users_dict = {}
        async for user in users_collection.find({"hikvision_device_ip": device_ip}):
            # Convertir l'ObjectId en string
            user_dict = dict(user)
            user_dict["_id"] = str(user_dict["_id"])
            # Convertir les datetime en string ISO
            for key, value in user_dict.items():
                if isinstance(value, datetime):
                    user_dict[key] = value.isoformat()
            
            emp_no = user_dict.get("employee_no")
            if emp_no:
                mongo_users_dict[emp_no] = user_dict
        
        # Fusionner
        enriched_users = []
        for hik_user in hik_users:
            emp_no = hik_user.get("employeeNo") or hik_user.get("employeeid")
            
            if emp_no and emp_no in mongo_users_dict:
                mongo_data = mongo_users_dict[emp_no]
                hik_user.update(mongo_data)
                hik_user["has_mongo_data"] = True
            else:
                hik_user["has_mongo_data"] = False
            
            enriched_users.append(hik_user)
        
        # Filtrer si recherche
        if search:
            enriched_users = [
                u for u in enriched_users
                if search.lower() in (u.get("name", "") or "").lower() or
                   search.lower() in (str(u.get("employeeNo", "")) or "").lower()
            ]
        
        # Utiliser le MongoJSONEncoder pour la sérialisation
        return JSONResponse(
            content={
                "status": "success",
                "users": enriched_users,
                "total": len(enriched_users)
            },
            media_type="application/json"
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={
                "status": "error",
                "message": str(e)
            },
            status_code=500,
            media_type="application/json"
        )
# 3. METTRE À JOUR UN UTILISATEUR (UPDATE)
@app.put("/api/users/update")
async def update_user_endpoint(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    employee_no: str = Query(...),
    port: int = Query(80),
    name: Optional[str] = Query(None),
    cin: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    telephone: Optional[str] = Query(None),
    address: Optional[str] = Query(None),
    carte_number: Optional[str] = Query(None),
    fingerprint_id: Optional[str] = Query(None),
    user_type: Optional[str] = Query(None),
    valid_days: Optional[int] = Query(None),
    door_rights: Optional[str] = Query(None)
):
    """
    Met à jour un utilisateur dans Hikvision ET MongoDB
    """
    try:
        results = {"employee_no": employee_no}
        
        # 1. Mettre à jour Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        hik_result = manager.update_user(employee_no, name, user_type, valid_days, door_rights)
        results["hikvision_updated"] = hik_result.get("success", False)
        
        # 2. Mettre à jour MongoDB
        update_data = {"updated_at": datetime.utcnow()}
        
        if name is not None:
            update_data["name"] = name
        if cin is not None:
            update_data["cin"] = cin
        if email is not None:
            update_data["email"] = email
        if telephone is not None:
            update_data["telephone"] = telephone
        if address is not None:
            update_data["address"] = address
        if carte_number is not None:
            update_data["carte_number"] = carte_number
        if fingerprint_id is not None:
            update_data["fingerprint_id"] = fingerprint_id
        if user_type is not None:
            update_data["user_type"] = user_type
        
        mongo_result = await users_collection.update_one(
            {"employee_no": employee_no, "hikvision_device_ip": device_ip},
            {"$set": update_data}
        )
        
        results["mongodb_updated"] = mongo_result.modified_count > 0
        
        return JSONResponse({
            "status": "success",
            "message": "Utilisateur mis à jour",
            "details": results
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

# 4. SUPPRIMER UN UTILISATEUR (DELETE)
@app.delete("/api/users/delete")
async def delete_user_endpoint(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    employee_no: str = Query(...),
    port: int = Query(80)
):
    """
    Supprime un utilisateur de Hikvision ET MongoDB
    """
    try:
        results = {"employee_no": employee_no}
        
        # 1. Supprimer de Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        hik_result = manager.delete_user(employee_no)
        results["hikvision_deleted"] = hik_result.get("success", False)
        
        # 2. Supprimer de MongoDB
        mongo_result = await users_collection.delete_one({
            "employee_no": employee_no,
            "hikvision_device_ip": device_ip
        })
        results["mongodb_deleted"] = mongo_result.deleted_count > 0
        
        return JSONResponse({
            "status": "success",
            "message": "Utilisateur supprimé",
            "details": results
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

# 5. DÉTAIL D'UN UTILISATEUR
@app.get("/api/users/detail")
async def get_user_detail(
    device_ip: str = Query(...),
    employee_no: str = Query(...)
):
    """
    Récupère les détails complets d'un utilisateur
    """
    try:
        user = await users_collection.find_one({
            "employee_no": employee_no,
            "hikvision_device_ip": device_ip
        })
        
        if not user:
            return JSONResponse({
                "status": "error",
                "message": "Utilisateur non trouvé"
            }, status_code=404)
        
        user["_id"] = str(user["_id"])
        
        return JSONResponse({
            "status": "success",
            "user": user
        })
        
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

# =================== ROUTE POUR UPLOAD PHOTO SEULE ===================

@app.post("/api/users/upload-photo")
async def upload_photo_only(
    device_ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    employee_no: str = Form(...),
    port: int = Form(80),
    photo: Optional[UploadFile] = File(None)
):
    """
    Upload uniquement la photo d'un utilisateur existant
    """
    try:
        results = {
            "employee_no": employee_no,
            "photo_uploaded": False
        }
        
        if not photo:
            return JSONResponse({
                "status": "error",
                "message": "Aucune photo fournie",
                "details": results
            }, status_code=400)
        
        # Upload et optimization de la photo
        ext = os.path.splitext(photo.filename)[1] or ".jpg"
        filename = f"{employee_no}_{int(time.time())}_{secrets.token_hex(4)}{ext}"
        filepath = UPLOAD_DIR / filename
        
        content = await photo.read()
        
        try:
            img = Image.open(io.BytesIO(content))
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            max_size = 800
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            img.save(filepath, 'JPEG', quality=85, optimize=True)
        except:
            with filepath.open("wb") as f:
                f.write(content)
        
        photo_url = f"http://{PUBLIC_IP}:{PUBLIC_PORT}/static/uploads/{filename}"
        time.sleep(0.5)
        
        # Upload à Hikvision
        manager = HikvisionManager(device_ip, username, password, port)
        photo_result = manager.upload_face_photo(employee_no, photo_url)
        
        if not photo_result.get("success"):
            time.sleep(0.5)
            photo_result = manager.upload_face_photo_base64(employee_no, str(filepath))
        
        results["photo_uploaded"] = photo_result.get("success", False)
        results["photo_url"] = photo_url
        
        # Mettre à jour MongoDB
        await users_collection.update_one(
            {"employee_no": employee_no, "hikvision_device_ip": device_ip},
            {"$set": {
                "photo_url": photo_url,
                "has_face_photo": results["photo_uploaded"],
                "updated_at": datetime.utcnow()
            }}
        )
        
        return JSONResponse({
            "status": "success",
            "message": "Photo uploadée avec succès",
            "details": results
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

# =================== ROUTE POUR AFFICHER user_detail7.html ===================

@app.get("/user_detail7", response_class=HTMLResponse)
async def show_user_detail7(request: Request):
    """
    Affiche la page de gestion des utilisateurs avec synchronisation complète
    """
    return templates.TemplateResponse("user_detail7.html", {"request": request})

@app.get("/ajout_user7", response_class=HTMLResponse)
async def show_ajout_user7(request: Request):
    """
    Affiche le formulaire d'ajout utilisateur avec synchronisation
    """
    return templates.TemplateResponse("ajout_user7.html", {"request": request})
@app.post("/api/sync/full")
async def full_sync(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    direction: str = Query("both"),  # "mongodb_to_hik", "hik_to_mongodb", "both"
    port: int = Query(80)
):
    """
    Synchronisation complète entre MongoDB et Hikvision
    """
    try:
        results = {}
        
        if direction in ["hik_to_mongodb", "both"]:
            print("🔄 Syncing Hikvision → MongoDB...")
            hik_result = await sync_hikvision_to_mongodb(device_ip, username, password, port)
            results["hikvision_to_mongodb"] = hik_result
        
        if direction in ["mongodb_to_hik", "both"]:
            print("🔄 Syncing MongoDB → Hikvision...")
            mongo_result = await sync_mongodb_to_hikvision(device_ip, username, password, port)
            results["mongodb_to_hikvision"] = mongo_result
        
        return JSONResponse({
            "status": "success",
            "message": "Synchronization completed",
            "results": results
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)   
################################## PRESENCES AVEC ABSENTS ##################################    
################################## PRESENCES AVEC ABSENTS ##################################    
# --- Utilitaire pour rendre JSON-compatible ---
################################## PRESENCES AVEC ABSENTS ##################################    
@app.get("/api/presences/with_absents", response_class=JSONResponse)
async def api_get_presences_with_absents(
    device_ip: str = Query(...),
    username: str = Query(...),
    password: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    """
    Récupère les événements ET identifie les utilisateurs absents
    LOGIQUE: Un utilisateur est ABSENT s'il est dans MongoDB/Hikvision mais PAS dans les événements
    """
    try:
        manager = HikvisionManager(device_ip, username, password)
        
        # ============================================================
        # ÉTAPE 1: RÉCUPÉRER TOUS LES UTILISATEURS ENREGISTRÉS
        # ============================================================
        print("\n" + "="*60)
        print("📋 ÉTAPE 1: RÉCUPÉRATION DES UTILISATEURS ENREGISTRÉS")
        print("="*60)
        
        # 1.1 Utilisateurs MongoDB (CORRECTION: inclure TOUS les champs)
        mongo_users_list = []
        users_cursor = users_collection.find({"hikvision_device_ip": device_ip})
        async for user in users_cursor:
            user_data = {
                # 🔥 IDs (plusieurs variantes pour compatibilité)
                "employee_id": user.get("employee_no", ""),
                "employee_no": user.get("employee_no", ""),
                
                # 🔥 Informations personnelles
                "name": user.get("name", ""),
                "cin": user.get("cin", ""),
                "email": user.get("email", ""),
                "telephone": user.get("telephone", ""),
                "address": user.get("address", ""),
                
                # 🔥 Informations biométriques
                "carte_number": user.get("carte_number", ""),
                "fingerprint_id": user.get("fingerprint_id", ""),
                "photo_url": user.get("photo_url", ""),
                
                # 🔥 Métadonnées
                "hikvision_device_ip": user.get("hikvision_device_ip", ""),
                "created_at": str(user.get("created_at", "")),
                "source": "mongodb"
            }
            mongo_users_list.append(user_data)
            print(f"   ✅ MongoDB: {user_data['employee_no']} - {user_data['name']}")
            print(f"      CIN: {user_data['cin']}, Email: {user_data['email']}, Tel: {user_data['telephone']}")
        
        print(f"\n✅ MongoDB: {len(mongo_users_list)} utilisateurs")
        
        # 1.2 Utilisateurs Hikvision
        hik_users = manager.get_all_users()
        print(f"✅ Hikvision: {len(hik_users)} utilisateurs")
        
        # Créer un dictionnaire des utilisateurs MongoDB par employee_no
        mongo_dict = {u['employee_no']: u for u in mongo_users_list if u['employee_no']}
        
        # Ajouter les utilisateurs Hikvision qui ne sont pas dans MongoDB
        all_registered_users = list(mongo_users_list)
        for hik_user in hik_users:
            emp_no = hik_user.get("employeeNo") or hik_user.get("employeeid") or ""
            name = hik_user.get("name") or hik_user.get("userName") or ""
            
            if emp_no and emp_no not in mongo_dict:
                print(f"   ➕ Ajout Hikvision: {emp_no} - {name}")
                hik_user_data = {
                    "employee_id": emp_no,
                    "employee_no": emp_no,
                    "name": name,
                    "cin": "",
                    "email": "",
                    "telephone": "",
                    "address": "",
                    "carte_number": "",
                    "fingerprint_id": "",
                    "photo_url": "",
                    "hikvision_device_ip": device_ip,
                    "created_at": "",
                    "source": "hikvision"
                }
                all_registered_users.append(hik_user_data)
        
        print(f"\n📊 TOTAL UTILISATEURS ENREGISTRÉS: {len(all_registered_users)}")
        
        # ============================================================
        # ÉTAPE 2: RÉCUPÉRER TOUS LES ÉVÉNEMENTS
        # ============================================================
        print("\n" + "="*60)
        print("📡 ÉTAPE 2: RÉCUPÉRATION DES ÉVÉNEMENTS")
        print("="*60)
        
        all_events = manager.get_all_events()
        print(f"✅ {len(all_events)} événements récupérés")
        
        # Filtrer par date
        filtered_events = []
        for event in all_events:
            if start_date and event["date"] < start_date:
                continue
            if end_date and event["date"] > end_date:
                continue
            filtered_events.append(event)
        
        print(f"📅 {len(filtered_events)} événements après filtrage par date")
        
        # ============================================================
        # ÉTAPE 3: IDENTIFIER QUI EST PRÉSENT DANS LES ÉVÉNEMENTS
        # ============================================================
        print("\n" + "="*60)
        print("🔍 ÉTAPE 3: IDENTIFICATION DES PRÉSENTS")
        print("="*60)
        
        present_employee_ids = set()
        present_names_normalized = set()
        
        for event in filtered_events:
            emp_id = str(event.get("employee_id", "")).strip()
            name = str(event.get("name", "")).strip()
            
            if emp_id and emp_id != "-":
                present_employee_ids.add(emp_id)
            
            if name and name != "-" and name.upper() != "INCONNU":
                present_names_normalized.add(name.upper())
        
        print(f"✅ Présents par ID: {present_employee_ids}")
        print(f"✅ Présents par Nom: {present_names_normalized}")
        
        # ============================================================
        # ÉTAPE 4: IDENTIFIER LES ABSENTS (CORRECTION COMPLÈTE)
        # ============================================================
        print("\n" + "="*60)
        print("❌ ÉTAPE 4: IDENTIFICATION DES ABSENTS")
        print("="*60)
        
        absent_users = []
        present_users_list = []
        
        for user in all_registered_users:
            emp_no = str(user.get("employee_no", "")).strip()
            name = str(user.get("name", "")).strip()
            name_normalized = name.upper()
            
            # Vérifier si présent dans les événements
            is_present = (
                emp_no in present_employee_ids or 
                name_normalized in present_names_normalized
            )
            
            print(f"\n🔍 {emp_no} - {name}")
            print(f"   CIN: {user.get('cin', '-')}")
            print(f"   Email: {user.get('email', '-')}")
            print(f"   Téléphone: {user.get('telephone', '-')}")
            print(f"   ID dans événements? {emp_no in present_employee_ids}")
            print(f"   Nom dans événements? {name_normalized in present_names_normalized}")
            print(f"   ➜ {'PRÉSENT ✅' if is_present else 'ABSENT ❌'}")
            
            if is_present:
                present_users_list.append(user)
            else:
                # 🔥 CORRECTION: Garder TOUTES les informations de l'utilisateur
                absent_user = {
                    "employee_id": emp_no,
                    "employee_no": emp_no,
                    "name": name,
                    "cin": user.get("cin", ""),
                    "email": user.get("email", ""),
                    "telephone": user.get("telephone", ""),
                    "address": user.get("address", ""),
                    "carte_number": user.get("carte_number", ""),
                    "fingerprint_id": user.get("fingerprint_id", ""),
                    "photo_url": user.get("photo_url", ""),
                    "source": user.get("source", ""),
                    "status": "ABSENT"
                }
                absent_users.append(absent_user)
                
                # 🔥 DEBUG: Afficher les données de l'absent
                print(f"   📋 Données absent sauvegardées:")
                print(f"      CIN: {absent_user['cin']}")
                print(f"      Email: {absent_user['email']}")
                print(f"      Téléphone: {absent_user['telephone']}")
                print(f"      Carte: {absent_user['carte_number']}")
                print(f"      Empreinte: {absent_user['fingerprint_id']}")
        
        # ============================================================
        # ÉTAPE 5: ENRICHIR LES ÉVÉNEMENTS
        # ============================================================
        for event in filtered_events:
            emp_id = str(event.get("employee_id", "")).strip()
            
            # Trouver l'utilisateur correspondant
            for user in all_registered_users:
                if user["employee_no"] == emp_id:
                    event["cin"] = user.get("cin", "")
                    event["email"] = user.get("email", "")
                    event["telephone"] = user.get("telephone", "")
                    event["address"] = user.get("address", "")
                    event["carte_number"] = user.get("carte_number", "")
                    event["fingerprint_id"] = user.get("fingerprint_id", "")
                    break
        
        # ============================================================
        # RÉSUMÉ FINAL
        # ============================================================
        print("\n" + "="*60)
        print("📊 RÉSUMÉ FINAL")
        print("="*60)
        print(f"Total utilisateurs enregistrés: {len(all_registered_users)}")
        print(f"Présents dans événements: {len(present_users_list)}")
        print(f"Absents: {len(absent_users)}")
        print(f"\n❌ Liste des ABSENTS avec détails:")
        for user in absent_users:
            print(f"   ID: {user['employee_no']}")
            print(f"   Nom: {user['name']}")
            print(f"   CIN: {user['cin']}")
            print(f"   Email: {user['email']}")
            print(f"   Téléphone: {user['telephone']}")
            print(f"   Carte: {user['carte_number']}")
            print(f"   Empreinte: {user['fingerprint_id']}")
            print(f"   ---")
        print("="*60 + "\n")
        
        # ============================================================
        # ÉTAPE 6: ENREGISTRER DANS evenements2
        # ============================================================
        now = datetime.now()
        date_key = now.strftime("%Y-%m-%d")

        async def save_evenement(user, status):
            filter_query = {
                "employee_no": user.get("employee_no", ""),
                "status": status,
                "date_key": date_key,
                "device_ip": device_ip
            }
            update_doc = {
                "$set": {
                    "employee_no": user.get("employee_no", ""),
                    "name": user.get("name", ""),
                    "cin": user.get("cin", ""),
                    "email": user.get("email", ""),
                    "telephone": user.get("telephone", ""),
                    "carte_number": user.get("carte_number", ""),
                    "fingerprint_id": user.get("fingerprint_id", ""),
                    "status": status,
                    "timestamp": now,
                    "date_key": date_key,
                    "device_ip": device_ip
                }
            }
            await evenements2_collection.update_one(filter_query, update_doc, upsert=True)

        for user in present_users_list:
            await save_evenement(user, "PRESENT")
        for user in absent_users:
            await save_evenement(user, "ABSENT")
        
        print("✅ Présences/absences enregistrées dans evenements2")
        
        # ============================================================
        # STATISTIQUES
        # ============================================================
        stats = {
            "total_events": len(filtered_events),
            "total_registered_users": len(all_registered_users),
            "present_users": len(present_users_list),
            "absent_users": len(absent_users)
        }

        # ============================================================
        # RETOUR FINAL API
        # ============================================================
        return JSONResponse({
            "success": True,
            "events": filtered_events,
            "users": all_registered_users,
            "present_users": present_users_list,
            "absent_users": absent_users,
            "stats": stats
        })

    except Exception as e:
        import traceback
        print(f"\n❌ ERREUR CRITIQUE:")
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "absent_users": [],
            "events": []
        }, status_code=500)

############ Export donnez
@app.get("/api/attendance/by_status", response_class=JSONResponse)
async def get_attendance_by_status(
    status: str = Query(..., regex="^(present|absent|all)$"),
    date: str = Query(...),  # format "YYYY-MM-DD"
):
    """
    Récupère les utilisateurs par statut et date depuis la collection evenements2
    """
    try:
        # Convertir la date en objet datetime
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        start = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0)
        end   = datetime(date_obj.year, date_obj.month, date_obj.day, 23, 59, 59)

        query = {"timestamp": {"$gte": start, "$lte": end}}
        if status != "all":
            query["status"] = status.upper()  # PRESENT ou ABSENT

        cursor = evenements2_collection.find(query)
        results = []
        async for doc in cursor:
            results.append({
                "employee_no": doc.get("employee_no", ""),
                "name": doc.get("name", ""),
                "status": doc.get("status", ""),
                "timestamp": doc.get("timestamp").strftime("%d/%m/%Y - %H:%M:%S")
            })

        return JSONResponse({"success": True, "results": results})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e), "results": []}, status_code=500)
# Ajouter ces routes dans main6.py

@app.get("/inscription", response_class=HTMLResponse)
async def external_registration_page(request: Request):
    """
    Page d'inscription externe pour nouveaux utilisateurs
    Accessible sans authentification
    """
    return templates.TemplateResponse("user_page/inscription3.html", {"request": request})



@app.get("/api/config/device")
async def get_device_config_public():
    """
    Retourne la configuration du device actuel pour les utilisateurs externes
    (version sécurisée sans mot de passe)
    """
    return JSONResponse({
        "device_ip": SELECTED_DEVICE_CONFIG.get("ip", "192.168.101.18"),
        "port": SELECTED_DEVICE_CONFIG.get("port", 80),
        "available": True
    })


@app.post("/api/users/register_external")
async def register_external_user(
    employee_no: str = Form(...),
    name: str = Form(...),
    cin: str = Form(""),
    email: str = Form(""),
    telephone: str = Form(""),
    address: str = Form(""),
    photos: List[UploadFile] = File(...)
):
    """
    Inscription publique pour utilisateurs externes
    Utilise les credentials admin par défaut
    """
    
    # Utiliser la configuration par défaut
    device_ip = SELECTED_DEVICE_CONFIG.get("ip", "192.168.101.18")
    username = SELECTED_DEVICE_CONFIG.get("username", "admin")
    password = SELECTED_DEVICE_CONFIG.get("password", "Eni20230")
    port = SELECTED_DEVICE_CONFIG.get("port", 80)
    
    print(f"\n{'='*60}")
    print(f"🌐 [INSCRIPTION EXTERNE]")
    print(f"  - Utilisateur: {name} ({employee_no})")
    print(f"  - Photos: {len(photos)}")
    print(f"{'='*60}\n")
    
    results = {
        "employee_no": employee_no,
        "name": name,
        "hikvision_created": False,
        "mongodb_created": False,
        "photo_uploaded": False,
        "known_faces_saved": False
    }
    
    try:
        # 1. Créer dans Hikvision
        print(f"🔗 Création Hikvision...")
        manager = HikvisionManager(device_ip, username, password, port)
        hik_result = manager.add_user(employee_no, name, "normal", 365, "1")
        results["hikvision_created"] = hik_result.get("success", False)
        
        if not results["hikvision_created"]:
            raise Exception("Échec création dans Hikvision")
        
        # 2. Traitement des photos
        photo_url = ""
        known_faces_paths = []
        
        if photos and len(photos) > 0:
            # Créer dossier known_faces/{nom}
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name.replace(' ', '_')
            
            known_faces_dir = BASE_DIR / "known_faces" / safe_name
            known_faces_dir.mkdir(parents=True, exist_ok=True)
            
            for idx, photo in enumerate(photos):
                if not photo.filename:
                    continue
                
                content = await photo.read()
                ext = os.path.splitext(photo.filename)[1] or ".jpg"
                
                # Sauvegarder dans uploads/
                timestamp = int(time.time())
                filename_upload = f"{employee_no}_{timestamp}_{secrets.token_hex(4)}{ext}"
                filepath_upload = UPLOAD_DIR / filename_upload
                
                # Sauvegarder dans known_faces/
                filename_known = f"{safe_name}_{idx+1}{ext}"
                filepath_known = known_faces_dir / filename_known
                
                # Optimiser l'image
                import io
                from PIL import Image
                
                try:
                    img = Image.open(io.BytesIO(content))
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    
                    max_size = 800
                    if img.width > max_size or img.height > max_size:
                        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    
                    img.save(filepath_upload, 'JPEG', quality=85, optimize=True)
                    img.save(filepath_known, 'JPEG', quality=95, optimize=True)
                    known_faces_paths.append(str(filepath_known))
                    
                except Exception as e:
                    print(f"⚠️ Erreur optimisation: {e}")
                    with filepath_upload.open("wb") as f:
                        f.write(content)
                    with filepath_known.open("wb") as f:
                        f.write(content)
                    known_faces_paths.append(str(filepath_known))
                
                # URL pour Hikvision (première photo)
                if idx == 0:
                    photo_url = f"http://{PUBLIC_IP}:{PUBLIC_PORT}/static/uploads/{filename_upload}"
            
            results["known_faces_saved"] = len(known_faces_paths) > 0
            
            # Upload vers Hikvision
            if photo_url:
                time.sleep(1)
                photo_result = manager.upload_face_photo(employee_no, photo_url)
                
                if not photo_result.get("success"):
                    time.sleep(1)
                    photo_result = manager.upload_face_photo_base64(employee_no, str(filepath_upload))
                
                results["photo_uploaded"] = photo_result.get("success", False)
        
        # 3. Sauvegarder dans MongoDB
        mongo_result = await users_collection.insert_one({
            "employee_no": employee_no,
            "name": name,
            "cin": cin,
            "email": email,
            "telephone": telephone,
            "address": address,
            "carte_number": "",
            "fingerprint_id": "",
            "user_type": "normal",
            "valid_days": 365,
            "photo_url": photo_url,
            "known_faces_dir": str(known_faces_dir) if known_faces_paths else "",
            "known_faces_photos": known_faces_paths,
            "hikvision_device_ip": device_ip,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "synced_with_hikvision": True,
            "has_face_photo": results["photo_uploaded"],
            "registration_source": "external"
        })
        
        results["mongodb_created"] = True
        results["mongodb_id"] = str(mongo_result.inserted_id)
        
        # 4. Recharger les visages
        reload_known_faces()
        
        print(f"✅ Inscription externe réussie: {name}")
        
        return JSONResponse({
            "status": "success",
            "message": f"Inscription réussie pour {name}",
            "details": results
        })
        
    except Exception as e:
        print(f"❌ Erreur inscription externe:")
        traceback.print_exc()
        
        return JSONResponse({
            "status": "error",
            "message": f"Erreur: {str(e)}",
            "details": results
        }, status_code=500)


@app.get("/inscription/success", response_class=HTMLResponse)
async def registration_success(request: Request):
    """Page de confirmation après inscription"""
    return templates.TemplateResponse("user_page/inscription_ok.html", {"request": request})
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

#cd /home/fanantenana/Musique/WebReco_face\ pro_fin_anné && uvicorn main6:app --host 0.0.0.0 --port 8000 --reload    