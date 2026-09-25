# language: fr
Fonctionnalité: État de dégivrage

  Scénario: Un dégivrage actif ne déclenche pas une alerte
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et le snapshot simule un dégivrage actif
    Quand j'ouvre la page d'accueil
    Et je clique sur l'onglet « vue d'ensemble »
    Alors aucune alerte de dégivrage n’est affichée
    Quand je clique sur l'onglet « santé »
    Alors le statut de dégivrage est Actif
