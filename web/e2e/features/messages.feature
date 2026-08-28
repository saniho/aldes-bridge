# language: fr
Fonctionnalité: Affichage des messages MQTT

  Scénario: Section messages présente sans correspondance
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Et je tape « __aucun_message__ » dans la recherche
    Alors la section des messages est visible
    Et le compteur de messages filtrés affiche zéro
    Et un texte par défaut est affiché dans les messages
