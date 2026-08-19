# language: fr
Fonctionnalité: Gestion des modes du bridge

  Scénario: Basculement en mode listen
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors le titre de la page est « Aldes Bridge »
    Et la barre de statut affiche « Mode : proxy »
    Et le sélecteur de mode propose « listen »
    Quand je choisis le mode « listen » dans le sélecteur
    Alors une confirmation est demandée
    Et j'accepte la confirmation
    Alors la barre de statut affiche « Mode : listen »
    Et le mode « listen » est actif côté API

  Scénario: Annulation du changement de mode
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite avec confirmation refusée
    Quand j'ouvre la page d'accueil
    Alors la barre de statut affiche « Mode : proxy »
    Quand je choisis le mode « bridge » dans le sélecteur
    Et je refuse la confirmation
    Alors la barre de statut affiche toujours « Mode : proxy »
    Et le mode « proxy » est actif côté API

  Scénario: Tous les modes sont proposés dans le sélecteur
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors le sélecteur de mode propose « proxy »
    Et le sélecteur de mode propose « bridge »
    Et le sélecteur de mode propose « listen »
    Et le sélecteur de mode propose « raw »
