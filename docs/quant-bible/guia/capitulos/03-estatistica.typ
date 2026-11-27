#import "../template.typ": *

= Fundamentos de estatística

Em probabilidade, o modelo é conhecido e perguntamos sobre os dados. Em estatística, os dados são conhecidos e perguntamos sobre o modelo.

== Lei dos grandes números e teorema central do limite

Sejam $X_1, dots, X_n$ independentes e de mesma distribuição, com média $mu$ e variância $sigma^2$ finitas, e $overline(X)_n$ a média amostral.

#definicao[
  *Lei dos grandes números:* $overline(X)_n -> mu$ quando $n -> infinity$.

  *Teorema central do limite:*
  $ sqrt(n) (overline(X)_n - mu)/sigma -> cal(N)(0, 1) quad "em distribuição". $
]

Na prática, $overline(X)_n$ é aproximadamente normal com média $mu$ e *erro-padrão* $sigma\/sqrt(n)$. Para reduzir o erro pela metade, é preciso quadruplicar a amostra.

O teorema falha ou demora quando as observações são dependentes (retornos de ativos correlacionados, janelas sobrepostas) ou quando as caudas são pesadas. Com dependência positiva, o número *efetivo* de observações é bem menor que $n$.

#problema("a moeda é justa?")[
  Em 1000 lançamentos saíram 550 caras. Há evidência de viés?
]
#solucao[
  Sob a hipótese justa, o número de caras tem média 500 e desvio $sqrt(250) approx 15.8$. A distância é $z = 50\/15.8 approx 3.16$, com valor-p bilateral perto de $0.0016$. Há forte evidência de viés, embora o viés estimado, de 5 pontos percentuais, tenha margem de cerca de 3.
]

#problema("quanto tempo para provar um Sharpe")[
  Uma estratégia tem índice de Sharpe anual 1. Quantos anos de dados para uma estatística $t$ de 2?
]
#solucao[
  Para retornos independentes, $t approx "Sharpe anual" times sqrt("anos")$. Logo são necessários 4 anos. Com Sharpe 0,5, são 16 anos.
]

== Estimadores

Um estimador $hat(theta)$ é uma função dos dados. Medimos sua qualidade pelo viés e pelo erro quadrático médio (EQM):

$ "viés" = EE[hat(theta)] - theta, quad "EQM" = EE[(hat(theta) - theta)^2] = "viés"^2 + Var(hat(theta)). $

Um estimador é *consistente* se converge para $theta$. Um pouco de viés pode valer a pena quando reduz muito a variância (é a ideia da regularização, no capítulo 4).

#definicao[
  O estimador de *máxima verossimilhança* escolhe o parâmetro que torna os dados observados mais prováveis:
  $ hat(theta) = argmax_theta sum_(i=1)^n log f(x_i; theta). $
]

- Bernoulli: $hat(p) = overline(x)$.
- Exponencial: $hat(lambda) = 1\/overline(x)$.
- Normal: $hat(mu) = overline(x)$ e $hat(sigma)^2 = 1/n sum_i (x_i - overline(x))^2$, que é viesado; dividir por $n-1$ corrige.
- Uniforme em $(0, theta)$: $hat(theta) = max_i x_i$, que subestima; $(n+1)/n max_i x_i$ não tem viés.

O *método dos momentos* iguala momentos amostrais aos teóricos. É mais simples e costuma ser menos eficiente.

== Intervalos de confiança

#definicao[
  Um intervalo de confiança de nível $1 - alpha$ é uma regra $I$, calculada dos dados, tal que $P_theta (theta in I) >= 1 - alpha$ para todo $theta$.
]

Para a média, com amostra grande e desvio estimado $s$:
$ overline(x) plus.minus z s/sqrt(n), quad z = 1.645 " (90%)", 1.96 " (95%)", 2.576 " (99%)". $

Com amostra pequena de dados normais, troque $z$ pelo quantil da distribuição $t$ com $n-1$ graus de liberdade.

#intuicao[
  O parâmetro é fixo; o intervalo é que é aleatório. "95%" quer dizer que o procedimento acerta em 95% das amostras, e não que _este_ intervalo tenha 95% de chance de conter $theta$. Essa segunda frase descreve um intervalo bayesiano de credibilidade.
]

#problema("tamanho da pesquisa")[
  Quantas respostas para estimar uma proporção com margem de 1 ponto percentual a 95%?
]
#solucao[
  O pior caso é $p = 0.5$: $1.96 sqrt(0.25\/n) <= 0.01$, logo $n >= 9604$.
]

Quando não há fórmula simples (mediana, Sharpe, quantis), use o *bootstrap*: reamostre os dados com reposição muitas vezes, recalcule a estatística e use os quantis. Em séries temporais, reamostre *blocos* para preservar a dependência.

== Testes de hipótese

Escolhem-se uma hipótese nula $H_0$, uma estatística e um nível $alpha$.

- *Valor-p:* probabilidade, sob $H_0$, de um resultado ao menos tão extremo quanto o observado. Não é a probabilidade de $H_0$ ser verdadeira.
- *Erro tipo I:* rejeitar $H_0$ verdadeira (probabilidade $alpha$).
- *Erro tipo II:* não rejeitar $H_0$ falsa (probabilidade $beta$). O *poder* é $1 - beta$ e cresce com a amostra e com o tamanho do efeito.

=== Múltiplos testes

Quem testa muitas ideias encontra "resultados" por acaso. Com 20 testes independentes a 5% e nenhuma ideia verdadeira:
$ P("ao menos um falso positivo") = 1 - 0.95^20 approx 64%. $

- *Bonferroni:* use $alpha\/m$ em cada um dos $m$ testes. Simples e conservador.
- *Benjamini–Hochberg:* controla a fração esperada de descobertas falsas, com mais poder.
- *Sharpe deflacionado:* compara o Sharpe escolhido com o maior que o acaso produziria no mesmo número de tentativas.

#problema("o melhor entre muitos")[
  Você testou 64 estratégias sem vantagem alguma. Cada estatística $t$ é aproximadamente $cal(N)(0, 1)$ e independente das outras. O que esperar da maior?
]
#solucao[
  O máximo de 64 normais padrão tem média perto de $2.3$. Um $t$ de 2,2 na melhor estratégia é _o que se espera do puro acaso_.
]
