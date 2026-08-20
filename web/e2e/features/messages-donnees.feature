# language: fr
Fonctionnalité: Messages MQTT avec données

  Scénario: Injection d'un message et affichage
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et l'historique des messages est vidé
    Quand j'ouvre la page d'accueil
    Quand des messages MQTT sont injectés
    Alors un message est affiché dans le flux
    Et le compteur de messages affiche au moins une valeur
