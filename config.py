"""
Configuration de la synchronisation MongoDB <--> Hikvision
Fichier centralisé pour tous les paramètres
"""

import os
from typing import Dict, Optional

# =================== CONFIGURATION HIKVISION ===================

class HikvisionConfig:
    """Configuration des devices Hikvision"""
    
    # Device principal (à modifier selon votre setup)
    PRIMARY_DEVICE = {
        "ip": os.getenv("HIK_DEVICE_IP", "192.168.101.24"),
        "username": os.getenv("HIK_USERNAME", "admin"),
        "password": os.getenv("HIK_PASSWORD", "Eni20230"),
        "port": int(os.getenv("HIK_PORT", "80"))
    }
    
    # Devices supplémentaires (optionnel)
    SECONDARY_DEVICES = [
        # {
        #     "ip": "192.168.101.25",
        #     "username": "admin",
        #     "password": "password",
        #     "port": 80
        # }
    ]
    
    # Configuration ISAPI
    ISAPI_TIMEOUT = 10  # Secondes
    ISAPI_RETRY_COUNT = 3
    ISAPI_RETRY_DELAY = 1  # Secondes
    
    # Configuration de synchronisation
    AUTO_SYNC_ENABLED = True  # Synchronisation automatique
    SYNC_INTERVAL = 300  # Secondes (5 minutes)
    LOG_SYNC_DETAILS = True  # Log détaillé des synchronisations


# =================== CONFIGURATION MONGODB ===================

class MongoDBConfig:
    """Configuration MongoDB"""
    
    # Credentials
    USERNAME = os.getenv("MONGO_USERNAME", "nam_mongoDB")
    PASSWORD = os.getenv("MONGO_PASSWORD", "******")
    CLUSTER = os.getenv("MONGO_CLUSTER", "cluster0.xxxxxxx")
    
    # Database
    DATABASE = os.getenv("MONGO_DATABASE", "securite_system")
    
    # Collections
    USERS_COLLECTION = "utilisateurs"
    VIDEOS_COLLECTION = "videos"
    IMAGES_COLLECTION = "images"
    LOGS_COLLECTION = "sync_logs"
    
    # Indexes (créés automatiquement)
    INDEXES = {
        "utilisateurs": [
            "employee_no",  # Index principal
            "email",
            "cin",
            "hikvision_device_ip"
        ]
    }
    
    # Configuration de connexion
    POOL_SIZE = 10
    CONNECT_TIMEOUT = 10000  # ms
    SERVER_SELECTION_TIMEOUT = 5000  # ms


# =================== CONFIGURATION SYNCHRONISATION ===================

class SyncConfig:
    """Configuration de synchronisation"""
    
    # Mode de synchronisation
    MODE = "bidirectional"  # bidirectional, hik_to_mongo, mongo_to_hik
    
    # Résolution des conflits
    CONFLICT_RESOLUTION = "last_write_wins"  # last_write_wins, hik_priority, mongo_priority
    
    # Rollback
    ENABLE_ROLLBACK = True  # Annuler en cas d'erreur
    ROLLBACK_TIMEOUT = 30  # Secondes
    
    # Logging
    LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
    LOG_FILE = "sync.log"
    LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5
    
    # Validation
    VALIDATE_ON_CREATE = True
    VALIDATE_ON_UPDATE = True
    VALIDATE_ON_DELETE = True
    
    # Champs requis
    REQUIRED_FIELDS = ["employee_no", "name"]
    
    # Champs optionnels par défaut
    OPTIONAL_FIELDS_DEFAULT = {
        "user_type": "normal",
        "valid_days": 365,
        "door_rights": "1",
        "status": "synced"
    }


# =================== CONFIGURATION SÉCURITÉ ===================

class SecurityConfig:
    """Configuration de sécurité"""
    
    # Authentification Hikvision
    AUTH_TYPE = "digest"  # digest, basic
    VERIFY_SSL = False  # Hikvision utilise souvent des certificats auto-signés
    
    # Chiffrement MongoDB
    ENABLE_ENCRYPTION = False
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
    
    # Rate limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_REQUESTS = 100  # requêtes
    RATE_LIMIT_PERIOD = 60  # secondes
    
    # API Keys
    API_KEY_REQUIRED = False
    API_KEYS = {
        # "key_name": "secret_key"
    }


# =================== CONFIGURATION CACHE ===================

class CacheConfig:
    """Configuration du cache"""
    
    CACHE_ENABLED = True
    CACHE_TTL = 300  # Secondes (5 minutes)
    CACHE_MAX_SIZE = 1000  # Nombre d'entrées
    
    # Éléments à mettre en cache
    CACHE_USERS = True
    CACHE_PHOTOS = True
    CACHE_DEVICE_INFO = True


# =================== CONFIGURATION NOTIFICATIONS ===================

