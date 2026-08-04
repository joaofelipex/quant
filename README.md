# Quant — MetaTrader 5 (Clear / B3)

Stack quant para **Clear MT5**: foco em **mini índice (WIN)**, também **ações** e **opções** (direcional simples).

## Clear — instalado nesta máquina

Terminal: **Clear Investimentos MT5**  
Pasta: `%APPDATA%\MetaQuotes\Terminal\698B86206820B42976F30D28CAC50412\MQL5`

### Setup rápido

1. Navegador → **Atualizar**
2. Market Watch (Ctrl+M) → Símbolos:
   - **WIN$** ou **WIN$N** (principal) · vencimento `WINxy`
   - Ações: `PETR4`, `VALE3`…
   - Opções: se a Clear listar no MT5 (nem todas as séries aparecem)
3. Perfil no EA:
   - `PROFILE_WIN` (default) → sessão Futures Day, ATR mín. 80, slip 30
   - `PROFILE_EQUITY` → pregão ações, slip maior, sem ATR mín.
   - `PROFILE_OPTIONS` → risco teto 0,25%, sem invert-on-signal
4. `SymbolDiagnostics` no gráfico → confere R$/ponto e lote
5. Strategy Tester (Ctrl+R) em demo antes de Algo Trading real

## Perfis

| Perfil | Símbolo típico | Sessão | Notas |
|--------|----------------|--------|--------|
| WIN | `WIN$`, `WIN$N` | Futures Day 09:00–18:25 | Seu foco principal |
| Equity | `PETR4`… | Equity 10:00–17:55 | Pula 15 min de abertura |
| Options | série da ação | Equity | EA **não** modela Gregas/vencimento — só compra/venda de prêmio |

Opções na Clear: estratégias com gregas/rolling costumam ser melhores em outras plataformas da corretora. Neste EA use só como experimento direcional e tamanho pequeno.

## Estratégias (v1.30)

| Modo | Sinal |
|------|--------|
| Momentum | EMA 9×21 (barra fechada) + ATR mín. (WIN) |
| Mean reversion | Bollinger + RSI |

Risco default: **0,5%** / trade (opções auto ≤ **0,25%**), perda diária máx. **2%**.

## Análise Python

```bash
cd python
pip install -r requirements.txt
python analyze_trades.py data/sample_trades.csv
```

## Fluxo recomendado (WIN primeiro)

1. Gráfico `WIN$` M5 ou M15
2. Perfil `WIN` + backtest no Tester
3. Exportar deals → `analyze_trades.py`
4. Depois replicar preset Equity / Options se quiser
