# Operação da VM

Instalação do zero: [`deploy/README.md`](../deploy/README.md). Aqui está o dia a dia. Os comandos rodam na VM, salvo
indicação.

## Serviços

| Unidade | Função | Frequência |
|---|---|---|
| `quant-live.service` | robô de regras | contínuo |
| `quant-control.service` | painel e API | contínuo |
| `quant-agent.timer` | IA | a cada minuto (age no intervalo dela) |
| `quant-metrics.timer` | retrato da conta | 2 min |
| `quant-flow.timer` | foto do livro | 1 min |
| `quant-alert.timer` | alertas (Telegram, e-mail) | 1 min |
| `quant-selfcheck.timer` | testes e saúde | 4× por dia |
| `quant-portfolio.timer` | paper da carteira | 00:10 UTC |
| `quant-order.service` | boleta | sob demanda |
| `quant-agent-agora.service` | ciclo da IA agora | sob demanda |
| `quant-deploy.service`, `quant-rollback.service` | publicar, reverter | sob demanda |

```bash
systemctl is-active quant-live quant-control
sudo journalctl -u quant-live -n 100 --no-pager
systemctl list-timers 'quant-*'
```

## Publicar

No seu computador (Git Bash, raiz do repositório; só o `HEAD` commitado vai no pacote):

```bash
deploy/enviar-pacote.sh CAMINHO_DA_CHAVE_SSH
```

Depois, no painel (**Gestão → Atualizar código**) ou na VM:

```bash
sudo systemctl start quant-deploy.service
sudo cat /var/lib/quant/deploy.json
```

O script testa o pacote numa cópia, faz backup (guarda os 5 últimos), aplica e reinicia **só o painel**.

```bash
sudo systemctl restart quant-live     # necessário para o robô usar o código novo
```

## Reverter

**Gestão → Reverter**, ou `sudo systemctl start quant-rollback.service`; depois reinicie o robô.

## Mudar parâmetros

Painel (**Operar**) e reiniciar o robô. Antes de uma mudança importante, guarde uma cópia:

```bash
sudo cp -p /var/lib/quant/runtime.env /var/lib/quant/runtime.env.antes-$(date -u +%Y%m%dT%H%M%SZ)
```

## Parar tudo

```bash
sudo -u quant touch /var/lib/quant/KILL
```

Fecha as posições do robô e o encerra; a IA recusa novas ações. Para retomar:

1. Confira na corretora que não há posição aberta.
2. Remova o `KILL` pela VM (o painel não remove).
3. Destrave o risco no painel (admin) e ligue o robô.

Parar o serviço (`systemctl stop quant-live`) **não** fecha posições; os stops continuam na corretora.

## Quando algo dá errado

| Sintoma | Onde olhar |
|---|---|
| Robô não entra | motivo na tela Ao vivo; `journalctl -u quant-live`; ER abaixo do mínimo é o caso comum |
| Ativo travado | motivo em `live_state.<ATIVO>.json`; *Destravar risco* |
| "posição órfã" | posição aberta sem stop conhecido: feche pela Boleta ou na corretora |
| "ativo fora" no início | menor contrato acima de 1,5 × `QUANT_NOTIONAL` |
| IA sem agir | ligada? intervalo? crédito da chave? `journalctl -u quant-agent` |
| Painel sem números | `quant-metrics.timer` |
| Publicação falhou | `deploy.json`; o backup é restaurado se a aplicação falhar |
| Histórico diverge da corretora | `python -m quant.reconcile` (só mostra; `--aplicar` grava, com robô e IA parados) |

## Rodar um diagnóstico com o código da VM

Como o usuário `quant`, sem chaves:

```bash
cd /var/lib/quant && sudo -u quant env PYTHONPATH=/opt/quant/src /opt/quant/.venv/bin/python -m quant.flow study
```

## Ao reiniciar a VM

Confirme que o robô voltou: `systemctl is-active quant-live`. Para ele subir sozinho, o serviço precisa estar
habilitado (`systemctl is-enabled quant-live`).
