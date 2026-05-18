#!/bin/bash
# Script de démarrage optimisé pour FastAPI + Hikvision Scanner

set -e  # Arrêter si une commande échoue

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  🚀 Hikvision Face Recognition - WebReco                       ║"
echo "║     Démarrage du serveur FastAPI avec support Scanner         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Déterminer le répertoire du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/5] 📁 Répertoire: $SCRIPT_DIR"
echo ""

# Vérifier que les dépendances Python sont installées
echo "[2/5] 🐍 Vérification des dépendances Python..."
python3 -c "import fastapi, motor, cv2, face_recognition" 2>/dev/null || {
    echo "❌ Dépendances manquantes. Exécutez:"
    echo "   pip install -r requirements.txt"
    exit 1
}
echo "✅ Toutes les dépendances sont présentes"
echo ""

# Vérifier la configuration sudo pour le scanner
echo "[3/5] 🔐 Vérification de la configuration SUDO..."
if [ -f "/etc/sudoers.d/hikvision-scan" ]; then
    echo "✅ Configuration SUDO trouvée"
else
    echo "⚠️  Configuration SUDO manquante (optionnel pour ce test)"
    echo "   Pour activer le scanner Hikvision automatique:"
    echo "   → sudo bash setup_sudo.sh"
fi
echo ""

# Arrêter les instances existantes
echo "[4/5] 🛑 Arrêt des instances précédentes..."
pkill -f "uvicorn main6" || true
sleep 1
echo "✅ Nettoyage effectué"
echo ""

# Démarrer le serveur
echo "[5/5] 🚀 Démarrage du serveur..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Lancer avec auto-reload pour le développement
uvicorn main6:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir . \
    --log-level info

# Si le serveur s'arrête
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⛔ Serveur arrêté"
