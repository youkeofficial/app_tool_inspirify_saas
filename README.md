# Déploiement du Générateur de Citations (Quote Generator)

Le projet est maintenant **prêt pour la production (Production-Ready)**. 
J'ai analysé l'architecture et vos fichiers Docker et voici un récapitulatif ainsi que les commandes de déploiement.

## 1. Modifications apportées pour la production
Dans le fichier `backend/Dockerfile`, la commande finale `CMD ["python", "app.py"]` exécutait le serveur de développement Flask (qui ne doit jamais être utilisé en production). 
Je l'ai remplacé par `CMD ["waitress-serve", "--port=5000", "app:app"]`. Waitress est un serveur WSGI robuste pour Windows/Linux, déjà listé dans vos dépendances (`requirements.txt`).

## 2. Architecture des ports
Votre projet est découpé en deux conteneurs via `docker-compose.yml` :
- **`inspirify-saas` (Port 5000)** : Le cœur de l'application Flask/Waitress qui génère les images, les audios TTS et les vidéos en appelant l'API.
- **`inspirify-mcp` (Port 8002)** : Le serveur FastMCP (Model Context Protocol) pour permettre à une IA de s'interfacer avec l'API en Server-Sent Events (SSE).

Les deux conteneurs partagent un volume persistant `inspirify_data` monté sur `/app/generated` afin que les fichiers générés survivent aux redémarrages.

## 3. Comment construire (build) l'image Docker
Si vous souhaitez construire l'image manuellement (par exemple, pour la pousser sur un conteneur Hub comme Docker Hub) :

```bash
# Placez-vous à la racine du projet (là où se trouve docker-compose.yml)
cd c:\prog\apps\quote-generator

# Construire l'image (par exemple sous le nom "inspirify-backend:latest")
docker build -t inspirify-backend:latest ./backend
```

*Note : `docker-compose` le fait automatiquement via la configuration `build: context: ./backend` si vous lancez la commande ci-dessous.*

## 4. Comment déployer sur n'importe quel serveur (VPS, Portainer, etc.)
La meilleure façon de déployer sur votre serveur de production est d'utiliser Docker Compose ou Portainer directement.

1. **Copiez le projet sur votre serveur**, ou "pullez" le code depuis votre dépôt Git.
2. Placez-vous dans le dossier racine du projet.
3. Lancez la commande suivante :
   ```bash
   docker-compose up --build -d
   ```

**Si vous utilisez Portainer :**
Vous pouvez déployer directement via le module Stacks.
1. Allez dans "Stacks" -> "Add stack"
2. Copiez/collez le contenu de votre fichier `docker-compose.yml` (ou liez votre repository Git public/privé).
3. Modifiez éventuellement le `build: context:` en remplaçant par l'image pré-buildée si vous ne voulez pas builder sur votre serveur Portainer, mais si vous avez le code il saura le faire (si vous uploadez le dossier backend dans un repository).
4. Cliquez sur "Deploy the stack". 

## 5. Vérification
Une fois déployé :
- L'API HTTP tourne de manière robuste et performante sur : `http://VOTRE_IP_SERVEUR:5000`
- Le serveur MCP tourne (pour que les agents IA l'utilisent en SSE) sur : `http://VOTRE_IP_SERVEUR:8002`

Vous pouvez tester en accédant à l'interface `http://VOTRE_IP_SERVEUR:5000/docs` ou en appelant l'API `/api/v1/library`.
