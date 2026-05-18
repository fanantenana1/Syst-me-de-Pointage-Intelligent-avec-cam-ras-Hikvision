"""from motor.motor_asyncio import AsyncIOMotorClient

DATABASE_URL = "mongodb+srv://haaahiii:1234@cluster1.wmj7n.mongodb.net/?retryWrites=true&w=majority&appName=Cluster1"

client = AsyncIOMotorClient(DATABASE_URL)
db = client["securite_system"]
users_collection = db["utilisateurs"]
videos_collection = db["videos"]
images_collection = db["images"]  # AJOUT
"""
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus
from datetime import datetime
from typing import List, Optional, Dict, Any

#DATABASE_URL = "mongodb+srv://haaahiii:1234@cluster1.wmj7n.mongodb.net/?retryWrites=true&w=majority&appName=Cluster1"
#DATABASE_URL = "mongodb+srv://Fana_mongoDB:Fanantenana@123@cluster0.ttdkudf.mongodb.net/?appName=Cluster0"
username = "Fana_mongoDB"
password = "Fanantenana@123"

# Encodage du mot de passe (gère automatiquement @, $, %, etc.)
password_encoded = quote_plus(password)

# URL MONGODB AVEC MOT DE PASSE SÉCURISÉ
DATABASE_URL = (
    f"mongodb+srv://{username}:{password_encoded}"
    "@cluster0.ttdkudf.mongodb.net/?retryWrites=true&w=majority"
)
client = AsyncIOMotorClient(DATABASE_URL)
db = client["securite_system"]
users_collection = db["utilisateurs"]
videos_collection = db["videos"]
images_collection = db["images"]
evenements_collection = db["evenements2"]  # 🆕 NOUVELLE COLLECTION POUR LES ÉVÉNEMENTS

# =================== FONCTIONS POUR LES UTILISATEURS ===================

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


# =================== 🆕 FONCTIONS POUR LES ÉVÉNEMENTS DE PRÉSENCE ===================

