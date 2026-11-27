#import "../template.typ": *

= Fundamentos de probabilidade

== Probabilidade condicional e teorema de Bayes

#definicao[
  A probabilidade de $A$ dado que $B$ ocorreu mede quanto de $B$ é "ocupado" por $A$:
  $ P(A|B) = P(A inter B)/P(B), quad P(B) > 0. $
]

Como $P(A inter B)$ pode ser escrito dos dois lados, $P(A|B) P(B) = P(B|A) P(A)$, o que dá o teorema de Bayes:

$ P(A|B) = (P(B|A) P(A))/P(B). $

Os quatro termos têm nomes que aparecem em entrevistas e em papers:
- $P(A)$: *prior*, a crença antes de ver a evidência;
- $P(B|A)$: *likelihood*, quão provável é a evidência se $A$ for verdadeiro;
- $P(B)$: *evidence*, calculada pela lei da probabilidade total, $P(B) = P(B|A)P(A) + P(B|not A)P(not A)$;
- $P(A|B)$: *posterior*, a crença atualizada.

#intuicao[
  O erro clássico é ignorar o prior. Uma evidência "forte" sobre um evento raro ainda deixa o evento improvável, porque os falsos positivos dos eventos comuns são muitos.
]

#problema("alarme de fraude")[
  Um banco tem 0,5% das transações fraudulentas. Seu detector sinaliza 90% das fraudes, mas também 4% das transações legítimas. Dada uma transação sinalizada, qual a chance de ser fraude?
]
#solucao[
  Com $F$ = fraude e $S$ = sinalizada:
  $ P(F|S) = (0.9 dot 0.005)/(0.9 dot 0.005 + 0.04 dot 0.995) = 0.0045/0.0443 approx 10.2%. $
  Mais de 89% dos alertas são falsos, apesar de o detector parecer bom. Em *market making* a mesma lógica vale para decidir se um fluxo de ordens é informado ou não.
]

#problema("atualização sequencial")[
  Duas moedas na mesa: uma justa e uma que dá cara com probabilidade $3/4$. Você escolhe uma ao acaso e vê 3 caras seguidas. Qual a probabilidade de ser a viciada?
]
#solucao[
  $ P("viciada"|3"C") = ((3/4)^3 dot 1/2)/((3/4)^3 dot 1/2 + (1/2)^3 dot 1/2) = 27/(27 + 8) approx 77.1%. $
  Cada nova observação multiplica a razão de chances (*odds*) por $(3/4)/(1/2) = 1.5$, e é por isso que o cálculo em forma de *odds* é mais rápido em entrevista.
]

== Esperança e variância

#definicao[
  Para uma variável aleatória $X$ discreta (com massa $p$) ou contínua (com densidade $f$):
  $ EE[X] = sum_x x p(x) quad "ou" quad EE[X] = integral_(-infinity)^infinity x f(x) dif x. $
  A variância mede a dispersão em torno da média $mu = EE[X]$:
  $ Var(X) = EE[(X - mu)^2] = EE[X^2] - mu^2. $
]

Ferramentas que resolvem a maior parte das questões:

- *Linearidade:* $EE[a X + b Y] = a EE[X] + b EE[Y]$, *mesmo com dependência*.
- *Função de variável:* $EE[g(X)] = sum_x g(x) p(x)$, sem precisar da distribuição de $g(X)$.
- *Escala:* $Var(a X + b) = a^2 Var(X)$.
- *Esperança total:* $EE[X] = EE[EE[X | Y]]$.
- *Variância total:* $Var(X) = EE[Var(X | Y)] + Var(EE[X | Y])$.

#intuicao[
  Para contar "quantos eventos acontecem", escreva a contagem como soma de indicadoras, $N = sum_i I_i$. Então $EE[N] = sum_i P(I_i = 1)$, sem se preocupar com dependência.
]

#problema("dado com segunda chance")[
  Você rola um dado e recebe o valor em reais. Pode descartar o resultado e rolar de novo uma vez. Quanto vale o jogo? E com duas novas chances?
]
#solucao[
  Resolva de trás para a frente. A última rolagem vale $3.5$, então na penúltima só se mantém 4, 5 ou 6:
  $ V_2 = (4 + 5 + 6)/6 + 3/6 dot 3.5 = 4.25. $
  Com duas novas chances, a primeira rolagem só é mantida se superar $4.25$ (5 ou 6):
  $ V_3 = (5 + 6)/6 + 4/6 dot 4.25 approx 4.67. $
]

