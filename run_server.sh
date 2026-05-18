#!/bin/bash
# 🚀 QUICK START - Démarrer le serveur

cd "/home/fanantenana/Musique/WebReco_face pro_fin_anné"

echo "🌐 Démarrage du serveur WebReco Face..."
echo ""
echo "✅ Serveur URL: http://localhost:8000"
echo "✅ Frontend: http://localhost:8000/ajout_user7"
echo ""
echo "⏳ Démarrage..."
echo ""

# Démarrer le serveur
uvicorn main6:app --host 0.0.0.0 --port 8000 --reload

# À la fin:
echo ""
echo "🛑 Serveur arrêté"
