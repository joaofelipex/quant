#!/usr/bin/env bash
# Prepara a CLI do Claude para o agente de IA: copia o binario para /usr/local/bin e abre o login da SUA conta como o
# usuario do servico (quant), numa pasta so dele. Voce faz o login no navegador; nada passa pelo painel nem por mim.
#   sudo bash /opt/quant/deploy/login-claude-cli.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 1; }
SRC="${1:-$(getent passwd ubuntu | cut -d: -f6)/.local/bin/claude}"
[ -x "$SRC" ] || { echo "CLI nao encontrada em $SRC (instale com: curl -fsSL https://claude.ai/install.sh | bash)"; exit 1; }
install -m 0755 "$(readlink -f "$SRC")" /usr/local/bin/claude
install -d -o quant -g quant -m 0700 /var/lib/quant/claude-home
echo "Abrindo a CLI como 'quant'. Dentro dela: /login, escolha a conta, autorize no navegador, depois /exit."
sudo -u quant env HOME=/var/lib/quant/claude-home /usr/local/bin/claude
if [ -s /var/lib/quant/claude-home/.claude/.credentials.json ]; then
  echo "login gravado para o agente."
else
  echo "login NAO encontrado: rode de novo e conclua o /login"; exit 1
fi
