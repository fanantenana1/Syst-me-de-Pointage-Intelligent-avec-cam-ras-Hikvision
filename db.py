"""from motor.motor_asyncio import AsyncIOMotorClient

DATABASE_URL = "mongodb api key"

client = AsyncIOMotorClient(DATABASE_URL)
db = client["securite_system"]
users_collection = db["utilisateurs"]
videos_collection = db["videos"]
images_collection = db["images"]  # AJOUT
"""
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus
from datetime import datetime

username = "usernam mongoDB"
password = "password"

# Encodage du mot de passe (gère automatiquement @, $, %, etc.)
password_encoded = quote_plus(password)

# URL MONGODB AVEC MOT DE PASSE SÉCURISÉ
DATABASE_URL = (
    f"mongodb+srv://{username}:{password_encoded}"
    "@cluster0.xxxx"
)
client = AsyncIOMotorClient(DATABASE_URL)
db = client["securite_system"]
users_collection = db["utilisateurs"]
videos_collection = db["videos"]
images_collection = db["images"]
evenements2_collection = db["evenements2"]  # 🆕 NOUVELLE COLLECTION


# Fonctions helper pour la synchronisation
async def sync_user_to_mongodb(employee_no: str, name: str, email: str = "", 
                                telephone: str = "",num_cart: str = "", empreint: str = "", cin: str = "", adresse: str = "",
                                photo_url: str = "", user_type: str = "normal",
                                valid_begin: str = "", valid_end: str = ""):
    """Synchronise un utilisateur Hikvision vers MongoDB"""
    try:
        user_data = {
            "employee_no": employee_no,
            "name": name,
            "email": email,
            "telephone": telephone,
            "num_cart": num_cart,
            "empreint": empreint,
            "cin": cin,
            "adresse": adresse,
            "photo_url": photo_url,
            "user_type": user_type,
            "valid_begin": valid_begin,
            "valid_end": valid_end,
            "updated_at": datetime.utcnow(),
            "source": "hikvision"
        }
        
        # Upsert (insert ou update)
        result = await users_collection.update_one(
            {"employee_no": employee_no},
            {
                "$set": user_data,
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
        return {"success": True, "modified": result.modified_count, "upserted": result.upserted_id}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_user_from_mongodb(employee_no: str):
    """Récupère les données complètes d'un utilisateur depuis MongoDB"""
    try:
        user = await users_collection.find_one({"employee_no": employee_no})
        if user:
            user["_id"] = str(user["_id"])
        return user
    except Exception as e:
        print(f"Error getting user from MongoDB: {e}")
        return None

async def delete_user_from_mongodb(employee_no: str):
    """Supprime un utilisateur de MongoDB"""
    try:
        result = await users_collection.delete_one({"employee_no": employee_no})
        return {"success": True, "deleted_count": result.deleted_count}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_all_mongodb_users():
    """Récupère tous les utilisateurs de MongoDB"""
    try:
        users = []
        async for user in users_collection.find():
            user["_id"] = str(user["_id"])
            users.append(user)
        return users
    except Exception as e:
        print(f"Error getting all users: {e}")
        return []

# =================== FONCTIONS AVANCÉES DE SYNCHRONISATION ===================

async def create_user_bidir(
    employee_no: str,
    name: str,
    email: str = "",
    telephone: str = "",
    cin: str = "",
    address: str = "",
    carte_number: str = "",
    fingerprint_id: str = "",
    photo_url: str = "",
    user_type: str = "normal",
    device_ip: str = "",
    **kwargs
):
    """
    Créer un utilisateur dans MongoDB avec tous les détails
    (appelé après synchronisation avec Hikvision)
    """
    try:
        user_data = {
            "employee_no": employee_no,
            "name": name,
            "email": email,
            "telephone": telephone,
            "cin": cin,
            "address": address,
            "carte_number": carte_number,
            "fingerprint_id": fingerprint_id,
            "photo_url": photo_url,
            "user_type": user_type,
            "hikvision_device_ip": device_ip,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "synced_with_hikvision": True,
            "source": "manual",
            **kwargs
        }
        
        result = await users_collection.insert_one(user_data)
        return {
            "success": True,
            "mongodb_id": str(result.inserted_id),
            "employee_no": employee_no
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def update_user_bidir(
    employee_no: str,
    device_ip: str = "",
    **update_fields
):
    """
    Mettre à jour un utilisateur dans MongoDB
    """
    try:
        if not device_ip:
            filter_query = {"employee_no": employee_no}
        else:
            filter_query = {"employee_no": employee_no, "hikvision_device_ip": device_ip}
        
        update_data = {**update_fields, "updated_at": datetime.utcnow()}
        
        result = await users_collection.update_one(
            filter_query,
            {"$set": update_data}
        )
        
        return {
            "success": True,
            "modified_count": result.modified_count,
            "employee_no": employee_no
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_user_by_employee_no(employee_no: str, device_ip: str = ""):
    """
    Récupère un utilisateur par son numéro d'employé
    """
    try:
        if device_ip:
            user = await users_collection.find_one({
                "employee_no": employee_no,
                "hikvision_device_ip": device_ip
            })
        else:
            user = await users_collection.find_one({"employee_no": employee_no})
        
        if user:
            user["_id"] = str(user["_id"])
        return user
    except Exception as e:
        print(f"Error getting user: {e}")
        return None

async def delete_user_bidir(employee_no: str, device_ip: str = ""):
    """
    Supprimer un utilisateur de MongoDB
    """
    try:
        if device_ip:
            result = await users_collection.delete_one({
                "employee_no": employee_no,
                "hikvision_device_ip": device_ip
            })
        else:
            result = await users_collection.delete_one({"employee_no": employee_no})
        
        return {
            "success": True,
            "deleted_count": result.deleted_count,
            "employee_no": employee_no
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_users_by_device(device_ip: str):
    """
    Récupère tous les utilisateurs pour un device Hikvision spécifique
    """
    try:
        users = []
        async for user in users_collection.find({"hikvision_device_ip": device_ip}):
            user["_id"] = str(user["_id"])
            users.append(user)
        return users
    except Exception as e:
        print(f"Error getting users by device: {e}")
        return []

async def search_users(search_term: str, device_ip: str = ""):
    """
    Chercher des utilisateurs par nom ou numéro d'employé
    """
    try:
        query = {
            "$or": [
                {"employee_no": {"$regex": search_term, "$options": "i"}},
                {"name": {"$regex": search_term, "$options": "i"}},
                {"email": {"$regex": search_term, "$options": "i"}},
                {"telephone": {"$regex": search_term, "$options": "i"}}
            ]
        }
        
        if device_ip:
            query["hikvision_device_ip"] = device_ip
        
        users = []
        async for user in users_collection.find(query):
            user["_id"] = str(user["_id"])
            users.append(user)
        return users
    except Exception as e:
        print(f"Error searching users: {e}")
        return []
