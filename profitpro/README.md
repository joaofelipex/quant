# WIN Trend Bot — Profit Pro

Bot de tendência para o mini índice (WIN), com filtro de regime para evitar operar em lateralização. Projeto separado do QuantSage (MT5/Clear) — este mira execução via Profit Pro (Nelogica).

## Estratégia

1. **Filtro de regime** — Efficiency Ratio (Kaufman) de 20 períodos. Só opera se `ER >= 0.5` (mercado em tendência); em range/caos, fica de fora.
2. **Filtro de tendência** — EMA(9) vs EMA(21): só entra na direção do cruzamento.
3. **Gatilho de entrada** — rompimento de canal Donchian(20): compra no rompimento da máxima recente, vende no rompimento da mínima, na direção da tendência.
4. **Stop** — 1.5x ATR(14) a partir do preço de entrada.
5. **Alvo** — risco:retorno fixo de 1:2 (2x a distância do stop).
6. **Sessão** — só opera entre 09:15 e 17:45 (evita abertura e fechamento, mais ruidosos).
7. **Custos considerados** — 1 tick (5 pontos) de slippage por lado + R$1,20 de emolumentos por round-trip. Ponto do WIN = R$0,20/contrato.

Código: `strategy/trend_follow.py` (indicadores e sinais) + `backtest/engine.py` (motor de simulação).

## Por que o filtro de regime existe

A primeira versão (sem filtro de regime) tinha profit factor 1,18 no agregado, mas o resultado dependia quase todo de um único mês (abril) — nos outros 4 meses do período testado, mal cobria os custos. Adicionar o filtro ER trocou volume por qualidade: menos trades, mas **todos os 6 meses testados ficaram positivos** e o profit factor subiu para 1,58.

## Validação (treino/teste)

Dados: WIN, candles de 5 min, 15/04/2026 a 14/09/2026 (~7.600 candles).

- **Treino**: 15/04 a 31/07 — usado para calibrar `er_threshold` e testar sensibilidade dos demais parâmetros.
- **Teste (out-of-sample)**: 01/08 a 14/09 — parâmetros fixados no treino, sem reajuste.

| Métrica (1 contrato) | Treino | Teste (out-of-sample) |
|---|---|---|
| Trades | 53 | 46 |
| Win rate | — | 39,1% |
| PnL líquido | R$ 1.708,50 | R$ 1.073,43 |
| Profit factor | 1,70 | **1,45** |
| Drawdown máx | -R$ 750,87 | -R$ 533,61 |

O profit factor se manteve saudável fora da amostra (não desabou) — sinal de que o filtro de regime captura algo real, não é só ajuste ao ruído do período de treino.

### O que foi testado e descartado

Sensibilidade a outros parâmetros (Donchian 10-40, ATR stop 1.0-2.5x, R:R 1:1 a 1:4, EMA 5/13 a 20/50) foi varrida no treino e as combinações "melhores" foram validadas no teste:

- **EMA fast/slow**: nenhum efeito em nenhuma configuração testada — o Donchian + filtro de regime dominam o sinal, não a EMA.
- **Donchian(30)** parecia melhor no treino, mas foi **neutro** no teste (praticamente idêntico ao Donchian 20).
- **R:R 1:2.5** parecia melhor no treino (PF 1,79) mas **piorou no teste** (PF caiu para 1,30) — overfitting clássico.

Conclusão: parâmetros mantidos nos valores originais. Otimizações adicionais não generalizaram.

## Parâmetros finais

```python
ema_fast = 9
ema_slow = 21
atr_period = 14
donchian_period = 20
er_period = 20
er_threshold = 0.5
atr_stop_mult = 1.5
risk_reward = 2.0
session = 09:15–17:45
```

## Limitações conhecidas

- **Amostra pequena**: só ~5 meses de dados (abril-set/2026). Teste out-of-sample de ~6 semanas é curto — resultado é promissor, não é prova de edge duradouro.
- **Sem volume**: os dados exportados do ProfitChart não incluem volume; filtros de liquidez/confirmação por volume não foram testados.
- **1 contrato fixo**: sem position sizing por risco% de capital ainda.
- **Sem execução real**: backtest apenas. Não há integração com ProfitDLL — isso é a próxima fase, depois de mais validação de dados.

