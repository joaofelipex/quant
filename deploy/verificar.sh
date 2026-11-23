#!/usr/bin/env bash
# Verificacao pos-instalacao. Rode NA VM, como root:   sudo bash deploy/verificar.sh [dominio]
# So le e consulta; nao altera nada. Sai com codigo 1 se alguma checagem falhar.
set -u
HOST="${1:-quant.mixco.com.br}"
STATE=/var/lib/quant
fail=0

ok()   { printf '  [OK ]  %s\n' "$1"; }
bad()  { printf '  [FALHA] %s\n' "$1"; fail=1; }
check() { local desc="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$desc"; else bad "$desc"; fi; }
mode_is() { [ "$(stat -c %a "$1" 2>/dev/null)" = "$2" ]; }
code_of() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@"; }

echo "== DNS e rede ($HOST)"
check "o dominio resolve (DNS publico aponta para algum IP)" getent hosts "$HOST"

echo "== Paper da carteira (fase 1)"
check "unidade quant-portfolio.service instalada" systemctl cat quant-portfolio.service
check "unidade passa no systemd-analyze verify" systemd-analyze verify /etc/systemd/system/quant-portfolio.service
check "timer habilitado" systemctl is-enabled quant-portfolio.timer
check "timer ativo (proximo disparo agendado)" systemctl is-active quant-portfolio.timer
check "/etc/quant-portfolio.env existe com modo 600" mode_is /etc/quant-portfolio.env 600
if [ ! -f /etc/quant-portfolio.env ]; then
  bad "/etc/quant-portfolio.env nao existe"
elif grep -Eiq 'BINANCE|SECRET|ALLOW_MAINNET' /etc/quant-portfolio.env; then
  bad "/etc/quant-portfolio.env contem chave de corretora (nao deveria)"
else
  ok "/etc/quant-portfolio.env sem chave de corretora"
fi
check "diretorio de estado pertence ao usuario quant" test "$(stat -c %U $STATE 2>/dev/null)" = quant
if [ -f "$STATE/portfolio_log.csv" ]; then
  last=$(tail -n1 "$STATE/portfolio_log.csv" | cut -d, -f1)
  age=$(( ( $(date -u +%s) - $(date -u -d "$last" +%s 2>/dev/null || echo 0) ) / 86400 ))
  [ "$age" -le 2 ] && ok "ultimo dia do log: $last (${age}d)" || bad "log desatualizado: ultimo dia $last (${age}d)"
else
  bad "portfolio_log.csv ainda nao existe (rode: systemctl start quant-portfolio.service)"
fi

echo "== Painel (nginx + HTTPS)"
check "nginx -t" nginx -t
check "index.html gerado nas ultimas 26 h" test -n "$(find /var/www/quant/index.html -mmin -1560 2>/dev/null)"
http=$(code_of --resolve "$HOST:80:127.0.0.1" "http://$HOST/")
[ "$http" = 301 ] && ok "HTTP :80 redireciona (301), nao serve o painel" || bad "HTTP :80 devolveu $http (esperado 301; nunca 200 nem 401)"
sem=$(code_of --resolve "$HOST:443:127.0.0.1" "https://$HOST/")
[ "$sem" = 401 ] && ok "HTTPS sem senha pede autenticacao (401) com certificado valido" \
  || bad "HTTPS sem senha devolveu $sem (esperado 401; 000 = certificado/porta com problema)"
check "certificado Let's Encrypt existe" test -f "/etc/letsencrypt/live/$HOST/fullchain.pem"

echo "== Runner (fase 2; so se ja foi instalado)"
if systemctl cat quant-live.service >/dev/null 2>&1; then
  check "unidade passa no systemd-analyze verify" systemd-analyze verify /etc/systemd/system/quant-live.service
  check "/etc/quant-live.env com modo 600" mode_is /etc/quant-live.env 600
  if grep -Eq '^QUANT_MODE=live' /etc/quant-live.env 2>/dev/null; then bad "QUANT_MODE=live: so com estrategia aprovada pela regra do repo"; else ok "QUANT_MODE nao e live"; fi
  if [ -e "$STATE/KILL" ]; then bad "arquivo KILL presente (kill-switch acionado)"; else ok "sem arquivo KILL"; fi
  echo "     estado do servico: $(systemctl is-active quant-live.service)"
else
  echo "  (quant-live.service nao instalado: ok, so a partir da fase 2)"
fi

echo
[ "$fail" = 0 ] && echo "Tudo certo." || echo "Ha checagens com FALHA acima."
exit "$fail"
