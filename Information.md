🎯 But du projet

Le projet vise à digitaliser et automatiser la gestion des présences dans un établissement universitaire grâce à la reconnaissance faciale et à l’IoT.
Objectif principal : remplacer le pointage papier, souvent lent, peu fiable et sujet aux fraudes, par un système intelligent, rapide et sécurisé.
⚙️ Fonctionnalités principales

    Automatisation du pointage : reconnaissance faciale instantanée (< 1 seconde) à l’entrée des salles ou à distance.

    Sécurité et anti‑fraude : identification biométrique unique, éliminant les signatures par procuration.

    Fiabilité et traçabilité : centralisation des données, export CSV, historique inaltérable.

    Interface intuitive : portail web pour administrateurs et étudiants (gestion, enrôlement, consultation).

    Innovation technique : dépassement de la limite matérielle (1500 personnes max) grâce à un cache dynamique permettant de gérer plus de 10 000 personnes sans surcoût matériel.

🛠️ Description et architecture

    Acquisition (IoT) : caméras Hikvision DS-K1T343EFWX.

    Backend : FastAPI (Python) pour performance et scalabilité.

    Base de données : MongoDB pour les présences, Cloudinary pour les images.

    Frontend : HTML5, CSS3, Bootstrap, JavaScript pour une interface moderne.

    Mécanisme clé : roulement automatique de la base de données (chargement/effacement en temps réel des groupes de 1500 personnes selon le planning).

📊 Résultats et démonstration

    Temps de reconnaissance : < 1 seconde.

    Taux de précision : > 95% (robuste même avec lunettes et luminosité variable).

    Dashboard administrateur : visualisation en temps réel, gestion des étudiants, consultation des historiques.

    Extension prévue : gestion multi‑sites et application web complète.

👉 En résumé, ce projet est une solution innovante qui modernise la gestion des présences universitaires en combinant IA, IoT et optimisation logicielle, tout en surmontant les limites matérielles pour atteindre une échelle de déploiement massive.
