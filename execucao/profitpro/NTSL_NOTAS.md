# NTSL (Profit Pro) — notas de sintaxe e semântica

Confirmado por compilação no editor do usuário ou pelo manual (`manual_ntsl_texto.txt`). O NTSL do Profit
difere do NTSL "público".

## Sintaxe

- Parâmetros: `parâmetro` · tipos: `Real`, `booleano` · lógicos: `e`, `ou`, `not` · literais `verdadeiro`/`falso`.
- Séries: `Fechamento`, `Maxima`, `Minima`, `Abertura` · `mediaexp(periodo, serie)` · `macd(lenta, rapida, sinal)`.
- **Não existem** (erro de compilação): `Maior`, `Menor`, `Maximo`, `Minimo`, `Hora`. Para canal Donchian use
  `Highest(Maxima, n)` / `Lowest(Minima, n)`; para ATR use `TrueHigh() - TrueLow()` suavizado com `mediaexp`.
- Colar linhas muito longas no editor trunca identificadores: quebre expressões em várias linhas.

## Semântica de ordens (a que mais custou dinheiro)

- **`SellToCover*` fecha posição COMPRADA; `BuyToCover*` fecha posição VENDIDA.** Se invertido, a ordem é
  ignorada e a posição nunca fecha. Foi o bug das v2–v9.
- Ordens `ToCover` são enviadas como **OCO** e reenviadas/atualizadas a cada candle: stop + alvo ao mesmo tempo
  é o padrão (`SellToCoverStop(stop, limite)` + `SellToCoverLimit(alvo)`).
- `Buy`/`Sell` com posição oposta viram cobertura automaticamente; com posição do mesmo lado **aumentam** a
  posição → sempre proteger com `BuyPosition = 0 e SellPosition = 0` (bug de pirâmide).
- Ordens não executadas até o fim do candle seguinte são canceladas, salvo reenvio.

## Armadilhas

- `Time` é a hora de **abertura** do candle, inteiro `HHMM` (ex.: `915`, `1750`).
- `Date` é **função** (`1AAMMDD`), não série: `Date[1]` não é confiável. Guarde a data anterior numa variável
  (`dataAnt`) e compare. Suspeita principal de a v13 não ter operado.
- `DailyResult(verdadeiro)` = resultado do dia, fechado + aberto, em R$.
- Backtest do Profit e backtest Python **não coincidem** por padrão: confira nº de trades e motivos de saída
  contra `estudos/win_trend/reports/trades_*.csv` antes de confiar em qualquer dos dois.
