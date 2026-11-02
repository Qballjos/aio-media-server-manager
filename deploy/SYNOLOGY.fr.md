# Synology : installer AIO pas à pas

Cette route concerne une **nouvelle installation**. Vous créez un projet Container Manager sans écrire de configuration vous-même.

## Avant de commencer

- Un Synology proposant Container Manager dans le Centre de paquets.
- Votre propre compte DSM avec droits administrateur et son mot de passe ; ne supposez pas que le compte admin existe.
- Un ordinateur sur le même réseau ; gardez DSM ouvert.

## 1. Installer Container Manager

Dans le **Centre de paquets**, cherchez Container Manager, installez-le et ouvrez-le.

**Vérification :** File Station affiche le partage docker. Ne le créez pas vous-même avant le paquet. Cette route utilise volume1 ; pour un autre volume, consultez [Avancé](SYNOLOGY_ADVANCED.md).

## 2. Activer le dossier personnel et SSH

Activez **Panneau de configuration → Utilisateur et groupe → Avancé → Service d’accueil utilisateur / User Home Service**. Votre compte reçoit ainsi un dossier personnel pour les médias.

Activez ensuite **Panneau de configuration → Terminal et SNMP → Terminal → Service SSH**, gardez le port 22 et appliquez.

**Vérification :** home apparaît dans File Station et SSH est coché.

## 3. Se connecter au NAS

Ouvrez **Terminal** sur Mac ou **Windows Terminal / PowerShell** sur Windows. Les commandes se saisissent ici, pas dans l’adresse du navigateur. Remplacez utilisateur et IP dans `ssh UTILISATEUR@IP-DU-NAS`. Exemple :

```bash
ssh alex@192.168.1.50
```

Utilisez vos propres valeurs. L’IP se trouve dans l’adresse DSM ou Panneau de configuration → Réseau → Interface réseau. Confirmez la première connexion seulement si l’adresse correspond. Saisissez le mot de passe DSM ; aucun caractère ne s’affiche, c’est normal.

**Vérification :** l’invite indique maintenant votre NAS. La prochaine commande s’exécute dessus.

## 4. Préparer le projet

Collez le bloc entier dans ce terminal connecté, puis Entrée :

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

Le script prépare les dossiers et le fichier ; il ne démarre pas encore AIO. Sudo peut demander le mot de passe DSM.

**Vérification :** Container Manager project files are ready apparaît. Notez le chemin Compose affiché. Arrêtez-vous ici en cas d’erreur.

## 5. Créer le projet dans DSM

Ouvrez **Container Manager → Projet → Créer**.

1. Nom : aio-media-manager.
2. Chemin : le dossier affiché, normalement docker → aio-media-manager.
3. Utilisez le docker-compose.yml déjà créé. Si DSM demande un téléversement, sélectionnez ce fichier généré, sans nouvelle configuration.
4. Gardez les réglages, terminez et démarrez le projet.

**Vérification :** un conteneur aio-media-manager devient actif. Le premier téléchargement peut durer plusieurs minutes.

## 6. Ouvrir le tableau de bord

Ouvrez **http://IP-DU-NAS:8080** avec la vraie adresse.

**Vérification :** AIO propose la création du compte administrateur. Créez-le, terminez l’assistant et choisissez seulement les apps utiles. Les fichiers sont normalement dans File Station → home → aio-media-manager. `exit` ferme SSH ; désactiver SSH ensuite n’arrête pas AIO.

Ensuite : [découvrir le tableau de bord](../docs/USAGE.md).

## En cas de problème

| Problème | Étape suivante |
|---|---|
| Container Manager absent | Vérifiez la compatibilité du modèle ; créer docker manuellement ne remplace pas le paquet. |
| Erreur du script ou Permission denied | Vérifiez compte DSM, Container Manager actif et dossier docker. Conservez le message exact. |
| AIO ne s’ouvre pas | Vérifiez le projet et utilisez l’IP du NAS, pas celle du PC, avec :8080. |

## Avancé

Pour d’autres emplacements, les options SSD, les installations existantes et les réglages techniques : [SYNOLOGY — Avancé](SYNOLOGY_ADVANCED.md).

[Aide officielle du produit: Synology](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project?version=7).
