# language: fr
Fonctionnalité: Navigation entre onglets

  Scénario: Aucun onglet n'est actif par défaut
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors aucun onglet n'est actif

  Scénario: Basculement vers commande
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Quand je clique sur l'onglet « commande »
    Alors l'onglet « commande » est actif

  Scénario: Menu burger et options
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors le menu burger est fermé
    Quand je clique sur le menu burger
    Alors le menu burger est ouvert
    Quand je clique sur le menu burger
    Alors le menu burger est fermé
