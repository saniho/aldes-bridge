# language: fr
Fonctionnalité: Thème jour et nuit

  Scénario: Basculement du thème
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors la WebUI est en mode nuit
    Quand je clique sur le menu burger
    Et je bascule le thème
    Alors la WebUI est en mode jour
    Quand je clique sur le menu burger
    Et je bascule le thème
    Alors la WebUI est en mode nuit
