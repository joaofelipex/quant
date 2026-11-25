#!/usr/bin/env bash
# Grava a chave da API da Anthropic (a "cabeca" do agente de IA) em /etc/quant/agent.env sem aparecer na tela, no historico
# do shell nem no chat. Rode NA VM, num terminal seu:   sudo bash deploy/definir-chave-ia.sh
set -euo pipefail
ENV=/etc/quant/agent.env
[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 2; }
read -rsp "Chave da API Anthropic (nao aparece ao digitar): " KEY; echo
if ! [[ $KEY =~ ^sk-ant-[A-Za-z0-9_-]{20,}$ ]]; then
  echo "formato invalido (esperado: sk-ant-...). Nada foi gravado."; exit 2
fi
install -d -m 0750 -o root -g quant /etc/quant
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" > "$tmp"
install -m 0640 -o root -g quant "$tmp" "$ENV"
echo "chave gravada em $ENV (modo 640, dono root:quant). Nada foi impresso."
echo "proximo passo: ligue o agente em IA > Ligar, ou rode um ciclo: sudo -u quant bash -c 'set -a; . /etc/quant-live.env; . $ENV; set +a; /opt/quant/.venv/bin/python -m quant.agent run --force'"