class NotificationConfig:
    """Configuration des notifications"""
    
    # Email
    EMAIL_ENABLED = False
    EMAIL_HOST = os.getenv("EMAIL_HOST", "")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USER = os.getenv("EMAIL_USER", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@system.local")
    
    # Événements à notifier
    NOTIFY_ON_CREATE = True
    NOTIFY_ON_UPDATE = True
    NOTIFY_ON_DELETE = True
    NOTIFY_ON_SYNC_ERROR = True
    
    # Webhooks
    WEBHOOK_ENABLED = False
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


# =================== CONFIGURATION CLOUDINARY ===================

class CloudinaryConfig:
    """Configuration Cloudinary pour les photos"""
    
    ENABLED = True
    CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "nam_cloud")
    API_KEY = os.getenv("CLOUDINARY_API_KEY", "*********")
    API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "*******")
    
    # Configuration upload
    UPLOAD_FOLDER = "faces"
    UPLOAD_FORMAT = "jpg"
    UPLOAD_QUALITY = 80
    UPLOAD_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


# =================== CONFIGURATION API ===================

class APIConfig:
    """Configuration FastAPI"""
    
    # Serveur
    HOST = os.getenv("API_HOST", "0.0.0.0")
    PORT = int(os.getenv("API_PORT", "8000"))
    RELOAD = os.getenv("API_RELOAD", "False").lower() == "true"
    WORKERS = int(os.getenv("API_WORKERS", "4"))
    
    # CORS
    CORS_ORIGINS = ["*"]
    CORS_CREDENTIALS = True
    CORS_METHODS = ["*"]
    CORS_HEADERS = ["*"]
    
    # Timeouts
    REQUEST_TIMEOUT = 30  # Secondes
    STREAMING_TIMEOUT = 60
    
    # Pagination
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100


# =================== CONFIGURATION DÉVELOPPEMENT ===================

class DevConfig:
    """Configuration de développement"""
    
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    MOCK_HIKVISION = False  # Utiliser un mock au lieu du vrai device
    MOCK_MONGODB = False  # Utiliser un mock au lieu du vrai MongoDB
    
    # Tests
    TESTING = False
    TEST_DATABASE = "securite_system_test"


# =================== CONFIGURATION PRODUCTION ===================

class ProdConfig:
    """Configuration de production"""
    
    DEBUG = False
    MOCK_HIKVISION = False
    MOCK_MONGODB = False
    TESTING = False
    
    # Sécurité
    VERIFY_SSL = True
    ENABLE_ENCRYPTION = True
    API_KEY_REQUIRED = True
    RATE_LIMIT_ENABLED = True


# =================== CONFIG MANAGER ===================

class ConfigManager:
    """Gestionnaire centralisé des configurations"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.hikvision = HikvisionConfig()
        self.mongodb = MongoDBConfig()
        self.sync = SyncConfig()
        self.security = SecurityConfig()
        self.cache = CacheConfig()
        self.notification = NotificationConfig()
        self.cloudinary = CloudinaryConfig()
        self.api = APIConfig()
        
        if self.environment == "production":
            self.dev = ProdConfig()
        else:
            self.dev = DevConfig()
    
    def get_hikvision_config(self) -> Dict:
        """Retourne la configuration Hikvision"""
        return self.hikvision.PRIMARY_DEVICE
    
    def get_database_url(self) -> str:
        """Construit l'URL MongoDB"""
        from urllib.parse import quote_plus
        
        password_encoded = quote_plus(self.mongodb.PASSWORD)
        url = (
            f"mongodb+srv://{self.mongodb.USERNAME}:{password_encoded}"
            f"@{self.mongodb.CLUSTER}****************"
        )
        return url
    
    def to_dict(self) -> Dict:
        """Retourne tous les paramètres en dict"""
        return {
            "environment": self.environment,
            "hikvision": self.hikvision.__dict__,
            "mongodb": self.mongodb.__dict__,
            "sync": self.sync.__dict__,
            "security": self.security.__dict__,
            "cache": self.cache.__dict__,
            "notification": self.notification.__dict__,
            "cloudinary": self.cloudinary.__dict__,
            "api": self.api.__dict__,
        }
    
    def validate(self) -> bool:
        """Valide la configuration"""
        errors = []
        
        # Vérifier Hikvision
        if not self.hikvision.PRIMARY_DEVICE.get("ip"):
            errors.append("Hikvision IP not configured")
        
        # Vérifier MongoDB
        if not self.mongodb.USERNAME or not self.mongodb.PASSWORD:
            errors.append("MongoDB credentials not configured")
        
        if errors:
            print("⚠️  Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True
    
    def print_config(self):
        """Affiche la configuration actuelle"""
        print("\n" + "="*60)
        print("Configuration actuelle")
        print("="*60)
        print(f"Environnement: {self.environment}")
        print(f"\nHikvision: {self.hikvision.PRIMARY_DEVICE['ip']}")
        print(f"MongoDB: {self.mongodb.DATABASE}")
        print(f"Synchronisation: {self.sync.MODE}")
        print("="*60 + "\n")


# =================== INSTANCE GLOBALE ===================

config = ConfigManager()

# Exporter
__all__ = [
    "config",
    "ConfigManager",
    "HikvisionConfig",
    "MongoDBConfig",
    "SyncConfig",
    "SecurityConfig",
    "CacheConfig",
    "NotificationConfig",
    "CloudinaryConfig",
    "APIConfig",
    "DevConfig",
    "ProdConfig"
]
