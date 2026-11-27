#import "../template.typ": *

= Introdução

Este guia reúne o que costuma ser cobrado em entrevistas de finanças quantitativas: probabilidade, estatística, regressão, estudos de caso, _market making_ e um banco de problemas. O texto e os problemas são próprios; a ordem dos assuntos acompanha a do _Quant Bible_ do MIT Sloan Business Club, usado como roteiro.

== Os três caminhos

#table(
  columns: (auto, 1fr, 1fr),
  [Função], [O que faz], [O que a entrevista mede],
  [_Quant trader_], [Precifica, cota e administra risco em tempo real.], [Probabilidade de cabeça, valor esperado, decisão sob pressão, _market making_.],
  [_Quant researcher_], [Procura e valida sinais em dados.], [Estatística, regressão, desenho de experimentos, estudos de caso.],
  [_Quant developer_], [Constrói os sistemas de dados, pesquisa e execução.], [Algoritmos, estruturas de dados, sistemas, C++ ou Python.],
)

Este guia cobre bem os dois primeiros. Para desenvolvimento, é preciso estudar programação e sistemas à parte.

== Como estudar

+ *Entenda antes de decorar.* Em cada fórmula, saiba dizer de onde ela vem e quando deixa de valer.
+ *Resolva antes de ler a solução.* Dê ao menos dez minutos a cada problema, escrevendo as hipóteses.
+ *Fale enquanto resolve.* O entrevistador avalia o raciocínio; um caminho claro com um erro de conta vale mais que um número solto.
+ *Treine conta de cabeça.* Frações, porcentagens, raízes aproximadas e potências de 2.
+ *Revise em ciclos.* Volte aos problemas que errou depois de uma semana e depois de um mês.

#intuicao[
  Diante de um problema novo, tente nesta ordem: um caso pequeno (2 moedas em vez de $n$), simetria, linearidade da esperança, condicionar no primeiro passo. Boa parte dos problemas cai em uma dessas quatro ideias.
]

== Roteiro sugerido

#table(
  columns: (auto, 1fr),
  [Semanas], [Assunto],
  [1 e 2], [Capítulo 2: probabilidade],
  [3], [Capítulo 3: estatística],
  [4 e 5], [Capítulo 4: regressão e ciência de dados],
  [6 e 7], [Capítulos 5 e 6: estudos de caso e _market making_ (em dupla)],
  [8], [Capítulo 7: banco de questões, com tempo marcado],
)
