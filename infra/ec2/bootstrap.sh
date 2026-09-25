#!/bin/bash
# User data para EC2 Ubuntu 24.04 LTS.
# Pegar en: Launch instance → Advanced details → User data.
# Se ejecuta una sola vez, como root, en el primer arranque.
set -euxo pipefail

apt-get update -y
apt-get install -y ca-certificates curl

# Docker Engine + Compose v2 desde el repositorio oficial de Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin jq

systemctl enable --now docker
usermod -aG docker ubuntu

# Carpeta de la app
mkdir -p /opt/cueva
chown ubuntu:ubuntu /opt/cueva

# SSH solo con llave (R1)
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh || true

# Swap de 1 GB (las instancias micro tienen 1 GB de RAM)
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