#problema("todas as faces")[
  Quantas rolagens, em média, até ver as seis faces de um dado?
]
#solucao[
  Já tendo visto $k$ faces, a próxima rolagem traz uma face nova com probabilidade $(6 - k)\/6$; a espera é geométrica, com média $6\/(6 - k)$. Somando:
  $ EE[T] = 6 (1 + 1/2 + 1/3 + 1/4 + 1/5 + 1/6) = 14.7. $
]

#problema("duas caras seguidas")[
  Com uma moeda justa, quantos lançamentos em média até sair cara-cara? E cara-coroa?
]
#solucao[
  Condicione no primeiro passo. Seja $a$ a espera partindo do zero e $b$ a espera logo depois de uma cara:
  $ a = 1 + 1/2 b + 1/2 a, quad b = 1 + 1/2 dot 0 + 1/2 a. $
  Daí $a = 6$. Para cara-coroa, depois da primeira cara um erro (outra cara) não apaga o progresso: são duas esperas de média 2, total $4$.
]

#problema("resultado do dia")[
  O número de operações em um dia é Poisson com média 100. Cada operação ganha em média R\$ 0,50, com desvio-padrão de R\$ 4, independente das demais. Qual a média e o desvio do resultado diário?
]
#solucao[
  Condicionando no número $N$ de operações, $EE[S] = 100 dot 0.5 = 50$ e
  $ Var(S) = EE[N] sigma^2 + Var(N) mu^2 = 100 dot 16 + 100 dot 0.25 = 1625. $
  O desvio é cerca de R\$ 40: um dia negativo é comum mesmo com vantagem positiva.
]

== Variáveis aleatórias

A função de distribuição acumulada é $F(a) = P(X <= a)$; no caso contínuo, $f = F'$.

#table(
  columns: (auto, 1.6fr, auto, auto),
  align: horizon,
  [Distribuição], [Massa ou densidade], [Média], [Variância],
  [Bernoulli($p$)], [$P(X=1) = p$, $P(X=0) = 1-p$], [$p$], [$p(1-p)$],
  [Binomial($n, p$)], [$binom(n, k) p^k (1-p)^(n-k)$], [$n p$], [$n p(1-p)$],
  [Geométrica($p$)], [$(1-p)^(k-1) p$, $k = 1, 2, dots$], [$1\/p$], [$(1-p)\/p^2$],
  [Poisson($lambda$)], [$e^(-lambda) lambda^k\/k!$], [$lambda$], [$lambda$],
  [Uniforme($a, b$)], [$1\/(b-a)$ em $[a, b]$], [$(a+b)\/2$], [$(b-a)^2\/12$],
  [Exponencial($lambda$)], [$lambda e^(-lambda x)$, $x >= 0$], [$1\/lambda$], [$1\/lambda^2$],
  [Normal($mu, sigma^2$)], [$1\/(sigma sqrt(2 pi)) e^(-(x-mu)^2\/(2 sigma^2))$], [$mu$], [$sigma^2$],
)

Relações úteis:

- *Sem memória:* na geométrica e na exponencial, $P(X > s + t | X > s) = P(X > t)$.
- *Mínimo de exponenciais* independentes de taxas $lambda_i$: é exponencial de taxa $sum_i lambda_i$, e o índice $i$ chega primeiro com probabilidade $lambda_i\/sum_j lambda_j$.
- *Eventos raros:* Binomial($n, p$) com $n$ grande e $n p = lambda$ moderado se aproxima de Poisson($lambda$).
- *Somas:* normais independentes somam em normal; Poissons independentes somam em Poisson.
- *Regra 68–95–99,7:* massa de uma normal a 1, 2 e 3 desvios da média.

#problema("dois ônibus")[
  Os ônibus A e B chegam como processos de Poisson independentes, com espera média de 10 e 15 minutos. Quanto se espera pelo primeiro e qual a chance de ser o A?
]
#solucao[
  As taxas somam $1\/10 + 1\/15 = 1\/6$ por minuto: espera média de 6 minutos. O A vem primeiro com probabilidade $(1\/10)\/(1\/6) = 0.6$.
]

#problema("o maior de n sorteios")[
  Sorteie $n$ números uniformes em $[0, 1]$. Qual o valor esperado do maior?
]
#solucao[
  $P(M <= x) = x^n$, logo a densidade é $n x^(n-1)$ e
  $ EE[M] = integral_0^1 x dot n x^(n-1) dif x = n/(n+1). $
  Pela simetria, $n$ pontos dividem o intervalo em $n+1$ pedaços de mesma média.
]

