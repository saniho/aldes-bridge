# language: fr
Fonctionnalité: Versions affichées dans le menu burger

  Scénario: Le menu burger affiche les versions UI et Backend
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Et je clique sur le menu burger
    Alors les versions UI et Backend sont affichées