#import "../template.typ": *

= Banco de questões

Problemas organizados por tema, a maioria clássicos de probabilidade, com enunciados próprios. Resolva com tempo marcado: de 3 a 5 minutos nas de aquecimento e até 15 nas demais. As respostas estão no fim do capítulo.

#let q = counter("questao")
#let questao(titulo, corpo) = block(breakable: false, width: 100%)[
  #q.step()
  #text(weight: "bold", fill: cor)[#context q.display(). #titulo.] #corpo
]

== Aquecimento

#questao[Duas crianças][Uma família tem duas crianças e você sabe que ao menos uma é menina. Supondo os sexos equiprováveis e independentes, qual a chance de as duas serem meninas?]

#questao[Maior de dois dados][Qual o valor esperado do maior resultado em dois dados?]

#questao[Primeiro ás][Quantas cartas, em média, se viram de um baralho de 52 até aparecer o primeiro ás (contando o ás)?]

#questao[Distância][Dois pontos uniformes e independentes em $[0, 1]$. Qual a distância média entre eles?]

#questao[Aniversários][Com 23 pessoas e 365 datas equiprováveis, a chance de alguma coincidência passa de 50%? Estime sem calculadora.]

#questao[Formigas][Em uma vareta de 1 metro há 50 formigas andando a 1 cm/s, cada uma para um lado. Ao se encontrarem, invertem o sentido; na ponta, caem. Qual o tempo máximo até não sobrar nenhuma?]

== Probabilidade

#questao[Quatro portas][Há um prêmio atrás de uma de quatro portas. Você escolhe uma; o apresentador, que sabe onde está o prêmio, abre outra vazia. Se você trocar para uma das duas restantes, ao acaso, qual a chance de ganhar?]

#questao[Ruína do jogador][Você tem 3 fichas e aposta 1 por vez em um jogo justo, até chegar a 10 ou a 0. Qual a chance de chegar a 10 e quantas rodadas se esperam?]

#questao[Ruína com vantagem][Na questão anterior, se cada rodada é ganha com probabilidade 0,6, qual a chance de chegar a 10?]

#questao[Três caras][Quantos lançamentos de uma moeda justa, em média, até três caras seguidas?]

#questao[Corrida de padrões][Lança-se uma moeda até aparecer cara-cara-cara ou coroa-cara-cara (nesta ordem). Qual a chance de coroa-cara-cara vir primeiro?]

#questao[Passar de 1][Somam-se uniformes em $(0, 1)$ até o total passar de 1. Quantas parcelas são usadas em média?]

#questao[Dez caras][A probabilidade de cara de uma moeda é desconhecida, uniforme em $(0, 1)$ a priori. Saíram 10 caras em 10 lançamentos. Qual a chance de cara no próximo?]

== Valor esperado e decisão

#questao[Cartas vermelhas e pretas][Um baralho tem 2 cartas vermelhas e 2 pretas. Cada vermelha virada vale $+1$ e cada preta $-1$, e você pode parar quando quiser. Quanto vale o jogo?]

#questao[Paradoxo com teto][Lança-se uma moeda até a primeira cara, no lançamento $k$, e paga-se $2^k$ reais, limitado a $2^20$. Quanto vale o jogo?]

#questao[Maldição do vencedor][Um bem vale $V$ para o dono, uniforme entre 0 e 100, e $1.5 V$ para você. Só o dono conhece $V$ e aceita sua oferta $b$ se $b >= V$. Quanto ofertar?]

#questao[Tamanho da aposta][Uma aposta paga 2 para 1 e é ganha com probabilidade 0,4. Que fração do capital o critério de Kelly indica?]

== Estatística e álgebra

#questao[Números de série][De uma frota numerada a partir de 1 foram vistos os veículos 19, 40, 42 e 60. Estime o total.]

#questao[Dias até a significância][Uma estratégia ganha em média 0,1% ao dia com desvio de 1%. Quantos dias independentes para $t = 2$?]

#questao[Correlação possível][$"Corr"(A, B) = 0.9$ e $"Corr"(A, C) = 0.9$. Em que intervalo pode estar $"Corr"(B, C)$?]

#questao[Regressão sem informação][Regride-se um ruído em 50 variáveis aleatórias independentes, com 100 observações e intercepto. Que $R^2$ esperar?]

#questao[Soma de variâncias][$X$ e $Y$ têm variância 1 e correlação $-0.5$. Qual a variância de $X + Y$ e de $X - Y$?]

== Respostas

#let resposta(n, corpo) = block(breakable: false)[*#n.* #corpo]

#resposta(1)[$1/3$. Os casos possíveis são MM, MH e HM. Se a informação fosse "a mais velha é menina", seria $1/2$.]

#resposta(2)[$P(M = k) = (2k - 1)/36$, e $EE[M] = 161/36 approx 4.47$.]

#resposta(3)[Os 4 ases dividem as 48 outras cartas em 5 blocos de mesma média: $48/5 + 1 = 10.6$.]

#resposta(4)[$1/3$: dois pontos dividem o intervalo em três pedaços de mesma média.]

#resposta(5)[Sim. Há $binom(23, 2) = 253$ pares, e $1 - e^(-253\/365) approx 0.50$; o valor exato é $0.507$.]

#resposta(6)[Como as formigas são indistinguíveis, o encontro equivale a uma atravessar a outra: no máximo 100 s.]

#resposta(7)[A porta inicial tem $1/4$; os $3/4$ restantes se dividem entre duas portas: $3/8$.]

#resposta(8)[$3/10$; a duração esperada é $3 dot (10 - 3) = 21$ rodadas.]

#resposta(9)[Com $r = q\/p = 2\/3$: $(1 - r^3)\/(1 - r^10) approx 0.716$.]

#resposta(10)[São 14 lançamentos. Em geral, para $n$ caras seguidas, $2^(n+1) - 2$.]

#resposta(11)[$7/8$. Cara-cara-cara só vence se os três primeiros lançamentos forem caras; caso contrário, uma coroa antecede a primeira dupla de caras.]

#resposta(12)[$P(N > n) = P(U_1 + dots + U_n <= 1) = 1\/n!$, logo $EE[N] = sum_(n >= 0) 1\/n! = e approx 2.718$.]

#resposta(13)[Regra da sucessão de Laplace: $(10 + 1)/(10 + 2) = 11/12$.]

#resposta(14)[$2/3$. Resolva de trás para a frente: em cada estado, o valor é o maior entre parar (0 adicional) e a média de continuar.]

#resposta(15)[Os 20 primeiros termos somam 1 cada e a cauda soma $2^20 dot 2^(-20) = 1$: total R\$ 21.]

#resposta(16)[Zero. O lucro esperado é $integral_0^b (1.5 v - b) dif v\/100 = -b^2\/400$: quando o dono aceita, a notícia é ruim.]

#resposta(17)[$f^* = 0.4 - 0.6\/2 = 0.1$.]

#resposta(18)[Com $m = 60$ o maior e $k = 4$ observações: $m (1 + 1\/k) - 1 = 74$.]

#resposta(19)[$n = (2 dot 1\/0.1)^2 = 400$ dias.]

#resposta(20)[$0.81 plus.minus (1 - 0.81) = [0.62, 1]$.]

#resposta(21)[$EE[R^2] = (p)/(n - 1) = 50\/99 approx 0.51$, apesar de não haver relação nenhuma.]

#resposta(22)[$1 + 1 - 1 = 1$ e $1 + 1 + 1 = 3$.]
