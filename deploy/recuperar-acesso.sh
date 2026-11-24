#!/usr/bin/env bash
# Roda NA VM. Recuperacao de acesso ao painel, sem precisar do navegador:
#   sudo deploy/recuperar-acesso.sh senha USUARIO     cria um admin com esse nome ou troca a senha dele (digitada sem eco)
#   sudo deploy/recuperar-acesso.sh 2fa USUARIO       remove o 2FA do usuario
#   sudo deploy/recuperar-acesso.sh token             mostra o token do primeiro acesso (so existe se nao ha usuarios)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "rode com sudo" >&2; exit 1; }
cd /opt/quant
run() { sudo -u quant env QUANT_AUTH_DIR=/var/lib/quant /opt/quant/.venv/bin/python -m quant.auth "$@"; }
case "${1:-}" in
    senha) run set-password "${2:?informe o usuario}" ;;
    2fa) run reset-2fa "${2:?informe o usuario}" ;;
    token) cat /var/lib/quant/setup-token 2>/dev/null || echo "sem token: ja existem usuarios" ;;
    *) sed -n '2,6p' "$0"; exit 2 ;;
esac
