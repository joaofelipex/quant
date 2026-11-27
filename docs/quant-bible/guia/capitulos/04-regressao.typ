#import "../template.typ": *

= Regressão e ciência de dados

A referência clássica para este capítulo é _The Elements of Statistical Learning_, de Hastie, Tibshirani e Friedman.

== Mínimos quadrados e vizinhos mais próximos

=== Mínimos quadrados

O modelo linear é $y = X beta + epsilon$, com $X$ de dimensão $n times p$. Minimizar $norm(y - X beta)^2$ leva às equações normais $X^top X beta = X^top y$. Se as colunas de $X$ são linearmente independentes:

$ hat(beta) = (X^top X)^(-1) X^top y, quad hat(y) = H y, quad H = X (X^top X)^(-1) X^top. $

$H$ projeta $y$ no espaço das colunas de $X$: é simétrica, $H^2 = H$, e seu traço é $p$. Os resíduos $y - hat(y)$ são ortogonais a todas as colunas de $X$; com intercepto, somam zero.

=== Vizinhos mais próximos

O método dos $k$ vizinhos prevê $y$ em um ponto pela média dos $k$ exemplos de treino mais próximos:
$ hat(f)(x) = 1/k sum_(x_i in N_k (x)) y_i. $
Não supõe forma funcional. Com $k = 1$ o erro de treino é zero, o que não diz nada sobre o erro fora da amostra. Os _métodos de núcleo_ trocam o peso igual por um peso que cai suavemente com a distância.

#table(
  columns: (auto, 1fr, 1fr),
  [], [Modelo linear], [$k$ vizinhos],
  [Hipótese], [Relação aproximadamente linear], [Apenas suavidade local],
  [Viés], [Alto se a hipótese falha], [Baixo com $k$ pequeno],
  [Variância], [Baixa], [Alta com $k$ pequeno],
  [Muitas variáveis], [Funciona, com regularização], [Sofre muito],
  [Interpretação], [Coeficientes], [Pouca],
)

=== Viés e variância

Para $y = f(x) + epsilon$ com $Var(epsilon) = sigma^2$, o erro esperado em um ponto é
$ EE[(y - hat(f)(x))^2] = sigma^2 + (EE[hat(f)(x)] - f(x))^2 + Var(hat(f)(x)), $
isto é, ruído irredutível, viés ao quadrado e variância. Modelos mais flexíveis reduzem o viés e aumentam a variância; no kNN, a variância é cerca de $sigma^2\/k$.

=== A maldição da dimensionalidade

Em um cubo unitário de $d$ dimensões com pontos uniformes, um subcubo com a fração $r$ dos dados precisa de lado $r^(1\/d)$. Com $d = 10$, para capturar 10% dos pontos o lado é $0.1^(0.1) approx 0.79$: a "vizinhança" cobre quase todo o intervalo de cada variável e deixa de ser local.

== Inferência na regressão

Hipóteses clássicas: modelo linear correto; $EE[epsilon | X] = 0$; erros de variância constante e não correlacionados; colunas sem colinearidade perfeita. Sob elas, o teorema de Gauss–Markov diz que mínimos quadrados tem a menor variância entre os estimadores lineares não viesados. A normalidade só é necessária para os testes exatos em amostra pequena.

$ Var(hat(beta)) = sigma^2 (X^top X)^(-1), quad hat(sigma)^2 = "SQR"/(n - p), quad t_j = hat(beta)_j/"EP"(hat(beta)_j), $

onde SQR é a soma dos quadrados dos resíduos. Para testar um *grupo* de coeficientes, compare o modelo restrito (0, com $p_0$ parâmetros) ao completo (1, com $p_1$):
$ F = (("SQR"_0 - "SQR"_1)\/(p_1 - p_0))/("SQR"_1\/(n - p_1)). $
Variáveis correlacionadas podem ser individualmente não significativas e, juntas, muito significativas.

$R^2 = 1 - "SQR"\/"SQT"$, em que SQT é a soma dos quadrados em torno da média. O $R^2$ nunca diminui ao incluir variáveis, por isso não serve para escolher modelos.