async def create_presence_event(
    employee_no: str,
    name: str,
    status: str,  # "present", "absent", "unknown"
    event_datetime: datetime,
    device_ip: str = "",
    method: str = "",  # "Card", "Fingerprint", "Face", etc.
    door_no: str = "",
    period: str = "",  # "Matin", "Après-midi", "Soir", "Nuit"
    day: str = "",
    major: str = "",
    minor: str = "",
    validated: str = "",  # "Validé", "Refusé"
    notes: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    Créer un nouvel événement de présence dans MongoDB
    
    Args:
        employee_no: Numéro d'employé
        name: Nom de la personne
        status: Statut de présence ("present", "absent", "unknown")
        event_datetime: Date et heure de l'événement
        device_ip: IP du device Hikvision
        method: Méthode d'accès (Card, Fingerprint, Face, etc.)
        door_no: Numéro de la porte
        period: Période de la journée
        day: Jour de la semaine
        major: Code majeur
        minor: Code mineur
        validated: Statut de validation
        notes: Notes supplémentaires
        
    Returns:
        Dict avec success, event_id, et employee_no
    """
    try:
        event_data = {
            "employee_no": employee_no,
            "name": name,
            "status": status,
            "event_datetime": event_datetime,
            "date": event_datetime.strftime("%Y-%m-%d") if isinstance(event_datetime, datetime) else str(event_datetime).split()[0],
            "time": event_datetime.strftime("%H:%M:%S") if isinstance(event_datetime, datetime) else str(event_datetime).split()[1] if len(str(event_datetime).split()) > 1 else "",
            "device_ip": device_ip,
            "method": method,
            "door_no": door_no,
            "period": period,
            "day": day,
            "major": major,
            "minor": minor,
            "validated": validated,
            "notes": notes,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "source": "hikvision",
            "is_deleted": False,
            **kwargs
        }
        
        result = await evenements_collection.insert_one(event_data)
        
        return {
            "success": True,
            "event_id": str(result.inserted_id),
            "employee_no": employee_no
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def bulk_create_presence_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Créer plusieurs événements de présence en une seule opération (optimisé)
    
    Args:
        events: Liste de dictionnaires contenant les données d'événements
        
    Returns:
        Dict avec success, inserted_count, et event_ids
    """
    try:
        if not events:
            return {"success": True, "inserted_count": 0, "event_ids": []}
        
        # Préparer les données
        now = datetime.utcnow()
        for event in events:
            event["created_at"] = now
            event["updated_at"] = now
            event["is_deleted"] = False
            if "source" not in event:
                event["source"] = "hikvision"
        
        result = await evenements_collection.insert_many(events)
        
        return {
            "success": True,
            "inserted_count": len(result.inserted_ids),
            "event_ids": [str(id) for id in result.inserted_ids]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_presence_event(event_id: str) -> Optional[Dict[str, Any]]:
    """
    Récupérer un événement de présence par son ID
    
    Args:
        event_id: ID de l'événement
        
    Returns:
        Dictionnaire de l'événement ou None
    """
    try:
        from bson import ObjectId
        event = await evenements_collection.find_one({"_id": ObjectId(event_id)})
        if event:
            event["_id"] = str(event["_id"])
        return event
    except Exception as e:
        print(f"Error getting event: {e}")
        return None


async def get_presence_events_by_employee(
    employee_no: str,
    device_ip: str = "",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Récupérer tous les événements de présence pour un employé
    
    Args:
        employee_no: Numéro d'employé
        device_ip: Filtrer par IP du device (optionnel)
        start_date: Date de début (optionnel)
        end_date: Date de fin (optionnel)
        status: Filtrer par statut (optionnel)
        
    Returns:
        Liste des événements
    """
    try:
        query = {"employee_no": employee_no, "is_deleted": False}
        
        if device_ip:
            query["device_ip"] = device_ip
        
        if status:
            query["status"] = status
        
        if start_date or end_date:
            query["event_datetime"] = {}
            if start_date:
                query["event_datetime"]["$gte"] = start_date
            if end_date:
                query["event_datetime"]["$lte"] = end_date
        
        events = []
        async for event in evenements_collection.find(query).sort("event_datetime", -1):
            event["_id"] = str(event["_id"])
            events.append(event)
        
        return events
    except Exception as e:
        print(f"Error getting events for employee: {e}")
        return []


async def get_presence_events_by_date_range(
    start_date: datetime,
    end_date: datetime,
    device_ip: str = "",
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Récupérer tous les événements de présence dans une période
    
    Args:
        start_date: Date de début
        end_date: Date de fin
        device_ip: Filtrer par IP du device (optionnel)
        status: Filtrer par statut (optionnel)
        
    Returns:
        Liste des événements
    """
    try:
        query = {
            "event_datetime": {"$gte": start_date, "$lte": end_date},
            "is_deleted": False
        }
        
        if device_ip:
            query["device_ip"] = device_ip
        
        if status:
            query["status"] = status
        
        events = []
        async for event in evenements_collection.find(query).sort("event_datetime", -1):
            event["_id"] = str(event["_id"])
            events.append(event)
        
        return events
    except Exception as e:
        print(f"Error getting events by date range: {e}")
        return []


async def get_all_presence_events(device_ip: str = "") -> List[Dict[str, Any]]:
    """
    Récupérer tous les événements de présence
    
    Args:
        device_ip: Filtrer par IP du device (optionnel)
        
    Returns:
        Liste des événements
    """
    try:
        query = {"is_deleted": False}
        
        if device_ip:
            query["device_ip"] = device_ip
        
        events = []
        async for event in evenements_collection.find(query).sort("event_datetime", -1):
            event["_id"] = str(event["_id"])
            events.append(event)
        
        return events
    except Exception as e:
        print(f"Error getting all events: {e}")
        return []


async def update_presence_event(
    event_id: str = None,
    employee_no: str = None,
    event_datetime: str = None,
    **update_fields
) -> Dict[str, Any]:
    """
    Mettre à jour un événement de présence
    
    Args:
        event_id: ID de l'événement (optionnel si employee_no et event_datetime fournis)
        employee_no: Numéro d'employé (pour recherche)
        event_datetime: Date/heure de l'événement (pour recherche)
        **update_fields: Champs à mettre à jour
        
    Returns:
        Dict avec success et modified_count
    """
    try:
        from bson import ObjectId
        
        # Construire la requête de recherche
        if event_id:
            query = {"_id": ObjectId(event_id)}
        elif employee_no and event_datetime:
            query = {
                "employee_no": employee_no,
                "event_datetime": event_datetime
            }
        else:
            return {"success": False, "error": "event_id or (employee_no + event_datetime) required"}
        
        update_data = {**update_fields, "updated_at": datetime.utcnow()}
        
        result = await evenements_collection.update_one(
            query,
            {"$set": update_data}
        )
        
        return {
            "success": True,
            "modified_count": result.modified_count
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def delete_presence_event(event_id: str = None, employee_no: str = None, event_datetime: str = None) -> Dict[str, Any]:
    """
    Marquer un événement comme supprimé (soft delete)
    
    Args:
        event_id: ID de l'événement
        employee_no: Numéro d'employé (pour recherche)
        event_datetime: Date/heure de l'événement (pour recherche)
        
    Returns:
        Dict avec success et modified_count
    """
    try:
        from bson import ObjectId
        
        # Construire la requête de recherche
        if event_id:
            query = {"_id": ObjectId(event_id)}
        elif employee_no and event_datetime:
            query = {
                "employee_no": employee_no,
                "event_datetime": event_datetime
            }
        else:
            return {"success": False, "error": "event_id or (employee_no + event_datetime) required"}
        
        result = await evenements_collection.update_one(
            query,
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "success": True,
            "modified_count": result.modified_count,
            "deleted": result.modified_count > 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_presence_statistics(
    device_ip: str = "",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Obtenir des statistiques sur les présences
    
    Args:
        device_ip: Filtrer par IP du device (optionnel)
        start_date: Date de début (optionnel)
        end_date: Date de fin (optionnel)
        
    Returns:
        Dictionnaire avec les statistiques
    """
    try:
        query = {"is_deleted": False}
        
        if device_ip:
            query["device_ip"] = device_ip
        
        if start_date or end_date:
            query["event_datetime"] = {}
            if start_date:
                query["event_datetime"]["$gte"] = start_date
            if end_date:
                query["event_datetime"]["$lte"] = end_date
        
        # Compter les événements par statut
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]
        
        status_counts = {}
        async for result in evenements_collection.aggregate(pipeline):
            status_counts[result["_id"]] = result["count"]
        
        # Compter les employés uniques
        unique_employees = await evenements_collection.distinct("employee_no", query)
        
        # Total des événements
        total_events = await evenements_collection.count_documents(query)
        
        return {
            "success": True,
            "total_events": total_events,
            "present_count": status_counts.get("present", 0),
            "absent_count": status_counts.get("absent", 0),
            "unknown_count": status_counts.get("unknown", 0),
            "unique_employees": len(unique_employees),
            "status_breakdown": status_counts
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_employee_presence_summary(
    employee_no: str,
    device_ip: str = "",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Obtenir un résumé des présences pour un employé
    
    Args:
        employee_no: Numéro d'employé
        device_ip: Filtrer par IP du device (optionnel)
        start_date: Date de début (optionnel)
        end_date: Date de fin (optionnel)
        
    Returns:
        Dictionnaire avec le résumé
    """
    try:
        query = {"employee_no": employee_no, "is_deleted": False}
        
        if device_ip:
            query["device_ip"] = device_ip
        
        if start_date or end_date:
            query["event_datetime"] = {}
            if start_date:
                query["event_datetime"]["$gte"] = start_date
            if end_date:
                query["event_datetime"]["$lte"] = end_date
        
        # Compter par statut
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]
        
        status_counts = {}
        async for result in evenements_collection.aggregate(pipeline):
            status_counts[result["_id"]] = result["count"]
        
        total = sum(status_counts.values())
        present = status_counts.get("present", 0)
        
        return {
            "success": True,
            "employee_no": employee_no,
            "total_events": total,
            "present_count": present,
            "absent_count": status_counts.get("absent", 0),
            "unknown_count": status_counts.get("unknown", 0),
            "presence_rate": (present / total * 100) if total > 0 else 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def search_presence_events(
    search_term: str,
    device_ip: str = "",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Rechercher des événements de présence
    
    Args:
        search_term: Terme de recherche (nom ou employee_no)
        device_ip: Filtrer par IP du device (optionnel)
        start_date: Date de début (optionnel)
        end_date: Date de fin (optionnel)
        
    Returns:
        Liste des événements trouvés
    """
    try:
        query = {
            "$or": [
                {"employee_no": {"$regex": search_term, "$options": "i"}},
                {"name": {"$regex": search_term, "$options": "i"}}
            ],
            "is_deleted": False
        }
        
        if device_ip:
            query["device_ip"] = device_ip
        
        if start_date or end_date:
            query["event_datetime"] = {}
            if start_date:
                query["event_datetime"]["$gte"] = start_date
            if end_date:
                query["event_datetime"]["$lte"] = end_date
        
        events = []
        async for event in evenements_collection.find(query).sort("event_datetime", -1):
            event["_id"] = str(event["_id"])
            events.append(event)
        
        return events
    except Exception as e:
        print(f"Error searching events: {e}")
        return []