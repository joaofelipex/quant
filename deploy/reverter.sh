#!/usr/bin/env bash
# Volta o codigo de /opt/quant ao backup mais recente feito por atualizar.sh. Nao reinicia o runner.
set -euo pipefail
if [ -z "${QUANT_DEPLOY_SELF:-}" ]; then
    tmp="$(mktemp /tmp/reverter.XXXXXX)"; cp "$0" "$tmp"; QUANT_DEPLOY_SELF=1 exec bash "$tmp" "$@"
fi
APP="${QUANT_APP:-/opt/quant}"; DATA="${QUANT_DATA:-/var/lib/quant}"; PY="${QUANT_PY:-$APP/.venv/bin/python}"; BK=$DATA/backups; ST=$DATA/deploy.json
TS="$(date -u +%Y%m%dT%H%M%SZ)"
status() {
    "$PY" - "$ST" "$1" "$2" "$TS" <<'PY'
import json, sys, time
path, state, msg, ts = sys.argv[1:5]
json.dump({"state": state, "msg": msg, "id": ts, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(path, "w"))
PY
}
last="$(ls -1t "$BK"/pre-*.tar.gz 2>/dev/null | head -1 || true)"
if [ -z "$last" ]; then status erro "nao ha backup para reverter"; exit 1; fi
tar -xzf "$last" -C "$APP"
(cd "$APP" && "$PY" -c "import quant.control, quant.live.config") || { status erro "backup nao importa"; exit 1; }
mv "$last" "$last.usado"
status ok "revertido para $(basename "$last" .tar.gz). Reinicie o runner para usar o codigo antigo."
[ -n "${QUANT_NO_RESTART:-}" ] || systemctl restart quant-control || true
