#!/usr/bin/env bash
# Roda no SEU computador (Git Bash), na raiz do repo: empacota o HEAD e coloca na caixa de entrada da VM.
# Depois, no painel /controle/, clique em "Atualizar". Uso:  deploy/enviar-pacote.sh ~/Downloads/ssh-key-....key
set -euo pipefail
KEY="${1:?uso: deploy/enviar-pacote.sh CAMINHO_DA_CHAVE_SSH [usuario@host]}"; HOST="${2:-ubuntu@129.80.27.120}"
[ -z "$(git status --porcelain --untracked-files=no)" ] || echo "AVISO: ha mudancas nao commitadas; so o HEAD vai no pacote" >&2
SHA="$(git rev-parse --short HEAD)"
git archive --format=tar.gz HEAD | ssh -i "$KEY" "$HOST" \
    'cat > /tmp/quant.tar.gz && sudo install -d -m 750 -o quant -g quant /var/lib/quant/inbox && \
     sudo install -m 640 -o quant -g quant /tmp/quant.tar.gz /var/lib/quant/inbox/quant.tar.gz && rm /tmp/quant.tar.gz && \
     echo "pacote pronto na caixa de entrada; clique em Atualizar no painel"'
echo "enviado: $SHA"
