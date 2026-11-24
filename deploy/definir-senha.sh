#!/usr/bin/env bash
# Roda NA VM: define (ou troca) a senha de login do painel. A senha e digitada no terminal, sem eco, e so o hash e gravado.
# Uso:  sudo deploy/definir-senha.sh [usuario]      (padrao: painel)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "rode com sudo" >&2; exit 1; }
cd /opt/quant
sudo -u quant env QUANT_AUTH_FILE=/var/lib/quant/auth.json QUANT_SESSION_KEY=/var/lib/quant/session.key \
    /opt/quant/.venv/bin/python -m quant.auth set-password "${1:-painel}"