#table(
  columns: (auto, 1fr, 1fr),
  [Problema], [Sintoma e efeito], [Remédio],
  [Heterocedasticidade], [Variância dos resíduos muda; erros-padrão errados], [Erros robustos (White)],
  [Autocorrelação], [Resíduos dependentes; $t$ inflado], [Newey–West, blocos],
  [Colinearidade], [Coeficientes instáveis; $"VIF"_j = 1\/(1 - R_j^2)$ alto], [Remover, combinar, ridge],
  [Pontos influentes], [Poucos dados decidem o ajuste], [Alavancagem $H_(i i)$, distância de Cook],
  [Não linearidade], [Padrão no gráfico de resíduos], [Transformar, interações, _splines_],
)

== Regularização e modelos relacionados

=== Ridge

$ hat(beta)^"ridge" = argmin_beta norm(y - X beta)^2 + lambda norm(beta)^2 = (X^top X + lambda I)^(-1) X^top y. $
Sempre tem solução para $lambda > 0$. Pela decomposição em valores singulares $X = U D V^top$, cada direção é encolhida pelo fator $d_j^2\/(d_j^2 + lambda)$: as direções de pouca variância encolhem mais.

=== Lasso

Troca a penalidade por $lambda sum_j abs(beta_j)$ e zera coeficientes, fazendo seleção de variáveis. Com colunas ortonormais (e a perda $1/2 norm(y - X beta)^2$), a solução é o _soft-thresholding_ da solução de mínimos quadrados:
$ hat(beta)_j^"lasso" = "sinal"(hat(beta)_j) max(abs(hat(beta)_j) - lambda, 0). $

#intuicao[
  Ridge equivale a supor uma distribuição a priori normal para os coeficientes; lasso, uma de Laplace, com bico em zero. A geometria conta a mesma história: a bola da norma 1 tem quinas nos eixos, e é nas quinas que a solução costuma parar. A _elastic net_ mistura as duas penalidades e lida melhor com grupos de variáveis correlacionadas.
]

Padronize as variáveis antes de penalizar e não penalize o intercepto.

=== Seleção de variáveis

A busca do melhor subconjunto é combinatória. A seleção _stepwise_ adiciona (ou remove) uma variável por vez. A regressão de menor ângulo (LAR) aumenta gradualmente os coeficientes das variáveis mais correlacionadas com o resíduo e, com uma pequena modificação, percorre todo o caminho do lasso. Depois de selecionar variáveis nos mesmos dados, os valores-p usuais ficam otimistas.

=== Regressão logística

Para resposta binária, o logaritmo das chances é linear:
$ log (p(x))/(1 - p(x)) = x^top beta, quad p(x) = 1/(1 + e^(-x^top beta)). $
Ajusta-se por máxima verossimilhança, sem fórmula fechada. $e^(beta_j)$ é o fator pelo qual as chances se multiplicam quando $x_j$ sobe uma unidade. Se as classes são perfeitamente separáveis, os coeficientes divergem; a regularização resolve.

== Redução de dimensionalidade

A *análise de componentes principais* (PCA) procura direções ortogonais de máxima variância. São os autovetores $v_j$ da matriz de covariância; o autovalor $lambda_j$ é a variância do componente $z_j = X v_j$, e a fração explicada é $lambda_j\/sum_k lambda_k$.

- *Regressão em componentes principais:* regride $y$ nos primeiros componentes. Ignora $y$ ao escolher as direções.
- *Mínimos quadrados parciais:* escolhe direções que combinam variância de $X$ e correlação com $y$.
- Padronize quando as escalas forem diferentes. Em finanças, o primeiro componente de retornos de ações costuma ser "o mercado".

#problema("PCA de duas variáveis")[
  Duas variáveis padronizadas têm correlação $rho > 0$. Quais os componentes e quanto o primeiro explica?
]
#solucao[
  A matriz $mat(1, rho; rho, 1)$ tem autovalores $1 + rho$ e $1 - rho$, com autovetores $(1, 1)\/sqrt(2)$ e $(1, -1)\/sqrt(2)$. O primeiro explica $(1 + rho)\/2$.
]

== Validação

- Separe treino, validação e teste. O teste é usado *uma vez*.
- A validação cruzada em $K$ partes estima o erro fora da amostra e escolhe hiperparâmetros.
- Em séries temporais, o treino vem antes do teste (_walk-forward_). Retire do treino as observações cujo rótulo se sobrepõe ao período de teste (_purge_) e deixe uma folga (_embargo_).
- *Vazamento* é usar informação que não existiria na hora da decisão: padronizar com a média da amostra inteira, escolher variáveis antes de dividir os dados, usar dados revisados depois.

