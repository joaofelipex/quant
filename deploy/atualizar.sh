#!/usr/bin/env bash
# Atualiza o codigo em /opt/quant a partir do pacote que VOCE colocou na caixa de entrada (nao baixa nada da rede).
#   pacote: /var/lib/quant/inbox/quant.tar.gz   (gerado por deploy/enviar-pacote.sh, via SSH)
# Valida o pacote, roda a suite de testes numa copia de staging e SO ENTAO aplica, com backup para reverter.
# Nao reinicia o runner: o codigo novo so vale depois de reiniciar (painel). Reinicia so o painel de controle.
set -euo pipefail
if [ -z "${QUANT_DEPLOY_SELF:-}" ]; then  # roda de uma copia: o proprio script e sobrescrito pela atualizacao
    tmp="$(mktemp /tmp/atualizar.XXXXXX)"; cp "$0" "$tmp"; QUANT_DEPLOY_SELF=1 exec bash "$tmp" "$@"
fi
APP="${QUANT_APP:-/opt/quant}"; DATA="${QUANT_DATA:-/var/lib/quant}"; PY="${QUANT_PY:-$APP/.venv/bin/python}"
IN=$DATA/inbox/quant.tar.gz; STG=$DATA/staging; BK=$DATA/backups; ST=$DATA/deploy.json
TS="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$DATA/inbox" "$BK"

status() {  # status <estado> <mensagem>
    "$PY" - "$ST" "$1" "$2" "$TS" <<'PY'
import json, sys, time
path, state, msg, ts = sys.argv[1:5]
json.dump({"state": state, "msg": msg, "id": ts, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(path, "w"))
PY
}
fail() { status erro "$1"; echo "ERRO: $1" >&2; exit 1; }

[ -f "$IN" ] || fail "nenhum pacote em $IN (rode deploy/enviar-pacote.sh no seu computador)"
status rodando "validando o pacote"
tar -tzf "$IN" >/dev/null 2>&1 || fail "pacote corrompido"
if tar -tzf "$IN" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then fail "pacote com caminho absoluto ou '..' (recusado)"; fi
tar -tzf "$IN" | sed 's#^\./##' | grep -q '^src/quant/__init__.py$' || fail "pacote sem src/quant (nao parece o projeto)"

rm -rf "$STG"; mkdir -p "$STG"; tar -xzf "$IN" -C "$STG"
PYTHONPATH="$STG/src" "$PY" -c "import quant,sys; assert quant.__file__.startswith(sys.argv[1]), quant.__file__" "$STG" \
    || fail "o pacote nao e o que os testes importam (staging)"
status rodando "rodando a suite de testes do pacote"
if ! out="$(cd "$STG" && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$STG/src" "$PY" -m pytest -q -o addopts= -p no:cacheprovider -W ignore 2>&1)"; then
    fail "testes do pacote falharam: $(echo "$out" | tail -1)"
fi
echo "$out" | grep -Eq '[0-9]+ passed' || fail "pytest sem 'passed' (nada foi testado)"
resumo="$(echo "$out" | tail -1)"

status rodando "backup e aplicacao"
tar -czf "$BK/pre-$TS.tar.gz" -C "$APP" --exclude=.venv --exclude='__pycache__' . || fail "falha no backup"
ls -1t "$BK"/pre-*.tar.gz | tail -n +6 | xargs -r rm -f   # guarda os 5 mais recentes
tar -xzf "$IN" -C "$APP" || { tar -xzf "$BK/pre-$TS.tar.gz" -C "$APP"; fail "falha ao extrair; backup restaurado"; }
if ! (cd "$APP" && "$PY" -c "import quant.control, quant.live.config, quant.alerts, quant.selfcheck"); then
    tar -xzf "$BK/pre-$TS.tar.gz" -C "$APP"; fail "codigo novo nao importa; backup restaurado"
fi
mv "$IN" "$DATA/inbox/aplicado-$TS.tar.gz"; ls -1t "$DATA"/inbox/aplicado-*.tar.gz | tail -n +3 | xargs -r rm -f
rm -rf "$STG"
status ok "aplicado ($resumo). Reinicie o runner para usar o codigo novo. Backup: pre-$TS"
[ -n "${QUANT_NO_RESTART:-}" ] || systemctl restart quant-control || true
