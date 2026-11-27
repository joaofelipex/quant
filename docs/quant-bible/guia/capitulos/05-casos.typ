#import "../template.typ": *

= Estudos de caso de pesquisa

Um estudo de caso é aberto de propósito. O que se avalia é a ordem das perguntas e o cuidado com o que pode dar errado.

== Um roteiro

+ *Objetivo:* o que será previsto, para quê e com qual métrica de erro.
+ *Dados:* o que existe, em que momento fica disponível, o que falta e o que está enviesado.
+ *Exploração:* distribuições, valores extremos, relações óbvias.
+ *Referência simples:* a regra mais boba que alguém usaria. Todo modelo precisa vencê-la.
+ *Modelo:* comece interpretável e só complique com ganho medido.
+ *Validação:* uma divisão que imite o uso real.
+ *Comunicação:* resultado, incerteza, limites e próximo passo.

== Caso 1: preço de apartamentos

_Você recebe vendas de apartamentos de uma cidade nos últimos cinco anos (preço, área, quartos, vagas, andar, idade, bairro, data) e precisa estimar o valor de imóveis à venda hoje._

*Perguntas antes de modelar.* O erro que importa é em reais ou em porcentagem? O preço registrado é o negociado ou o anunciado? Há vendas entre parentes ou erros de digitação?

*Escolhas de modelagem.*
- Prever $log("preço")$: o erro fica proporcional e os efeitos viram porcentagens.
- Área em log, pois dobrar a área não costuma dobrar o preço.
- Área, quartos e vagas são colineares; os coeficientes individuais ficam instáveis. Se o objetivo é prever, ridge resolve; se é explicar, combine variáveis (por exemplo, área por quarto).
- Bairro tem muitas categorias e algumas com poucas vendas. Encolha a média de cada bairro em direção à média da cidade, com peso $n_b\/(n_b + k)$.
- Distância a transporte, comércio e parques pode explicar o que o bairro esconde.
- O mercado muda no tempo: inclua um índice por trimestre.

*Referência:* mediana do preço por metro quadrado do bairro nos últimos 12 meses.

*Validação:* treinar no passado e testar no período seguinte. Uma divisão aleatória deixa o modelo ver vendas futuras do mesmo prédio. Reporte o erro percentual mediano e a fração das previsões dentro de 10%, separados por bairro e faixa de preço.

#intuicao[
  Imóveis que venderam não são uma amostra aleatória dos imóveis. Os que ficaram anos anunciados sem comprador não aparecem na base, e o modelo tende a superestimar imóveis parecidos com eles.
]

== Caso 2: demanda de energia por hora

_Preveja o consumo elétrico de uma região para cada hora do dia seguinte. Há cinco anos de consumo horário, temperatura e calendário._

*O que o consumo mostra:* ciclo diário, ciclo semanal, feriados, efeito de temperatura em forma de U (frio e calor aumentam o consumo) e tendência de longo prazo.

*Variáveis.*
- Hora e dia do ano são cíclicos: use pares $sin(2 pi h\/24)$ e $cos(2 pi h\/24)$, ou um modelo por hora.
- Temperatura com dois termos, $max(0, T - 22)$ e $max(0, 18 - T)$, ou _splines_.
- Consumo defasado: mesma hora de ontem (se já disponível) e da semana anterior.
- Indicadoras de feriado, véspera e emendas.

*A armadilha principal:* no momento da previsão não se conhece a temperatura de amanhã, só a *previsão* dela. Treinar com a temperatura realizada produz um erro de teste otimista.

*Referências:* repetir a mesma hora de uma semana atrás.

*Modelos:* regressão regularizada com as variáveis acima; depois, árvores com _boosting_ para capturar interações. Árvores não extrapolam tendência, então modele a diferença em relação à referência.

*Validação:* _walk-forward_ cobrindo todas as estações. Olhe o erro por hora e os piores dias, porque o custo de errar no pico é maior. Se o erro de subestimar custa mais que o de superestimar, preveja um quantil em vez da média, com a perda _pinball_.

== Caso 3: um backtest bom demais

_Um colega mostra uma estratégia em criptomoedas com índice de Sharpe 2,5 em dois anos e pede para colocá-la em produção._

*Custos.* Suponha retorno bruto médio de 25 pontos-base por operação. Com taxa de 12 pontos-base na entrada e na saída mais 10 de _spread_, o custo é 34: a estratégia perde 9 por operação. Pergunte qual custo foi usado e se ele foi medido.

*Tentativas.* Quantas variantes foram testadas antes desta? Com 64 variantes e dois anos, o maior Sharpe anual esperado por puro acaso é da ordem de $2.3\/sqrt(2) approx 1.6$.

*Dependência.* Mil operações em 19 moedas muito correlacionadas não são mil observações independentes. Calcule o erro sobre o retorno diário da carteira, ou use bootstrap em blocos.

*Vazamento.* O sinal usa o fechamento da barra em que a ordem é executada? O universo foi escolhido com moedas que sobreviveram até hoje?

*Execução.* A ordem limite é preenchida de preferência quando o preço vem contra (seleção adversa). Há taxa de financiamento nos contratos perpétuos? O tamanho cabe no livro de ofertas?

*Robustez.* O resultado se mantém em cada ano, com parâmetros vizinhos e sem os três melhores ativos?

*Resposta.* Não colocar em produção ainda: congelar as regras, medir em dados novos com ordens simuladas ou de tamanho mínimo e definir antes o que faria a estratégia ser descartada.
