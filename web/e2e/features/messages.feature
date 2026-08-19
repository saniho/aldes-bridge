# language: fr
Fonctionnalité: Affichage des messages MQTT

  Scénario: Section messages présente avec état vide
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Et l'historique des messages est vidé
    Quand j'ouvre la page d'accueil
    Alors la section des messages est visible
    Et le compteur de messages affiche « 0 / 0 »
    Et un texte par défaut est affiché dans les messages
