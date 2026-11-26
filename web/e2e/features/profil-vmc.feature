# language: fr
Fonctionnalité: Profil VMC inspirair-home-s

  Scénario: Le profil VMC adapte le tableau de bord
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Et je clique sur l'onglet « vue d'ensemble »
    Alors le texte « Capteurs » n'est pas affiché
    Et le texte « Présence » est affiché
    Et le texte « Eau chaude » est affiché
    Quand je change le profil pour « inspirair-home-s »
    Alors le texte « Capteurs » est affiché
    Et le texte « Présence » n'est pas affiché
    Et le texte « Eau chaude » n'est pas affiché

  Scénario: Le profil VMC adapte les modes rapides
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Et je clique sur l'onglet « infos aldes »
    Alors le texte « Climatisation » est affiché
    Et le texte « Temp. principale » est affiché
    Quand je change le profil pour « inspirair-home-s »
    Alors le texte « Climatisation » n'est pas affiché
    Et le texte « Ventilation » est affiché
    Et le texte « Temp. principale » n'est pas affiché

  Scénario: L'onglet santé affiche les cartes de la VMC
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Et je clique sur l'onglet « santé »
    Alors le texte « Qualité d'air » n'est pas affiché
    Quand je change le profil pour « inspirair-home-s »
    Alors le texte « Qualité d'air » est affiché
    Et le texte « État de l'installation » est affiché
    Et le texte « Dégivrage (Defr) » n'est pas affiché