== Funções de variáveis e distribuições conjuntas

Se $Y = g(X)$ com $g$ estritamente monótona e derivável:
$ f_Y (y) = f_X (g^(-1)(y)) abs(dif/(dif y) g^(-1)(y)). $
Se $g$ não é monótona, some as contribuições de todas as raízes, ou derive a acumulada $P(g(X) <= y)$.

Para um par $(X, Y)$ com densidade conjunta $f(x, y)$:

- marginal: $f_X (x) = integral f(x, y) dif y$;
- condicional: $f_(Y|X) (y | x) = f(x, y)\/f_X (x)$;
- independência: $f(x, y) = f_X (x) f_Y (y)$ para todo par;
- soma de independentes (convolução): $f_(X+Y) (z) = integral f_X (x) f_Y (z - x) dif x$.

#intuicao[
  Com duas variáveis uniformes, desenhe o quadrado e meça a área do evento. Quase sempre é mais rápido que integrar.
]

#problema("quadrado de uma uniforme")[
  Se $X$ é uniforme em $(0, 1)$, qual a densidade de $Y = X^2$?
]
#solucao[
  $P(Y <= y) = P(X <= sqrt(y)) = sqrt(y)$, logo $f_Y (y) = 1\/(2 sqrt(y))$ em $(0, 1)$: a massa se acumula perto de zero.
]

#problema("encontro marcado")[
  Duas pessoas chegam em instantes uniformes e independentes dentro de uma hora. Cada uma espera 15 minutos. Qual a chance de se encontrarem?
]
#solucao[
  No quadrado $[0, 1]^2$, elas se encontram se $abs(X - Y) <= 1\/4$. A área fora da faixa são dois triângulos de lado $3\/4$:
  $ P = 1 - (3/4)^2 = 7/16. $
]

#problema("vareta em três pedaços")[
  Quebre uma vareta em dois pontos uniformes e independentes. Qual a chance de os três pedaços formarem um triângulo?
]
#solucao[
  Formam triângulo se nenhum pedaço passa de metade da vareta. No quadrado dos dois cortes, a região favorável são dois triângulos de área $1\/8$ cada: $P = 1\/4$.
]

== Covariância e correlação

#definicao[
  $ Cov(X, Y) = EE[X Y] - EE[X] EE[Y], quad rho = Cov(X, Y)/(sigma_X sigma_Y) in [-1, 1]. $
]

- $Var(sum_i a_i X_i) = sum_i sum_j a_i a_j Cov(X_i, X_j) = a^top Sigma a$.
- Independência implica covariância zero; *a volta é falsa*. Com $X$ uniforme em $(-1, 1)$ e $Y = X^2$, a covariância é zero e $Y$ é função de $X$.
- Correlação mede associação *linear* e é sensível a valores extremos. A de Spearman, calculada sobre os postos, mede associação monótona.
- Uma matriz de covariância precisa ser semidefinida positiva: nem toda combinação de correlações é possível.

#problema("carteira de variância mínima")[
  Dois ativos têm volatilidades de 20% e 30% e correlação 0,2. Qual o peso do primeiro na carteira de menor variância?
]
#solucao[
  Minimizando $w^2 sigma_1^2 + (1-w)^2 sigma_2^2 + 2 w (1-w) rho sigma_1 sigma_2$:
  $ w^* = (sigma_2^2 - rho sigma_1 sigma_2)/(sigma_1^2 + sigma_2^2 - 2 rho sigma_1 sigma_2) = (0.09 - 0.012)/(0.04 + 0.09 - 0.024) approx 0.736. $
  A volatilidade resultante é cerca de 18,1%, abaixo da de qualquer um dos dois.
]

#problema("diversificação com ativos correlacionados")[
  São 19 ativos de mesma volatilidade, com correlação 0,7 entre cada par. A quantos ativos independentes equivale uma carteira de pesos iguais?
]
#solucao[
  $ Var(overline(X)) = sigma^2/n (1 + (n-1) rho). $
  O número efetivo é $n\/(1 + (n-1) rho) = 19\/13.6 approx 1.4$. Somar mais ativos quase não reduz o risco, cuja variância tende a $rho sigma^2$.
]

#problema("três variáveis")[
  Três variáveis têm a mesma correlação $rho$ entre cada par. Qual o menor $rho$ possível?
]
#solucao[
  Com variâncias 1, $Var(X_1 + X_2 + X_3) = 3 + 6 rho >= 0$, logo $rho >= -1\/2$. Para $n$ variáveis, $rho >= -1\/(n-1)$.
]
