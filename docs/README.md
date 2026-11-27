# Documentação do quant

Retrato de 27/11/2026. Onde houver conflito entre estes textos e o código, vale o código.

## Em uma página

- **O que é:** um repositório de pesquisa quantitativa em Python e um sistema que opera sozinho na **conta demo** da
  Kalshi (contratos perpétuos), com painel web, rodando numa VM.
- **O que não é:** não há dinheiro real em operação e **nenhuma estratégia foi aprovada** pela regra do repositório
  (DSR ≥ 0,95). O que roda na demo serve para acumular evidência.
- **Melhor candidata:** `trend_follow` em barras de 1 h em 19 criptomoedas ([`trend_19cripto`](../estudos/trend_19cripto/README.md)),
  com veredito *inconclusivo*.

## Documentos

| Documento | Para saber |
|---|---|
| [arquitetura.md](arquitetura.md) | Como as peças se ligam e onde cada dado fica |
| [robo.md](robo.md) | O robô de regras: sinal, entrada, saída, risco e parâmetros |
| [ia.md](ia.md) | O agente de IA: ciclo, travas, modo sombra e o que se mediu |
| [painel.md](painel.md) | Telas, API, papéis e segurança |
| [operacao.md](operacao.md) | Dia a dia da VM: serviços, publicar, reverter, parar, diagnosticar |
| [pesquisa.md](pesquisa.md) | Todos os estudos, veredictos e lições |
| [biblioteca.md](biblioteca.md) | Pacote Python, dados, backtest, testes e adapters (MT5, Profit) |

## Documentos que já existiam

| Documento | Conteúdo |
|---|---|
| [../README.md](../README.md) | Visão do repositório e tabela de pesquisa |
| [../deploy/README.md](../deploy/README.md) | Instalação passo a passo da VM |
| [roteiro_testnet.md](roteiro_testnet.md) | Validação da execução na testnet da Binance |
| [dados.md](dados.md) | Fontes de dados |
| [conceitos/](conceitos/README.md) | Notas de teoria: fundamentos, ações, renda fixa, macro, derivativos, microestrutura, validação |
| [quant-bible/guia/main.pdf](quant-bible/guia/main.pdf) | Guia de estudos para entrevistas de quant |
| [../execucao/README.md](../execucao/README.md) | Robôs para MetaTrader 5 e Profit Pro |

## Começar em 5 minutos

```bash
pip install -e ".[dev]"
pytest
ruff check src tests estudos
python estudos/win_trend/run_backtest.py
```

Painel (desenvolvimento): `python -m quant.control` em um terminal e `cd web && npm ci && npm start` em outro.
