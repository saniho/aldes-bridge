# language: fr
Fonctionnalité: Panneau de configuration

  Scénario: Accès au panneau config via le menu burger
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et les paramètres sont réinitialisés
    Quand j'ouvre la page d'accueil
    Et je clique sur le menu burger
    Et je clique sur l'item de menu « config »
    Alors le panneau de configuration est visible

  Scénario: Les paramètres par défaut sont affichés
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et les paramètres sont réinitialisés
    Quand j'ouvre la page d'accueil
    Et je clique sur le menu burger
    Et je clique sur l'item de menu « config »
    Alors le champ rétention historique affiche « 90 »
    Et le champ taille max logs affiche « 25 MB »

  Scénario: Modification de la rétention historique
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et les paramètres sont réinitialisés
    Quand j'ouvre la page d'accueil
    Et je clique sur le menu burger
    Et je clique sur l'item de menu « config »
    Quand je tape « 30 » dans le champ rétention historique
    Et je clique sur « Appliquer »
    Alors un message de confirmation est affiché
    Et la rétention historique est « 30 » côté API