== Perguntas clássicas sobre regressão

#problema("as duas regressões")[
  A inclinação de $y$ em $x$ é 0,8 e a correlação é 0,5. Qual a inclinação de $x$ em $y$?
]
#solucao[
  $beta_(y x) = rho sigma_y\/sigma_x$ e $beta_(x y) = rho sigma_x\/sigma_y$, logo o produto é $rho^2$: $beta_(x y) = 0.25\/0.8 = 0.3125$. Não é $1\/0.8$.
]

#problema("dados duplicados")[
  Você copia cada linha da base e ajusta de novo. O que muda?
]
#solucao[
  $X^top X$ e $X^top y$ dobram, então $hat(beta)$ não muda e o $R^2$ também não. Os erros-padrão caem por um fator perto de $1\/sqrt(2)$ e os $t$ sobem, sem informação nova: a hipótese de independência foi violada.
]

#problema("mudança de unidade")[
  O que acontece se uma variável explicativa passa de metros para centímetros?
]
#solucao[
  Seus valores são multiplicados por 100, o coeficiente e o erro-padrão são divididos por 100; $t$, $R^2$ e previsões não mudam. Com ridge ou lasso sem padronização, as previsões *mudariam*.
]

#problema("erro de medida")[
  Observa-se $x^* = x + u$, com $u$ ruído independente. O que acontece com a inclinação?
]
#solucao[
  Ela é atenuada em direção a zero:
  $ beta^* = beta sigma_x^2/(sigma_x^2 + sigma_u^2). $
  Ruído em $y$, ao contrário, só aumenta a variância do estimador.
]

#problema("variáveis quase iguais")[
  Duas variáveis têm correlação 0,999. O que esperar de mínimos quadrados, ridge e lasso?
]
#solucao[
  Mínimos quadrados determina bem a soma dos coeficientes e mal cada um deles. Ridge divide o efeito entre as duas. Lasso tende a escolher uma, e a escolha pode trocar com pequenas mudanças nos dados.
]

== A visão da econometria

Prever e explicar são tarefas diferentes. A econometria pergunta pelo efeito *causal*: o que aconteceria com $y$ se mudássemos o tratamento $D$, mantendo o resto igual.

=== Viés de seleção

Sejam $Y_1$ e $Y_0$ os resultados potenciais com e sem tratamento. A diferença observada se decompõe em
$ EE[Y|D=1] - EE[Y|D=0] &= EE[Y_1 - Y_0 | D=1] \ &+ (EE[Y_0|D=1] - EE[Y_0|D=0]), $
o efeito sobre os tratados mais o viés de seleção. Um *experimento aleatorizado* torna $D$ independente de $(Y_0, Y_1)$ e zera o segundo termo.

=== Variável omitida

Compare a regressão longa (com o controle $A$) à curta (sem ele). Se $gamma$ é o coeficiente de $A$ na longa e $delta$ é a inclinação de $A$ em $D$:
$ beta^"curta" = beta^"longa" + delta gamma. $

#problema("sinal do viés")[
  Na regressão longa, o efeito do tratamento é 1 e o do controle é 2. A inclinação do controle no tratamento é 0,5. Quanto dá a regressão curta?
]
#solucao[
  $beta^"curta" = 1 + 0.5 dot 2 = 2$: o dobro do efeito verdadeiro.
]

=== Quando não há experimento

#table(
  columns: (auto, 1fr, 1fr),
  [Método], [Ideia], [Hipótese crítica],
  [Controles], [Comparar iguais nas variáveis observadas], [Nada relevante ficou de fora],
  [Variável instrumental], [Usar variação de $D$ vinda de um instrumento $Z$: $Cov(Z, Y)\/Cov(Z, D)$], [$Z$ afeta $D$ e só afeta $Y$ por meio de $D$],
  [Diferenças em diferenças], [Comparar a variação dos tratados com a do grupo de controle], [Tendências paralelas],
  [Descontinuidade], [Comparar quem ficou logo acima e logo abaixo de um corte], [Ninguém manipula a posição no corte],
)
