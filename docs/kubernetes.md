# Déploiement dans Kubernetes

Ce guide déploie Aldes Bridge directement dans un cluster Kubernetes ou K3s,
sans machine virtuelle dédiée. Il reprend la même architecture que l'installation
Docker : le bridge écoute la box en MQTT/TLS sur le port 8883 et expose son API
et sa WebUI sur le port 8080.

## Prérequis

- un cluster capable d'exposer des services sur le réseau local, par exemple avec
  MetalLB ;
- une StorageClass fournissant des volumes `ReadWriteOnce` ;
- une adresse IP fixe pour le bridge et une autre pour le serveur DNS local ;
- la possibilité de distribuer l'adresse du serveur DNS avec le DHCP du réseau.

L'exemple utilise le namespace `aldes`, `<BRIDGE_IP>` pour l'adresse du bridge,
`<DNS_IP>` pour celle de dnsmasq et `<UPSTREAM_DNS>` pour le DNS habituel du
réseau. Ces valeurs doivent être remplacées avant l'application des manifests.

## Image conteneur

Chaque push sur `main` publie une image dans GitHub Container Registry avec les
tags `latest` et un tag immuable construit à partir du commit :

```text
ghcr.io/saniho/aldes-bridge:sha-<commit>
```

La création d'un tag Git `vX.Y.Z` publie également les tags d'image `X.Y.Z` et
`X.Y`. Le tag SemVer complet est recommandé pour les déploiements courants ; le
tag SHA permet de verrouiller exactement le code exécuté :

```text
ghcr.io/saniho/aldes-bridge:0.3.1
ghcr.io/saniho/aldes-bridge:sha-<commit>
```

La page `Packages` du dépôt indique le tag disponible. Si le paquet est privé,
créer un secret de registre dans le namespace :

```bash
kubectl create namespace aldes
kubectl create secret docker-registry ghcr-aldes-bridge \
  --namespace aldes \
  --docker-server ghcr.io \
  --docker-username '<utilisateur-github>' \
  --docker-password '<token-read-packages>'
```

Le token doit uniquement disposer du droit `read:packages`. Cette étape est
inutile lorsque l'image est publique ; dans ce cas, supprimer `imagePullSecrets`
du Deployment ci-dessous.

## Bridge

Enregistrer le manifest suivant dans `aldes-bridge.yaml`, remplacer l'image et
les valeurs propres au cluster, puis l'appliquer :

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: aldes
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: aldes-bridge-logs
  namespace: aldes
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aldes-bridge
  namespace: aldes
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: aldes-bridge
  template:
    metadata:
      labels:
        app.kubernetes.io/name: aldes-bridge
    spec:
      imagePullSecrets:
        - name: ghcr-aldes-bridge
      containers:
        - name: aldes-bridge
          image: ghcr.io/saniho/aldes-bridge:0.3.1
          imagePullPolicy: IfNotPresent
          env:
            - name: ALDES_MODE
              value: bridge
            - name: ALDES_BOX_TZ
              value: Europe/Paris
            - name: TZ
              value: Europe/Paris
          ports:
            - name: mqtt-tls
              containerPort: 8883
            - name: http
              containerPort: 8080
          volumeMounts:
            - name: logs
              mountPath: /app/logs
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /api/config
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /api/config
              port: http
            initialDelaySeconds: 30
            periodSeconds: 30
      volumes:
        - name: logs
          persistentVolumeClaim:
            claimName: aldes-bridge-logs
---
apiVersion: v1
kind: Service
metadata:
  name: aldes-bridge
  namespace: aldes
spec:
  type: LoadBalancer
  loadBalancerIP: <BRIDGE_IP>
  selector:
    app.kubernetes.io/name: aldes-bridge
  ports:
    - name: mqtt-tls
      port: 8883
      targetPort: mqtt-tls
    - name: http
      port: 8080
      targetPort: http
```

```bash
kubectl apply -f aldes-bridge.yaml
kubectl get pod,service,pvc -n aldes
curl "http://<BRIDGE_IP>:8080/api/config"
```

## Redirection DNS dans Kubernetes

La box Aldes doit résoudre `aldesiotsuite.azure-devices.net` vers `<BRIDGE_IP>`.
Le déploiement suivant fournit cette redirection avec dnsmasq et relaie toutes
les autres requêtes vers `<UPSTREAM_DNS>`.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: aldes-maskdns
  namespace: aldes
data:
  dnsmasq.conf: |
    address=/aldesiotsuite.azure-devices.net/<BRIDGE_IP>
    server=<UPSTREAM_DNS>
    cache-size=1000
    local-ttl=60
    log-facility=-
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aldes-maskdns
  namespace: aldes
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: aldes-maskdns
  template:
    metadata:
      labels:
        app.kubernetes.io/name: aldes-maskdns
    spec:
      containers:
        - name: dnsmasq
          image: docker.io/dockurr/dnsmasq:2.91
          ports:
            - name: dns-tcp
              containerPort: 53
              protocol: TCP
            - name: dns-udp
              containerPort: 53
              protocol: UDP
          volumeMounts:
            - name: config
              mountPath: /etc/dnsmasq.conf
              subPath: dnsmasq.conf
              readOnly: true
          resources:
            requests:
              cpu: 10m
              memory: 16Mi
            limits:
              cpu: 100m
              memory: 64Mi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
              add:
                - NET_BIND_SERVICE
      volumes:
        - name: config
          configMap:
            name: aldes-maskdns
---
apiVersion: v1
kind: Service
metadata:
  name: aldes-maskdns
  namespace: aldes
spec:
  type: LoadBalancer
  loadBalancerIP: <DNS_IP>
  selector:
    app.kubernetes.io/name: aldes-maskdns
  ports:
    - name: dns-tcp
      port: 53
      targetPort: dns-tcp
      protocol: TCP
    - name: dns-udp
      port: 53
      targetPort: dns-udp
      protocol: UDP
```

Après application, configurer le DHCP du réseau pour distribuer `<DNS_IP>` comme
serveur DNS, puis contrôler les réponses :

```bash
dig @<DNS_IP> aldesiotsuite.azure-devices.net +short
dig @<DNS_IP> github.com +short
```

La première commande doit renvoyer `<BRIDGE_IP>` et la seconde une adresse
publique normale.

## Vérifications

```bash
openssl s_client \
  -connect <BRIDGE_IP>:8883 \
  -servername aldesiotsuite.azure-devices.net \
  </dev/null

curl "http://<BRIDGE_IP>:8080/api/config"
kubectl logs -n aldes deployment/aldes-bridge --follow
```

Le certificat présenté sur le port 8883 est autosigné et doit avoir pour CN
`aldesiotsuite.azure-devices.net`. Lorsque la box est connectée, `/api/config`
renvoie `connected: true`.

La télémétrie thermique n'est pas publiée à l'ouverture de la connexion MQTT.
Sur le matériel testé, les messages `MT*` et `UsC*` arrivent par rafales environ
toutes les 30 minutes, avec des publications supplémentaires possibles lors de
changements d'état. Un redémarrage du pod ne déclenche donc pas nécessairement
une nouvelle mesure.

## Mise à jour

Remplacer le tag de version dans le Deployment, puis appliquer le manifest :

```bash
kubectl apply -f aldes-bridge.yaml
kubectl rollout status deployment/aldes-bridge -n aldes
```

Le PVC conserve l'historique, la télémétrie et le mode sélectionné entre deux
versions du conteneur.
