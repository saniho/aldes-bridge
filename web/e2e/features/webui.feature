# language: fr
Fonctionnalité: WebUI — chargement et changement de mode

  Scénario: Charger la WebUI et basculer en mode listen
    Étant donné le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors le titre de la page est « Aldes Bridge »
    Et la barre de statut affiche « Mode : proxy »
    Et le sélecteur de mode propose « listen »

    Quand je choisis le mode « listen » dans le sélecteur
    Alors une confirmation est demandée
    Et j'accepte la confirmation
    Alors la barre de statut affiche « Mode : listen »
    Et le mode « listen » est actif côté API