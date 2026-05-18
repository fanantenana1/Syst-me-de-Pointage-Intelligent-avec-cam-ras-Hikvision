#!/bin/bash
# Test si le setup sudo est bien configuré

echo "🔍 Test de configuration SUDO pour Hikvision..."
echo ""

# Test 1: Vérifier que /etc/sudoers.d/hikvision-scan existe
if [ -f "/etc/sudoers.d/hikvision-scan" ]; then
    echo "✅ Fichier /etc/sudoers.d/hikvision-scan existe"
else
    echo "❌ Fichier /etc/sudoers.d/hikvision-scan MANQUANT"
    echo "   Exécutez: sudo bash setup_sudo.sh"
    exit 1
fi

echo ""

# Test 2: Vérifier que sudo fonctionne sans mot de passe
echo "Vérification de l'accès sudo sans mot de passe..."
if sudo -n python3 -c "print('✅ Sudo OK')" 2>/dev/null; then
    echo "✅ sudo accepte les commandes sans mot de passe"
else
    echo "❌ sudo ne fonctionne pas"
    echo "   Solution: Exécutez à nouveau setup_sudo.sh"
    exit 1
fi

echo ""

# Test 3: Vérifier que troue_ip.py existe
if [ -f "troue_ip.py" ]; then
    echo "✅ troue_ip.py trouvé"
else
    echo "❌ troue_ip.py MANQUANT"
    exit 1
fi

echo ""

# Test 4: Tester un scan rapide (sans timeout long)
echo "Test du scan Hikvision (10 secondes max)..."
timeout 10 sudo -n python3 troue_ip.py 2>&1 | head -5

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SUCCÈS! Le scanner fonctionne"
    echo "   Vous pouvez maintenant redémarrer le serveur"
    echo ""
    echo "   Commande: bash run_server.sh"
else
    echo ""
    echo "⚠️  Le scan a rencontré un problème"
    echo "   Vérifiez que Hikvision est connectée au réseau"
fi
