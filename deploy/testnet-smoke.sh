#!/usr/bin/env bash
# Roda a checagem de fumaca da testnet como o usuario 'quant', com as chaves de /etc/quant-live.env.
# As chaves passam pelo systemd (EnvironmentFile) e nunca aparecem na tela nem na lista de processos.
# Rode NA VM:   sudo bash deploy/testnet-smoke.sh        (docs/roteiro_testnet.md, secao 1)
set -euo pipefail
ENV=/etc/quant-live.env

[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 2; }
[ -f "$ENV" ] || { echo "$ENV nao existe"; exit 2; }
if grep -q '^QUANT_MODE=live' "$ENV"; then echo "RECUSADO: QUANT_MODE=live"; exit 2; fi
grep -Eq '^BINANCE_API_KEY=.+' "$ENV" || { echo "chaves vazias: rode antes  sudo bash deploy/definir-chaves.sh"; exit 2; }

exec systemd-run --quiet --pipe --wait --collect \
  -p User=quant -p EnvironmentFile="$ENV" -p WorkingDirectory=/opt/quant -p NoNewPrivileges=yes -p PrivateTmp=yes \
  /opt/quant/.venv/bin/python -m quant.live.testnet_check
