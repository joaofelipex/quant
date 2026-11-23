#!/usr/bin/env bash
# Grava as chaves da Binance (TESTNET/DEMO) em /etc/quant-live.env sem aparecer na tela, no historico do shell nem no chat.
# Rode NA VM, num terminal seu:   sudo bash deploy/definir-chaves.sh
set -euo pipefail
ENV=/etc/quant-live.env

[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 2; }
[ -f "$ENV" ] || { echo "$ENV nao existe: instale-o antes (deploy/README.md, fase 2)"; exit 2; }
if grep -q '^QUANT_MODE=live' "$ENV"; then
  echo "RECUSADO: QUANT_MODE=live. Este script so grava chaves de testnet/demo."; exit 2
fi

read -rsp "API key da TESTNET/DEMO (nao aparece ao digitar): " KEY; echo
read -rsp "API secret da TESTNET/DEMO (nao aparece ao digitar): " SECRET; echo
if ! [[ $KEY =~ ^[A-Za-z0-9]{20,}$ && $SECRET =~ ^[A-Za-z0-9]{20,}$ ]]; then
  echo "formato invalido (esperado: letras e numeros, 20+ caracteres). Nada foi gravado."; exit 2
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
grep -vE '^(BINANCE_API_KEY|BINANCE_API_SECRET)=' "$ENV" > "$tmp" || true
printf 'BINANCE_API_KEY=%s\nBINANCE_API_SECRET=%s\n' "$KEY" "$SECRET" >> "$tmp"
install -m 0600 -o root -g root "$tmp" "$ENV"
echo "chaves gravadas em $ENV (modo 600, dono root). Nada foi impresso."
echo "proximo passo:  sudo bash deploy/testnet-smoke.sh"
