# language: fr
Fonctionnalité: Affichage des messages MQTT

  Scénario: Section messages présente avec état vide
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors la section des messages est visible
    Et le compteur de messages affiche au moins une valeur
