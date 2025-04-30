# Projet FINDAM

*Plateforme de location de logements meublés au Cameroun*

## 📋 Sommaire

- [Description du Projet](#-description-du-projet)
- [Business Model](#-business-model)
- [Acteurs et User Stories](#-acteurs-et-user-stories)
- [Architecture Technique](#-architecture-technique)
- [Structure du Projet](#-structure-du-projet)
- [Modèles de Données](#-modèles-de-données)
- [Fonctionnalités Implémentées](#-fonctionnalités-implémentées)
- [Étapes Restantes](#-étapes-restantes)
- [Guide d'Installation](#-guide-dinstallation)

## 🏠 Description du Projet

FINDAM est une plateforme inspirée d'Airbnb, spécialement conçue pour le marché camerounais, permettant aux propriétaires de proposer des logements meublés à la location à court, moyen ou long terme, et aux utilisateurs de réserver ces logements de manière sécurisée avec des fonctionnalités adaptées au contexte local.

### Fonctionnalités Distinctives

- **Système de négociation** via chat et codes promo
- **Intégration Mobile Money** avec NotchPay
- **Gestion des réservations physiques** (hors plateforme)
- **Système de vérification d'identité** adapté au contexte camerounais
- **Abonnements pour propriétaires** avec niveaux de service

## 💰 Business Model

### Sources de Revenus

1. **Commission sur les réservations** : 10% du montant total
   - 3% prélevés sur les propriétaires
   - 7% ajoutés à la facture des locataires

2. **Abonnements pour propriétaires**
   - **Gratuit (Standard)** : Limité à 2 logements, commission standard (13%)
   - **Mensuel (10 000 FCFA)** : Publication illimitée, commission réduite (10%), mise en avant, statistiques
   - **Trimestriel (25 000 FCFA)** : Avantages mensuels + outils d'analyse avancés (17% d'économie)
   - **Annuel (80 000 FCFA)** : Avantages trimestriels + fonctionnalités exclusives (33% d'économie)

3. **Options de mise en avant** (phase ultérieure)
   - Positionnement prioritaire dans les résultats
   - Badge "Propriétaire vérifié"

### Mesures Anti-abus

- Vérification d'identité obligatoire
- Paiement via la plateforme uniquement
- Rétention 24h après check-in
- Système d'évaluation mutuelle

## 👥 Acteurs et User Stories

### Acteurs Principaux

1. **Locataires/Clients**
2. **Propriétaires/Hôtes**
3. **Administrateurs**
4. **Système de Paiement**
5. **Visiteurs**

### User Stories - Locataires

#### Inscription et Profil
- En tant que visiteur, je veux pouvoir créer un compte facilement
- En tant que locataire, je veux compléter mon profil avec mes informations personnelles
- En tant que locataire, je veux vérifier mon identité (CNI, selfie)

#### Recherche et Réservation
- Je veux rechercher des logements par ville/quartier, dates et capacité
- Je veux utiliser des filtres avancés (équipements, budget)
- Je veux consulter le calendrier de disponibilité d'un logement
- Je veux voir le prix total calculé automatiquement
- Je veux pouvoir demander un rabais

#### Paiement et Suivi
- Je veux payer ma réservation via Mobile Money ou carte bancaire
- Je veux recevoir une confirmation de réservation
- Je veux consulter mon historique de réservations
- Je veux laisser un avis après mon séjour

#### Communication
- Je veux contacter le propriétaire via le chat intégré
- Je veux appliquer un code promo

### User Stories - Propriétaires

#### Inscription et Vérification
- Je veux m'inscrire comme propriétaire
- Je veux vérifier mon identité
- Je veux souscrire à un forfait d'abonnement

#### Gestion des Logements
- Je veux ajouter un nouveau logement avec photos et description
- Je veux définir les tarifs (nuitée/semaine/mois)
- Je veux paramétrer les frais annexes (ménage, caution)
- Je veux configurer des réductions pour les longs séjours
- Je veux définir ma politique d'annulation

#### Gestion des Disponibilités
- Je veux gérer mon calendrier de disponibilités
- Je veux bloquer des dates pour des réservations hors plateforme
- Je veux accéder à des statistiques d'occupation (premium)

#### Communication et Transactions
- Je veux échanger avec les locataires via le chat
- Je veux générer des codes promo personnalisés
- Je veux recevoir des notifications de nouvelles demandes
- Je veux recevoir mes paiements de manière sécurisée
- Je veux évaluer mes locataires après leur séjour

### User Stories - Administrateurs

- Je veux valider les inscriptions des propriétaires
- Je veux modérer les avis et commentaires
- Je veux suivre les transactions financières
- Je veux intervenir en cas de litige
- Je veux accéder à des statistiques d'utilisation

## 🔧 Architecture Technique

### Approche Globale

- **Backend** : API REST avec Django REST Framework
- **Frontend** : À développer séparément (React/Vue.js)
- **Base de données** : PostgreSQL (SQLite en développement)
- **Authentification** : JWT (JSON Web Tokens)
- **Upload de fichiers** : Intégré à Django avec compression d'images
- **Paiements** : Intégration directe avec NotchPay
- **Communication en temps réel** : WebSockets (à implémenter)

### Points Forts de l'Architecture

- **Séparation claire** backend/frontend
- **API réutilisable** pour application mobile future
- **Scalabilité** facilitée
- **Sécurité** renforcée par le framework Django
- **Testabilité** améliorée par la séparation des responsabilités

## 📁 Structure du Projet

```
findam/
│
├── findam/                    # Configuration principale
│   ├── settings.py            # Paramètres du projet
│   ├── urls.py                # URLs principales
│   └── ...
│
├── accounts/                  # Gestion des utilisateurs
│   ├── models.py              # Modèles utilisateurs et profils
│   ├── serializers.py         # Sérialiseurs API
│   ├── views.py               # Vues et endpoints
│   ├── permissions.py         # Permissions personnalisées
│   └── ...
│
├── properties/                # Gestion des logements
│   ├── models.py              # Modèles logements, équipements, etc.
│   ├── serializers.py
│   ├── views.py
│   ├── filters.py             # Filtres de recherche avancés
│   └── ...
│
├── bookings/                  # Gestion des réservations
│   ├── models.py              # Modèles réservations, codes promo
│   ├── serializers.py
│   ├── views.py
│   ├── permissions.py
│   └── ...
│
├── payments/                  # Gestion des paiements
│   ├── models.py              # Modèles transactions, remboursements
│   ├── serializers.py
│   ├── views.py
│   ├── services/              # Services d'intégration NotchPay
│   └── ...
│
├── communications/            # Gestion des communications
│   ├── models.py              # Modèles conversations, messages
│   ├── serializers.py
│   ├── views.py
│   ├── consumers.py           # Pour WebSockets (à développer)
│   └── ...
│
├── reviews/                   # Gestion des avis
│   ├── models.py              # Modèles avis, signalements
│   ├── serializers.py
│   ├── views.py
│   └── ...
│
└── common/                    # Utilitaires partagés
    ├── utils.py               # Fonctions utilitaires
    ├── middlewares.py         # Middlewares personnalisés
    └── ...
```

## 📊 Modèles de Données

### accounts
- **User**: Modèle utilisateur personnalisé (propriétaire, locataire, admin)
- **Profile**: Infos complémentaires et vérification d'identité
- **OwnerSubscription**: Abonnements des propriétaires

### properties
- **Property**: Informations complètes sur les logements
- **PropertyImage**: Images des logements
- **Amenity**: Équipements disponibles
- **City/Neighborhood**: Localisation
- **Availability**: Périodes d'indisponibilité
- **LongStayDiscount**: Réductions pour séjours longue durée

### bookings
- **Booking**: Réservations et informations associées
- **PromoCode**: Codes promotionnels
- **BookingReview**: Avis sur les réservations
- **PaymentTransaction**: Transactions de paiement

### communications
- **Conversation**: Conversations entre utilisateurs
- **Message**: Messages échangés
- **Notification**: Notifications système
- **DeviceToken**: Tokens pour notifications push

### payments
- **Transaction**: Transactions financières
- **Payout**: Versements aux propriétaires
- **PaymentMethod**: Méthodes de paiement enregistrées

### reviews
- **Review**: Avis détaillés
- **ReportedReview**: Signalements d'avis

## ✅ Fonctionnalités Implémentées

### Backend

- ✅ **Structure du projet** complète
- ✅ **Configuration de base** (settings, URLs, etc.)
- ✅ **Modèles de données** pour toutes les applications
- ✅ **API authentification** avec JWT
- ✅ **API gestion utilisateurs** (inscription, profil, vérification)
- ✅ **API gestion des logements** (création, recherche, filtrage)
- ✅ **API gestion des réservations** (workflow complet)
- ✅ **API paiement** avec NotchPay
- ✅ **API communications** (conversations, messages)
- ✅ **Admin Django** personnalisé

### Intégrations

- ✅ **NotchPay** pour les paiements
- ✅ **JWT** pour l'authentification
- ✅ **CORS** pour la communication cross-domain

## 🚧 Étapes Restantes

### Backend

finalisation de la views, admin , urls, etc ...

1. **Application Payments**:
   - Finaliser les modèles de versements aux propriétaires
   - Implémenter le système de commission
   - Ajouter les historiques de transactions

2. **Application Reviews**:
   - Finaliser les modèles d'avis détaillés
   - Implémenter le système de modération
   - Ajouter les signalements d'avis

3. **Communications en temps réel**:
   - Implémenter les WebSockets avec Django Channels
   - Finaliser le système de notifications push

4. **Tests**:
   - Écrire les tests unitaires
   - Écrire les tests d'intégration
   - Tester les workflows complets

5. **Documentation API**:
   - Générer la documentation API avec Swagger/OpenAPI
   - Documenter les endpoints et exemples

6. **Optimisations**:
   - Cache Redis pour les requêtes fréquentes
   - Optimisation des requêtes N+1
   - Pagination avancée

### Frontend (À développer)

1. **Choix du framework** (React ou Vue.js)
2. **Interface utilisateur** responsive
3. **Intégration avec l'API** backend
4. **Responsive design** mobile-first

## 📝 Guide d'Installation

### Prérequis

- Python 3.8+
- pip
- Virtualenv
- Git

### Installation

1. Cloner le dépôt
   ```bash
   git clone https://github.com/votre-organisation/findam.git
   cd findam
   ```

2. Créer un environnement virtuel
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows: venv\Scripts\activate
   ```

3. Installer les dépendances
   ```bash
   pip install -r requirements.txt
   ```

4. Configurer les variables d'environnement
   ```bash
   cp .env.example .env
   # Éditer .env avec vos configurations
   ```

5. Effectuer les migrations
   ```bash
   python manage.py migrate
   ```

6. Créer un super-utilisateur
   ```bash
   python manage.py createsuperuser
   ```

7. Lancer le serveur de développement
   ```bash
   python manage.py runserver
   ```

8. Accéder à l'administration
   ```
   http://localhost:8000/admin/
   ```

---

© 2023 FINDAM - Plateforme de location de logements meublés au Cameroun