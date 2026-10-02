#!/bin/bash
# Instala e publica o Estoque Inteligente em uma EC2 Amazon Linux 2023.
#
# Uso (dentro da EC2, como ec2-user: no Session Manager rode antes "sudo su - ec2-user"):
#   curl -fsSL https://raw.githubusercontent.com/<usuario>/<repo>/main/deploy/setup_ec2.sh -o setup.sh
#   bash setup.sh https://github.com/<usuario>/<repo>.git
#
# Rodar de novo atualiza o código (git pull), refaz o build e reinicia tudo.
set -euo pipefail

REPO_URL="${1:-}"
APP_DIR=/opt/estoque

echo "==> 1/6 Instalando pacotes (git, nginx, Python 3.11, Node.js)"
sudo dnf install -y -q git nginx python3.11 python3.11-pip tar xz nano
# Node.js 20 (binário oficial) para fazer o build do React
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
  ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/')
  curl -fsSL "https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-${ARCH}.tar.xz" \
    | sudo tar -xJ -C /usr/local --strip-components=1
fi
node --version

echo "==> 2/6 Baixando o código"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  [ -n "$REPO_URL" ] || { echo "Informe a URL do repositório: bash setup.sh <URL>"; exit 1; }
  sudo mkdir -p "$APP_DIR"
  sudo chown ec2-user:ec2-user "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> 3/6 Backend: ambiente virtual Python + dependências"
cd "$APP_DIR/backend"
[ -d venv ] || python3.11 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "    !! Criei backend/.env a partir do exemplo. Preencha S3_BUCKET (obrigatório)."
fi

echo "==> 4/6 Frontend: build do React"
cd "$APP_DIR/frontend"
npm install --no-audit --no-fund --loglevel=error
npm run build

echo "==> 5/6 Configurando nginx e o serviço da API"
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/nginx.conf
sudo cp "$APP_DIR/deploy/estoque.service" /etc/systemd/system/estoque.service
sudo chmod 755 "$APP_DIR"
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now nginx estoque
sudo systemctl restart estoque nginx

echo "==> 6/6 Verificando"
sleep 4
if curl -fsS http://localhost/api/health; then
  echo
else
  echo "    A API não respondeu. Veja os logs com: sudo journalctl -u estoque -n 50"
fi

TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)
PRIVATE_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)
echo
echo "Pronto! Acesse:            http://${PUBLIC_IP:-<IP-PUBLICO>}"
echo "URL para a Lambda (VPC):   http://${PRIVATE_IP}"
