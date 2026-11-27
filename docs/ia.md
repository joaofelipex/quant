# Agente de IA (`quant.agent`)

Um modelo Claude decide aberturas e fechamentos na **Kalshi demo**. Código: [`agent.py`](../src/quant/agent.py).

## Ciclo

O timer dispara a cada minuto; o agente só age quando passou o intervalo configurado.

1. Foto do livro de todo o universo, velas dos candidatos, posições reais e resultado do dia.
2. Fechamentos obrigatórios por regra (tempo máximo).
3. O modelo recebe **apenas números** (nenhum texto da internet) e responde pela ferramenta `decide`, com motivo.
4. O código valida cada ação.
5. Execução pela mesma rota da boleta. Posição sem stop é fechada na hora.
6. Tudo é registrado em `decisions.jsonl` e na auditoria.

## Travas

Uma ação é recusada se:

- passa do número de ações por ciclo, ou o kill-switch está acionado;
- o ambiente não é a Kalshi demo;
- o ativo está fora do universo, é operado pelo robô ou está com o mercado fechado;
- é venda com `long_only` ligado;
- (fora do modo sombra) a perda do dia atingiu o limite ou não pôde ser confirmada na corretora;
- já há posição no ativo ou o limite de posições foi atingido;
- falta valor ou stop, ou o stop está fora da faixa;
- o ativo está em cooldown;
- o alvo não cobre `edge_min` vezes o custo de ida e volta.

Valor acima de `max_usd` é reduzido ao máximo. Fechar uma posição existente passa pelas checagens gerais.

## Configuração

| Chave | Padrão | Significado |
|---|---|---|
| `enabled` | falso | liga o agente |
| `shadow` | falso | decide e registra, sem enviar aberturas |
| `aggressive` | falso | postura "operar tudo": abre em todo candidato com direção clara |
| `model` | claude-sonnet-5-5 | modelo (Sonnet, Haiku ou Opus) |
| `interval_min` | 10 | minutos entre ciclos |
| `universe` | `tudo` | ativos observados |
| `candidates` | 12 | ativos com análise detalhada |
| `max_usd` | 15 | valor máximo por entrada |
| `max_positions` | 5 | posições simultâneas |
| `max_actions` | 3 | ações por ciclo |
| `max_daily_loss` | 2 | USD |
| `long_only` | verdadeiro | só comprado |
| `stop_min`, `stop_max` | 0,5 e 5 | faixa do stop, em % |
| `cooldown_min` | 20 | espera para reabrir |
| `max_hold_h` | 24 | tempo máximo da posição |
| `edge_min` | 2 | múltiplo do custo exigido do alvo |

Operadores ligam e desligam; limites, modelo e universo são do administrador. Os valores em uso aparecem na aba IA do
painel.

## Modo sombra

As aberturas viram posições simuladas, com stop conferido só a cada ciclo, ao preço justo. Não arrisca saldo, mas
**continua chamando o modelo**, e o resultado simulado é otimista em relação à execução real.

## O que se mediu

Estudo [`ia_intradia`](../estudos/ia_intradia/README.md), 268 operações reais na demo (24 a 27/11/2026):

- acerto de 18% e −44,7 bps líquidos por operação (−18,2 antes da taxa);
- com a mesma saída fixa, as entradas ficaram **iguais a horas sorteadas** no mesmo ativo e lado;
- ordem limite reduz a taxa, mas a seleção adversa consome a economia.

Conclusão: não há evidência de que as entradas da IA tenham informação.

## Custo

Uma chamada ao modelo por ciclo. A aba IA mostra o consumo de tokens. A chave fica em `/etc/quant/agent.env`,
gravada por `deploy/definir-chave-ia.sh`.
