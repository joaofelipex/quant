#import "../template.typ": *

= Market making

== O que é

Um formador de mercado se compromete a comprar e vender: publica um preço de compra (_bid_) e um de venda (_ask_). Ganha a diferença, o _spread_, quando negocia dos dois lados, e presta liquidez a quem tem pressa. Corre dois riscos principais:

- *Estoque:* depois de comprar, fica exposto à queda do preço até conseguir vender.
- *Seleção adversa:* quem negocia pode saber mais. O formador compra justamente antes de o preço cair.

Em uma entrevista, "faça um mercado em $X$" pede duas coisas: um _bid_ e um _ask_, como "9 a 11". Quem aceita seu preço pode *comprar de você no ask* ou *vender para você no bid*.

== Teoria

Toda cotação responde a três perguntas.

+ *Onde está o meio?* No seu valor justo, atualizado com o que as negociações revelam.
+ *Qual a largura?* Maior quanto mais incerto o valor e quanto mais informada a contraparte.
+ *Para onde inclinar?* Para reduzir o estoque: comprado, baixe os dois preços; vendido, suba.

=== Por que existe spread

Um modelo simplificado de Glosten e Milgrom: o ativo vale $V_H$ ou $V_L$ com a mesma chance. Uma fração $alpha$ dos clientes sabe o valor e negocia a favor; os demais compram ou vendem ao acaso. Sem lucro nem prejuízo esperado, o _ask_ é $EE[V | "compra"]$.

#problema("spread de equilíbrio")[
  $V_H = 110$, $V_L = 90$ e 20% dos clientes são informados. Quais o _bid_ e o _ask_?
]
#solucao[
  $P("compra" | V_H) = 0.2 + 0.8 dot 0.5 = 0.6$ e $P("compra" | V_L) = 0.4$. Por Bayes, $P(V_H | "compra") = 0.6$, logo
  $ "ask" = 0.6 dot 110 + 0.4 dot 90 = 102, quad "bid" = 98. $
  O _spread_ é $alpha (V_H - V_L) = 4$. Depois de uma compra, o valor justo passa a ser 102: o mercado se move com o fluxo, mesmo sem notícia.
]

=== Estoque

No modelo de Avellaneda e Stoikov, o preço de referência do formador se afasta do preço de mercado $s$ conforme o estoque $q$:
$ r = s - q gamma sigma^2 (T - t), $
em que $gamma$ é a aversão a risco e $sigma^2$ a variância do preço por unidade de tempo. Mais estoque, mais volatilidade ou mais tempo até o fim pedem um ajuste maior.

=== Quanto apostar

#definicao[
  *Critério de Kelly:* para uma aposta que paga $b$ por unidade com probabilidade $p$ e perde a unidade com probabilidade $q = 1 - p$, a fração do capital que maximiza o crescimento de longo prazo é $f^* = p - q\/b$.
]

Com $p = 0.6$ e $b = 1$, $f^* = 0.2$, e o crescimento esperado é $0.6 ln 1.2 + 0.4 ln 0.8 approx 2.0%$ por aposta. Apostar o dobro de Kelly leva esse crescimento a cerca de zero (aqui, um pouco abaixo). Como $p$ é estimado, na prática se usa uma fração de Kelly.

=== Arbitragem entre mercados

Se $X$ é cotado em 10 a 12, $Y$ em 20 a 22 e $X + Y$ em 35 a 36, compre $X$ a 12 e $Y$ a 22 e venda a soma a 35: lucro certo de 1. Ao cotar várias coisas ligadas entre si, verifique se as suas próprias cotações não permitem isso.

=== Opção em um passo

Uma ação vale 100 e valerá 120 ou 80; juros zero. Uma opção de compra com preço de exercício 100 paga 20 ou 0. A carteira com $Delta = (20 - 0)\/(120 - 80) = 0.5$ ação e 40 de empréstimo replica o pagamento, logo a opção vale $0.5 dot 100 - 40 = 10$. A probabilidade real de alta não entra: basta a probabilidade neutra ao risco, $q = (100 - 80)\/(120 - 80) = 0.5$.

== Cenários de treino

=== Cenário 1: soma de três dados

Três dados serão rolados e revelados um a um. O valor justo inicial é $10.5$ e o desvio-padrão é $sqrt(3 dot 35\/12) approx 2.96$.

#table(
  columns: (auto, auto, auto, auto, 1fr),
  [Rodada], [Sua cotação], [Cliente], [Posição], [Raciocínio],
  [1], [9,5 a 11,5], [compra], [$-1$], [Centrada no valor justo],
  [2], [10,5 a 12,5], [compra], [$-2$], [Subir: a compra informa e você está vendido],
  [3], [11,5 a 13], [vende], [$-1$], [Sai um 5: justo $5 + 7 = 12$; meio acima por estar vendido],
)

Os outros dados saem 4 e 6, soma 15. O caixa é $11.5 + 12.5 - 11.5 = 12.5$ e a posição vendida de 1 custa 15: resultado $-2.5$. A cotação foi razoável e o resultado, negativo; avalie a decisão pelo que se sabia na hora.

=== Cenário 2: estimativa

_Faça um mercado no número de farmácias da sua cidade._

+ Estime em voz alta: população dividida por habitantes por farmácia (por exemplo, 1 milhão e uma a cada 4 mil dá 250).
+ Comece largo, na proporção da incerteza: 180 a 350.
+ Se o cliente comprar a 350, o valor provavelmente está acima. Mova o mercado bastante, por exemplo 320 a 480.
+ Se depois ele vender a 320, você tem um limite de cada lado: aperte, e mova menos a cada negócio.
+ Ao final, informe sem hesitar a posição e o preço médio.

=== Regras de bolso

- Responda sempre com os dois lados, e depressa.
- Depois de ser negociado, *mova* o preço. Repetir a mesma cotação é convite para perder de novo.
- Mantenha a contagem de posição e caixa. Resultado $=$ caixa $+$ posição $times$ valor final.
- Trocou a posição de lado? Os negócios casados já travaram um resultado, ganho ou perda.
- Não tenha apego ao primeiro palpite: o fluxo é informação.

=== Ordens limite em mercados eletrônicos

Quem deixa a ordem no livro costuma pagar taxa menor e ganhar o _spread_, mas só é executado quando alguém aceita negociar, o que é mais frequente quando o preço vai atravessá-lo. Compare sempre o resultado das ordens executadas com o das que ficaram sem execução.
