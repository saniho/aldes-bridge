#!/usr/bin/env bash
set -e

# Aldes Bridge - DNS setup script
# Installs and configures dnsmasq to redirect
# aldesiotsuite.azure-devices.net to the local server

echo "[*] Installation de dnsmasq..."
apt-get update -qq
apt-get install -y -qq dnsmasq

echo "[*] Configuration..."
cat > /etc/dnsmasq.d/aldes.conf << 'CONF'
interface=eth0
bind-interfaces
address=/aldesiotsuite.azure-devices.net/192.168.1.90
server=192.168.1.254
listen-address=192.168.1.90
port=53
CONF

# Disable default config
mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak 2>/dev/null || true
echo "" > /etc/dnsmasq.conf

echo "[*] Démarrage du service..."
systemctl enable dnsmasq
systemctl restart dnsmasq

echo "[*] Vérification..."
dig @127.0.0.1 aldesiotsuite.azure-devices.net +short

echo "[+] DNS configuré avec succès !"
echo ""
echo "Configure maintenant ta Freebox :"
echo "  1. http://mafreebox.freebox.fr"
echo "  2. Mode avancé > Réseau local > DHCP"
echo "  3. DNS 1 = 192.168.1.90"
echo "  4. Appliquer"
