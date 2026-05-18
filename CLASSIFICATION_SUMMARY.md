# 📊 Résumé des Changements de Classification

## Objectif
Changer la classification des présences d'une personne en se basant sur **l'identification de la personne** plutôt que sur le champ `event.validated` de Hikvision.

## Nouvelle Règle

**Une personne est classée :**
- ✅ **"Validée"** si elle a :
  - Un `employee_id` identifié (pas "-")
  - Un `name` non vide (pas "-")
  - **TOUS ses événements** héritent ce statut

- ❌ **"Refusée"** si elle n'a pas d'identification :
  - `employee_id` = "-" ou vide
  - `name` = "-" ou vide
  - **TOUS ses événements** héritent ce statut

## Fichiers Modifiés

### `templates/presences.html`

#### 1. Nouvelle fonction : `applyPersonClassification()` (lignes ~835-857)
```javascript
function applyPersonClassification(userStats) {
    return userStats.map(stat => {
        const isIdentified = stat.employee_id && stat.employee_id !== '-' && 
                            stat.name && stat.name !== '-';
        
        if (isIdentified) {
            return { ...stat, validated: stat.total, refused: 0 };
        } else {
            return { ...stat, validated: 0, refused: stat.total };
        }
    });
}
```

#### 2. `displayStatistics()` (lignes ~783-825)
- Recalcule les stats globales basées sur l'identification
- Les "Validés" = événements de personnes identifiées
- Les "Refusés" = événements de personnes non identifiées

#### 3. `showUserDetails()` (lignes ~950-1010)
- Applique la classification au niveau détails utilisateur
- Calcule `validated` et `refused` basés sur `isIdentified`
- Passe `isIdentified` à `displayEventTimeline()`

#### 4. `displayEventTimeline()` (lignes ~1112-1160)
- **MISE À JOUR** : reçoit paramètre `isPersonIdentified`
- Affiche le statut basé sur l'identification
- Garde le statut original de Hikvision en gris pour référence

#### 5. Appels à `applyPersonClassification()`
- Ligne ~768 : dans `loadPresences()`
- Ligne ~1411 : dans `applyFilters()`

#### 6. Filtre `statusFilter` (lignes ~1395-1413)
- Utilise l'identification au lieu de `event.validated`
- Filtre cohérent avec la nouvelle classification

## Exemples Avant/Après

### Avant (basé sur `event.validated` de Hikvision)
```
ID Employé   Nom       Total   Validés   Refusés
0055         XV        95      0         95     ❌
3822         Octave    47      0         47     ❌
-            -         557     0         557    ❌
```

### Après (basé sur identification)
```
ID Employé   Nom       Total   Validés   Refusés
0055         XV        95      95        0      ✅
3822         Octave    47      47        0      ✅
-            -         557     0         557    ❌
```

## Impacts

1. **Tableau des statistiques par utilisateur** : Utilise la nouvelle classification
2. **Modal "Détails Complets de l'Utilisateur"** :
   - Affiche les stats basées sur l'identification
   - Timeline montre le nouveau statut
   - Graphique doughnut reflète la nouvelle répartition
3. **Filtres avancés** : Cohérents avec la nouvelle classification
4. **Affichage brut du tableau des présences** : Garde le statut original de Hikvision pour audit

## Vérification

- [ ] Recharger `presences.html`
- [ ] Cliquer sur "Charger les présences"
- [ ] Vérifier que le tableau "Statistiques par utilisateur" montre les nouvelles valeurs
- [ ] Cliquer sur "Détails" pour une personne identifiée (ex: XV, Octave)
  - Doit afficher 100% de présences validées ✅
- [ ] Cliquer sur "Détails" pour personne non identifiée (ID="-")
  - Doit afficher 100% de présences refusées ❌
