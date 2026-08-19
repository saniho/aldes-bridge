# language: fr
Fonctionnalité: Déconnexion de la box

  Scénario: Bouton déconnecter non visible quand déconnecté
    Étant donné le mode du bridge est à proxy
    Et le bridge sert la WebUI construite
    Quand j'ouvre la page d'accueil
    Alors le bouton déconnecter n'est pas visible
