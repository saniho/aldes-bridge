# language: fr
Fonctionnalité: Filtres du flux de messages

  Scénario: Filtre par recherche
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et l'historique des messages est vidé
    Quand j'ouvre la page d'accueil
    Quand des messages MQTT sont injectés
    Alors un message est affiché dans le flux
    Quand je tape « inexistant » dans la recherche
    Alors un texte par défaut est affiché dans les messages
    Quand je tape « aldes » dans la recherche
    Alors un message est affiché dans le flux
