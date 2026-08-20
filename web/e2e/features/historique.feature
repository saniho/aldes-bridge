# language: fr
Fonctionnalité: Historique des valeurs

  Scénario: Le menu historique affiche les valeurs injectées
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et des télémétries numériques sont injectées
    Quand j'ouvre la page d'accueil
    Et je clique sur le menu burger
    Et je clique sur l'item de menu « 📊 historique »
    Alors le panneau historique est visible
    Et une valeur historique est affichée