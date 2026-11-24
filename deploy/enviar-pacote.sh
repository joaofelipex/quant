#!/usr/bin/env bash
# Roda no SEU computador (Git Bash), na raiz do repo: monta o painel Angular, empacota o HEAD + o build e coloca o pacote
# na caixa de entrada da VM. Depois, no painel /controle/ (Gestao), clique em "Atualizar codigo".
# Uso:  deploy/enviar-pacote.sh CAMINHO_DA_CHAVE_SSH [usuario@host]      (precisa de Node/npm; SKIP_WEB=1 pula o build)
set -euo pipefail
KEY="${1:?uso: deploy/enviar-pacote.sh CAMINHO_DA_CHAVE_SSH [usuario@host]}"; HOST="${2:-ubuntu@129.80.27.120}"
[ -z "$(git status --porcelain --untracked-files=no)" ] || echo "AVISO: ha mudancas nao commitadas; so o HEAD vai no pacote" >&2
SHA="$(git rev-parse --short HEAD)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
git archive --format=tar HEAD > "$TMP/pkg.tar"
if [ -z "${SKIP_WEB:-}" ]; then
    (cd web && npm ci --no-audit --no-fund && npm run build)
    tar -rf "$TMP/pkg.tar" -C web/dist/web --transform 's,^browser,web-dist,' browser   # build vai para /opt/quant/web-dist
fi
gzip -c "$TMP/pkg.tar" | ssh -i "$KEY" "$HOST" \
    'cat > /tmp/quant.tar.gz && sudo install -d -m 750 -o quant -g quant /var/lib/quant/inbox && \
     sudo install -m 640 -o quant -g quant /tmp/quant.tar.gz /var/lib/quant/inbox/quant.tar.gz && rm /tmp/quant.tar.gz && \
     echo "pacote pronto na caixa de entrada; clique em Atualizar no painel"'
echo "enviado: $SHA"
