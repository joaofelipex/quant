# Regras de entrada contra a "hora qualquer" (19 cripto, 1 h)

**Veredito: reprovadas.** Nenhuma regra passou. Nada daqui deve ir para a conta que envia ordens.

## Por que

A IA comprava depois de alta recente e, em 94 entradas reais (25 e 26/11/2026), ficou atras de entradas em horario
aleatorio nos mesmos ativos. Antes de trocar uma regra por outra, a pergunta: alguma regra simples supera comprar em
hora qualquer, depois dos custos, em historico longo?

## Metodo

- Velas de 1 h da Binance, 19 cripto, 25/12/2024 a 25/11/2026 (os 30 dias anteriores servem de aquecimento).
- Treino ate 10/12/2025, teste depois. So comprado, sem stop, prazos fixos de 4, 24, 72 e 168 h.
- Sinal no fechamento, entrada na abertura seguinte, sem posicoes sobrepostas na mesma moeda.
- `excesso` = retorno do trade menos a media de todas as barras da moeda no mesmo periodo e prazo.
- `t` calculado sobre medias semanais do excesso (moedas andam juntas).
- Custo de 30 bps por ida e volta; repetido com 4 bps.
- Filtro "taxas": taxas de 30 dias do DefiLlama acima dos 30 anteriores, com 2 dias de atraso.

## Resultado (custo de 30 bps)

32 combinacoes. Tres ficaram positivas e acima da hora qualquer nos dois periodos, todas no prazo de 72 h, nenhuma
com `t` perto de 3 no teste (em bps por trade):

| Regra | Liquido treino | Excesso treino | t treino | Liquido teste | Excesso teste | t teste |
|---|---|---|---|---|---|---|
| queda forte em 4 h | 27,0 | 58,0 | 1,4 | 26,9 | 87,4 | 1,5 |
| queda forte em 4 h + taxas | 41,6 | 63,8 | 0,2 | 39,5 | 100,3 | 1,7 |
| queda em 4 h com 30 d em alta | 8,5 | 30,9 | -1,1 | 36,9 | 90,7 | -0,5 |

- A regra parecida com a da IA (`momento_curto`) teve liquido negativo nos quatro prazos, no treino e no teste.
- `t` negativo com excesso positivo significa que a media por trade e puxada por poucas semanas cheias de sinais.
- Com custo de 4 bps, 7 combinacoes ficam positivas nos dois periodos; nenhuma com `t` >= 3.

## Limites

- Precos da Binance, nao da Kalshi demo. Sem funding e sem stop. Prazos menores que 4 h nao foram testados.
- A comparacao de 94 entradas da IA usou velas de 1 min e outro metodo; os dois resultados nao sao a mesma medida.
- As moedas sao as listadas hoje (vies de sobrevivencia). O historico de taxas pode ter sido revisado depois.
- Um unico corte treino/teste, e o teste ja foi olhado: ajustar regras em cima dele o invalida.

## Reproduzir

```
python scripts/baixar_defillama.py --pular tvl_protocolo
python estudos/regras_historico/testar.py            # --custo 4 para o custo baixo
```

Os precos ficam em `dados/raw/binance/h1_19/<MOEDA>USDT_1h.csv` (colunas datetime, open, high, low, close), baixados
das velas publicas da Binance; a pasta nao vai para o git.