## Próximos passos

1. Conseguir mais histórico (ideal 1-2 anos) para revalidar com amostra maior.
2. Position sizing por risco % de capital em vez de contrato fixo.
3. Circuit breaker de perda diária.
4. Integração via ProfitDLL para paper trading (simulador) antes de qualquer conta real.

## Implementação NTSL (Profit Pro)

O Profit Pro tem editor de automação nativo (NTSL), sem necessidade de ProfitDLL. A sintaxe real desse editor (confirmada por tentativa/erro) difere do NTSL "padrão" documentado publicamente:

- Seção de parâmetros: `parâmetro` (não `Input`)
- Tipos: `Real` (não `Float`), `booleano` (não `Boolean`)
- Operador lógico E: `e` (minúsculo)
- Médias: `Media(Periodo, Serie)`, `mediaexp(Periodo, Serie)` — ordem (periodo, serie)
- MACD: `macd(Lenta, Rapida, Sinal)` — built-in
- Séries de preço: `Fechamento`, `Maxima`, `Minima`, `Abertura`
- Posição: `BuyPosition`, `SellPosition` (quantidade em posição), `BuyAtMarket`, `SellShortAtMarket`, `BuyToCoverAtMarket`, `SellToCoverAtMarket`
- **Não existe** (confirmado por erro de compilação): `Maior`, `Menor`, `Maximo`, `Minimo` (rompimento de canal / Donchian), `Hora` (fechamento por horário)
- **Bug de truncamento**: colar código com linhas longas no editor corta caracteres no fim de identificadores. Solução: manter linhas curtas (declarações e expressões quebradas em várias linhas).

Como as funções de canal (Donchian) e ATR não foram localizadas, a versão em produção no Profit **não é** a estratégia validada em Python (EMA+Donchian+ER). É uma versão simplificada:

**`strategy/WinTrendBot_v2_com_stop.ntsl`** — EMA(9/21) + MACD(12,26,9) como confirmação de tendência, stop/alvo em pontos fixos (não ATR).

Essa versão foi validada separadamente em Python (mesmo motor de backtest, replicando a lógica exata):

| Config | Treino (PF) | Teste out-of-sample (PF) |
|---|---|---|
| Stop 300 / Alvo 600 (primeira tentativa) | 0,92 (perde) | 0,87 (perde) |
| **Stop 400 / Alvo 800 (parâmetro atual)** | **1,09** | **1,33** |

**Atenção**: 23,8% dos trades (stop 400/alvo 800) levam mais de uma sessão inteira (8h) pra fechar. Sem função de horário confirmada, não há fechamento forçado por código — depende da liquidação automática de day trade da corretora (BTG) no fim do pregão.

### Pendências para fechar o gap com a versão validada em Python

1. Confirmar nome real da função de canal (máximo/mínimo do período) — necessário pra Donchian breakout.
2. Confirmar nome real da função de horário (`Hora`/`Time`/outro) — necessário pra fechamento forçado por horário, independente da corretora.
3. Confirmar se existe ATR nativo, ou implementar manualmente.
4. Portar o filtro de regime (Efficiency Ratio) — precisa de soma móvel (`Somatoria` ou equivalente) ou estrutura de loop, ainda não confirmados.

## Rodando o backtest

Nota: essa instalação Python resolve `site-packages` relativo ao diretório atual, não ao local fixo da instalação. É preciso apontar `PYTHONPATH` explicitamente:

```bash
cd quant/profitpro
PYTHONPATH="/c/Users/Infraestrutura-IMTS/Lib/site-packages" /c/Python313/python.exe backtest/run_backtest.py
PYTHONPATH="/c/Users/Infraestrutura-IMTS/Lib/site-packages" /c/Python313/python.exe backtest/monthly_report.py
```

Saídas em `reports/`: `trades.csv`, `equity_curve.png`, `monthly_pnl.png`.
