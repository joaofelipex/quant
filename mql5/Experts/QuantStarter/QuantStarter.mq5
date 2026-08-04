//+------------------------------------------------------------------+
//| QuantStarter.mq5                                                 |
//| EA quant inicial: cruzamento EMA + filtro ATR + risco % equity   |
//|                                                                  |
//| Como usar no MetaTrader 5:                                       |
//| 1. Copie a pasta Experts\QuantStarter para:                      |
//|    <Dados do Terminal>\MQL5\Experts\                             |
//| 2. No MetaEditor (F4), abra QuantStarter.mq5 e Compile (F7)      |
//| 3. No MT5: Navegador > Expert Advisors > arraste no gráfico      |
//| 4. Habilite "Algo Trading" na toolbar                            |
//| 5. Strategy Tester (Ctrl+R) para backtest                        |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property version   "1.00"
#property strict
#property description "EA quant: EMA cross + ATR stops + risk % equity"

#include "Include\RiskManager.mqh"
#include "Include\SignalEngine.mqh"
#include "Include\TradeManager.mqh"

input group "=== Estratégia ==="
input int               InpFastEMA       = 12;          // EMA rápida
input int               InpSlowEMA       = 26;          // EMA lenta
input int               InpATRPeriod     = 14;          // Período ATR
input double            InpATR_SL        = 1.5;         // SL = ATR * este fator
input double            InpATR_TP        = 2.5;         // TP = ATR * este fator
input double            InpMinATRPoints  = 50;          // ATR mínimo (pontos) para operar

input group "=== Risco ==="
input double            InpRiskPercent   = 1.0;         // Risco % do equity por trade
input double            InpMaxDailyLoss  = 3.0;         // Perda máxima diária (%)
input int               InpMaxPositions  = 1;           // Máx. posições simultâneas
input bool              InpReverseOnCross= true;        // Fecha e inverte no cruzamento oposto

input group "=== Execução ==="
input ulong             InpMagic         = 20260803;    // Magic number
input int               InpDeviation     = 20;          // Slippage (pontos)
input bool              InpOnlyNewBar    = true;        // Avaliar só em barra nova

CRiskManager   g_risk;
CSignalEngine  g_signal;
CTradeManager  g_trade;
datetime       g_last_bar = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpFastEMA >= InpSlowEMA)
     {
      Print("Fast EMA deve ser < Slow EMA");
      return INIT_PARAMETERS_INCORRECT;
     }

   g_risk.Configure(InpRiskPercent, InpMaxDailyLoss, InpMaxPositions);
   g_trade.Configure(InpMagic, InpDeviation, "QuantStarter");

   if(!g_signal.Init(_Symbol, _Period, InpFastEMA, InpSlowEMA,
                     InpATRPeriod, InpMinATRPoints))
      return INIT_FAILED;

   PrintFormat("QuantStarter OK | %s %s | risk=%.2f%%",
               _Symbol, EnumToString(_Period), InpRiskPercent);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   g_signal.Release();
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(InpOnlyNewBar && !IsNewBar())
      return;

   ENUM_TRADE_SIGNAL signal = g_signal.Evaluate();
   if(signal == SIGNAL_NONE)
      return;

   double atr = g_signal.LastATR();
   if(atr <= 0.0)
      return;

   double sl_dist = atr * InpATR_SL;
   double tp_dist = atr * InpATR_TP;
   double lots    = g_risk.LotSize(_Symbol, sl_dist);
   if(lots <= 0.0)
     {
      Print("[EA] Lote inválido — verifique margem/símbolo");
      return;
     }

   if(signal == SIGNAL_BUY)
     {
      if(InpReverseOnCross)
         g_trade.CloseAll(_Symbol);
      if(!g_risk.CanOpenTrade(_Symbol, g_trade.Magic()))
         return;
      g_trade.OpenBuy(_Symbol, lots, sl_dist, tp_dist);
     }
   else if(signal == SIGNAL_SELL)
     {
      if(InpReverseOnCross)
         g_trade.CloseAll(_Symbol);
      if(!g_risk.CanOpenTrade(_Symbol, g_trade.Magic()))
         return;
      g_trade.OpenSell(_Symbol, lots, sl_dist, tp_dist);
     }
  }

//+------------------------------------------------------------------+
bool IsNewBar()
  {
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == 0)
      return false;
   if(t == g_last_bar)
      return false;
   g_last_bar = t;
   return true;
  }
//+------------------------------------------------------------------+
