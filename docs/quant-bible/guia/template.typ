// Template do guia de estudo quant (PT-BR)
#let cor = rgb("#1f3a5f")
#let Var = math.op("Var")
#let Cov = math.op("Cov")
#let Corr = math.op("Corr")
#let argmin = math.op("arg min", limits: true)
#let argmax = math.op("arg max", limits: true)

#let projeto(titulo: "", subtitulo: "", corpo) = {
  set document(title: titulo)
  set page(paper: "a4", margin: (x: 2.5cm, y: 2.5cm), numbering: "1",
    header: context if counter(page).get().first() > 1 [
      #set text(size: 9pt, fill: luma(120))
      #titulo #h(1fr) #subtitulo
      #line(length: 100%, stroke: 0.4pt + luma(200))
    ])
  set text(lang: "pt", region: "br", font: "Libertinus Serif", size: 11pt)
  set par(justify: true, leading: 0.7em)
  set heading(numbering: "1.1")
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    set text(fill: cor, size: 20pt)
    v(1cm); it; v(0.5cm)
  }
  show heading.where(level: 2): set text(fill: cor)
  set math.equation(numbering: "(1)")
  // virgula decimal: nas formulas, escreva 0.5 e o guia mostra 0,5
  show math.equation: it => {
    show regex("^\d+\.\d+$"): n => n.text.replace(".", ",")
    it
  }
  show table.cell.where(y: 0): set text(weight: "bold", fill: cor)
  set table(stroke: 0.5pt + luma(190), inset: 6pt)
  show table: set par(justify: false)

  align(center + horizon)[
    #text(size: 30pt, weight: "bold", fill: cor)[#titulo]
    #v(0.5cm)
    #text(size: 14pt, fill: luma(100))[#subtitulo]
  ]
  pagebreak()
  outline(title: "Sumário", depth: 2)
  corpo
}

#let caixa(titulo, corpo, cor-borda: cor, gruda: false) = block(
  width: 100%, inset: 10pt, radius: 4pt, sticky: gruda,
  stroke: (left: 3pt + cor-borda), fill: cor-borda.lighten(92%),
)[#text(weight: "bold", fill: cor-borda)[#titulo] \ #corpo]

#let definicao(corpo) = caixa("Definição", corpo)
#let intuicao(corpo) = caixa("Intuição", corpo, cor-borda: rgb("#2e7d32"))
#let problema(titulo, corpo) = caixa("Problema: " + titulo, corpo, cor-borda: rgb("#b45309"), gruda: true)
#let solucao(corpo) = block(breakable: false, inset: (left: 10pt))[#text(weight: "bold")[Solução.] #corpo]
