#!/usr/bin/env bash
#
# k8s/deploy.sh — Déploie Aldes Bridge sur Kubernetes / K3s
#
# Usage:
#   ./k8s/deploy.sh <BRIDGE_IP> <DNS_IP> <UPSTREAM_DNS> [VERSION]
#
# Exemple:
#   ./k8s/deploy.sh 192.168.1.90 192.168.1.91 192.168.1.1 0.3.1
#
# Prérequis: kubectl configuré, accès au cluster.

set -euo pipefail

VERSION="${4:-$(python3 -c "from server import __version__; print(__version__)" 2>/dev/null || echo "latest")}"
NAMESPACE="aldes"
IMAGE="ghcr.io/saniho/aldes-bridge:${VERSION}"

if [ $# -lt 3 ]; then
  echo "Usage: $0 <BRIDGE_IP> <DNS_IP> <UPSTREAM_DNS> [VERSION]"
  echo "  BRIDGE_IP     IP LoadBalancer pour le bridge (MQTT + HTTP)"
  echo "  DNS_IP        IP LoadBalancer pour dnsmasq"
  echo "  UPSTREAM_DNS  IP du DNS upstream (ex: routeur, 8.8.8.8)"
  echo "  VERSION       Tag image (défaut: $VERSION)"
  exit 1
fi

BRIDGE_IP="$1"
DNS_IP="$2"
UPSTREAM_DNS="$3"

echo "==> Namespace:   ${NAMESPACE}"
echo "==> Image:       ${IMAGE}"
echo "==> Bridge IP:   ${BRIDGE_IP}"
echo "==> DNS IP:      ${DNS_IP}"
echo "==> Upstream:    ${UPSTREAM_DNS}"
echo ""

# --- Namespace + PVC + Deployment + Service bridge ---
kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${NAMESPACE}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: aldes-bridge-logs
  namespace: ${NAMESPACE}
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
  namespace: ${NAMESPACE}
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
      containers:
        - name: aldes-bridge
          image: ${IMAGE}
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
  namespace: ${NAMESPACE}
spec:
  type: LoadBalancer
  loadBalancerIP: ${BRIDGE_IP}
  selector:
    app.kubernetes.io/name: aldes-bridge
  ports:
    - name: mqtt-tls
      port: 8883
      targetPort: mqtt-tls
    - name: http
      port: 8080
      targetPort: http
EOF

echo ""
echo "==> Bridge appliqué."

# --- DNS dnsmasq ---
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: aldes-maskdns
  namespace: ${NAMESPACE}
data:
  dnsmasq.conf: |
    address=/aldesiotsuite.azure-devices.net/${BRIDGE_IP}
    server=${UPSTREAM_DNS}
    cache-size=1000
    local-ttl=60
    log-facility=-
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aldes-maskdns
  namespace: ${NAMESPACE}
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
  namespace: ${NAMESPACE}
spec:
  type: LoadBalancer
  loadBalancerIP: ${DNS_IP}
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
EOF

echo "==> DNS appliqué."

# --- Attente rollout ---
echo ""
echo "==> Attente du rollout..."
kubectl rollout status deployment/aldes-bridge -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/aldes-maskdns -n "${NAMESPACE}" --timeout=120s

echo ""
echo "==> État final :"
kubectl get pod,service,pvc -n "${NAMESPACE}"

echo ""
echo "==> Bridge :   curl http://${BRIDGE_IP}:8080/api/config"
echo "==> DNS :      dig @${DNS_IP} aldesiotsuite.azure-devices.net +short"
