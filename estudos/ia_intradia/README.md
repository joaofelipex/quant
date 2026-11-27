# A IA e regras intradia nos perpétuos da Kalshi

**Veredito: sem vantagem. As entradas da IA valem o mesmo que horas sorteadas; a única regra que passou na demo
reprovou em preços de produção; ordem limite corta a taxa, mas não salva a operação.**

Dados: 268 operações fechadas da IA na conta demo (24 a 27/11/2026, pelos registros da corretora) e velas públicas
de 1 min (bid/ask) de 145 perpétuos da demo, de 17/11 a 27/11/2026. Para produção, velas públicas de 1 h da Kalshi
real (sem chave), de 06/2026 a 27/11/2026.

## 1. Onde a IA perde ([`entradas_ia.py`](entradas_ia.py))

| Recorte | Operações | Acerto | Antes da taxa | Taxa | Líquido (bps) |
|---|---|---|---|---|---|
| Todas | 268 | 18% | −18,2 | 26,5 | −44,7 |
| Ações | 175 | 18% | −15,4 | 29,0 | −44,4 |
| Metais | 31 | 23% | +15,0 | 12,1 | +2,9 |
| Vendas | 73 | 16% | −38,6 | 23,3 | −62,0 |
| Fechadas em < 15 min | 64 | 2% | −72,8 | 33,3 | −106,1 |
| Seguradas > 2 h | 50 | 42% | +26,8 | 26,3 | +0,4 |

A entrada já perde antes da taxa. As operações longas parecem melhores porque as perdedoras são fechadas cedo. Com
saída fixa (stop 2%), as mesmas 270 entradas ficam iguais ao mesmo ativo e lado em hora sorteada:

| Segurando | Entradas da IA | Hora sorteada | t da diferença |
|---|---|---|---|
| 15 min | −25,4 | −25,1 | 1,2 |
| 1 h | −27,3 | −25,8 | −0,2 |
| 4 h | −37,5 | −26,9 | 0,7 |
| 8 h | −81,1 | −34,6 | 0,7 |

Mudar stop, alvo ou prazo não resolve: o momento escolhido não tem informação.

## 2. Regras simples ([`regras.py`](regras.py))

Seguir (z > 1,5) ou ir contra (z > 2) o movimento de 15 min, 1 h, 4 h ou 1 dia, segurando 1 h, 4 h ou 1 dia, em
todas as classes, com spread real e taxa: 68 combinações com amostra. Cinco ficaram positivas no treino e na prova;
duas com t > 2:

- **Contra o movimento de 1 h no H100** (+203 bps, t 4,3): um único contrato que não existe em produção, quase todo
  o ganho nas vendas. Tratado como artefato da cotação da demo.
- **Contra o movimento de 4 h em ações** (+43 bps em 370 operações, 61% de acerto, t 2,3): sobreviveu a entrada
  atrasada em 3 min (em 10 min, t 1,7), sem os 3 melhores ativos, nos dois lados e nos 8 dias com operações.

## 3. A regra de ações em produção ([`producao.py`](producao.py))

Mesma regra em velas de 1 h (entrada no fechamento da hora seguinte), compra no ask e venda no bid:

| Dados | Classe | Operações | Líquido médio (bps) | Acerto |
|---|---|---|---|---|
| Produção | Ações | 323 | −28,9 | 40% |
| Produção | Cripto | 1.860 | −9,3 | 45% |
| Demo, 1 h | Ações | 506 | −22,8 | 43% |

Reprovada. O resultado de 1 min na demo foi sorte do período ou da cotação da demo.

## 4. Ordem limite ([`medir_maker.py`](medir_maker.py), [`ordem_limite.py`](ordem_limite.py))

`GET /margin/fee_tiers` na demo: ações e cripto pagam **12 bps** por lado a mercado e **2 bps** com ordem que fica no
livro; metais e índices 0,72 / 0,12; câmbio 1,8 / 0,3. Cinco compras limite de 1 contrato com `post_only` (que recusa
a ordem se ela cruzaria o livro) pagaram 2,0 a 2,2 bps; o teste custou cerca de US$ 0,33 na demo.

Simulação com instantes e lados sorteados, saída a mercado: a limite só executa quando o preço vem contra (seleção
adversa), e a economia de 10 bps vira de −1 a +6 bps.

| Classe (segura 1 h) | Executou | A mercado | Limite na entrada |
|---|---|---|---|
| Ações | 51% | −29,8 | −23,5 |
| Cripto | 43% | −34,5 | −35,7 |
| Câmbio | 58% | −7,8 | −5,3 |

Vale usar ordem limite quando houver um sinal que funcione; sozinha não cria vantagem.

## Limites

Dez dias de velas de 1 min e três dias de operações da IA. Muitas combinações testadas: o t de uma regra isolada é
otimista. A saída com ordem limite não foi simulada.

## Reproduzir

Copie da VM `/var/lib/quant/agent/decisions.jsonl` e `/var/lib/quant/metrics/fills.jsonl` para `dados/raw/vm_27nov/`.

```
cd estudos/ia_intradia
python -c "import comum; comum.baixar()"   # velas de 1 min da demo
python entradas_ia.py
python regras.py
python producao.py                          # baixa as velas de 1 h de produção e da demo
python ordem_limite.py
```

`medir_maker.py` envia ordens reais na conta **demo** e roda na VM, com a chave dela (como os diagnósticos do
`deploy/README.md`); fecha tudo o que abrir.
