# Roteiro de validação na testnet (Binance USD-M)

**Objetivo:** provar que o *encanamento* de execução (`src/quant/live`) faz na exchange o que os testes com ccxt falso
dizem que faz. **Não valida nenhuma estratégia**: preços e liquidez da testnet não são os reais, então o resultado de
PnL aqui não significa nada. Nada neste roteiro libera conta real; isso continua dependendo da regra do README
(estratégia aprovada, DSR ≥ 0,95).

## 0. Preparação

1. Escolha **um** ambiente de teste da Binance e crie as chaves nele (as chaves de um não valem no outro):
   - `testnet`: sandbox legado de futuros (`testnet.binancefuture.com`);
   - `demo`: Demo Trading, dentro da conta da Binance (`demo-fapi.binance.com`).
   Confira na documentação da Binance qual está ativo para o seu perfil hoje; o formato mudou nos últimos anos.
2. Permissões da chave: **só futuros/trading, sem saque**; restrinja por IP se o ambiente permitir.
3. Chaves só em variáveis de ambiente / `.env` (copie `deploy/quant-live.env.example`). **Nunca** no chat, no git
   nem em print.
4. `pip install -e ".[live]"`.

```bash
export BINANCE_API_KEY=...        # chaves de TESTE
export BINANCE_API_SECRET=...
export QUANT_TESTNET_KIND=testnet # ou demo
export QUANT_SYMBOL=ETH/USDT:USDT QUANT_QTY=0.01
```

## 1. Checagem automática (5 minutos)

```bash
python -m quant.live.testnet_check
```

Abre e fecha **uma** posição mínima e confere cada promessa do executor. O script só fala com testnet/demo: aborta
se a URL da API não for de teste e não toca em posição que já exista na conta.

| Checagem | Se falhar, significa |
|---|---|
| conta sem posição aberta | feche a posição de teste na interface e rode de novo |
| ordem a mercado preenche | permissão da chave, símbolo ou `QUANT_QTY` abaixo do mínimo da exchange |
| preço do fill a menos de 1% do ticker | testnet ilíquida ou preço médio lido errado em `market_order` |
| taxa informada (> 0) | `_fee` caiu no fallback; veja o aviso "taxa ... estimando" no log |
| posição reconhecida pela corretora | `position()` lê lado/quantidade errado (ex.: modo hedge) |
| stop protetor aceito (devolve id) | `STOP_MARKET` com `reduceOnly` rejeitado; leia o erro da exchange |
| `has_stop()` enxerga o stop | a detecção de tipo/`reduceOnly` do ccxt não bate com o que a exchange devolve |
| `cancel_stops()` remove o stop | `cancel_all_orders` não limpa ordens condicionais neste ambiente |
| saída reduce-only fecha a posição | ordem de saída bloqueada com stop pendente |
| conta limpa ao final | sobrou posição ou stop: limpe na interface antes de qualquer outro teste |

**Passa quando:** todas as checagens ficam `OK` em **3 execuções em dias diferentes**. Anote cada uma em §4.

## 2. Ensaios com o runner (um por vez, em primeiro plano; não use o systemd)

Rode em `QUANT_MODE=testnet` com `QUANT_TIMEFRAME=1m` para surgir sinal mais rápido (a testnet tem dados ralos; é
teste de encanamento). Pode levar horas até a primeira entrada. Registre o log de cada ensaio.

| # | Ensaio | Como | Resultado esperado |
|---|---|---|---|
| A | Entrada ponta a ponta | deixe o runner até a 1ª entrada | log "entrada ... stop=..." e **um stop `STOP_MARKET` reduce-only** visível na interface |
| B | Processo morre com posição | com posição aberta, mate o processo (`Stop-Process -Force`) | o stop continua na exchange; ao reiniciar, estado restaurado e **sem** "posição órfã" |
| C | Stop apagado à mão | cancele o stop na interface | em até 1 barra: "stop protetor sumiu ... recolocando" e o stop volta |
| D | Stop da corretora dispara | aproxime o stop do preço (ou espere um movimento) | "posição fechada fora do runner" com PnL estimado próximo do real |
| E | Kill-switch | `New-Item KILL` | fecha a posição, **cancela os stops**, estado `halted`, processo encerra |
| F | Rede cai com posição | derrube a rede 2–3 barras e restaure | stop conferido nas barras perdidas; **nenhuma entrada duplicada** |
| G | Perda diária | `QUANT_MAX_DAILY_LOSS=1` e deixe perder | "perda diária atingiu", entradas bloqueadas, saídas continuam funcionando |
| H | Dado atrasado | pause o feed (ou o relógio) além de 120 s | entrada "bloqueada: dado atrasado"; nenhuma ordem enviada |

Atenção ao ensaio E: com `Restart=always` o systemd religa o runner enquanto o arquivo `KILL` existir (problema
conhecido, ainda não corrigido). Por isso estes ensaios são em primeiro plano.

## 3. Critério para avançar

1. Checagem automática `OK` em 3 dias diferentes.
2. Ensaios A–H feitos e registrados, todos no resultado esperado.
3. Pelo menos 2 semanas com o runner na testnet sem posição órfã, ordem duplicada ou stop faltando.
4. Só então discutir conta real, o que **também** exige estratégia aprovada pela regra do README e uma revisão
   de regulação e tributação do seu caso (isto não é consultoria financeira).

Qualquer falha: corrija, escreva um teste que reproduza, e **reinicie a contagem** do item 1.

## 4. Registro

| Data | Ambiente | Checagem / ensaio | Resultado | Observações |
|---|---|---|---|---|
| | | | | |

## 5. O que a testnet NÃO prova

Slippage e profundidade reais, latência real, taxas do seu nível de conta, comportamento em movimentos extremos,
funding real e limites de risco da conta real. Esses só se medem com dinheiro real e posição mínima, depois de tudo
acima e de uma estratégia aprovada.
