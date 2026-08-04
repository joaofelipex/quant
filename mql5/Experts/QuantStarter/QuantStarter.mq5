//+------------------------------------------------------------------+
//| QuantStarter.mq5                                                 |
//| EA quant B3: momentum (EMA) ou mean reversion (BB+RSI)           |
//| + sessão B3 + ATR stops + risco % equity                         |
//|                                                                  |
//| Foque em WIN/WDO ou ações (PETR4, VALE3...). Confira o nome do   |
//| símbolo no Market Watch do seu broker MT5.                       |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property version   "1.20"
#property strict
#property description "EA quant B3: EMA/MeanRev + sessão B3 + ATR + risk %"

#include "Include\RiskManager.mqh"
#include "Include\SignalEngine.mqh"
#include "Include\MeanReversion.mqh"
#include "Include\SessionFilter.mqh"
#include "Include\TradeManager.mqh"

enum ENUM_STRATEGY_MODE
  {
   STRATEGY_MOMENTUM = 0,       // Cruzamento EMA
   STRATEGY_MEAN_REVERSION = 1  // Bollinger + RSI
  };

input group "=== Estratégia ==="
input ENUM_STRATEGY_MODE InpStrategy     = STRATEGY_MOMENTUM; // Modo
input int               InpFastEMA       = 9;           // EMA rápida (momentum)
input int               InpSlowEMA       = 21;          // EMA lenta (momentum)
input int               InpBBPeriod      = 20;          // Bollinger período
input double            InpBBDeviation   = 2.0;         // Bollinger desvio
input int               InpRSIPeriod     = 14;          // RSI período
input double            InpRSI_OS        = 30.0;        // RSI oversold
input double            InpRSI_OB        = 70.0;        // RSI overbought
input int               InpATRPeriod     = 14;          // Período ATR
input double            InpATR_SL        = 1.5;         // SL = ATR * fator
input double            InpATR_TP        = 2.0;         // TP = ATR * fator
input double            InpMinATRPoints  = 0;           // ATR mín. (0=desliga). WIN: tente 80–150

input group "=== Sessão B3 (hora do servidor) ==="
input ENUM_TRADE_SESSION InpSession      = SESSION_B3_EQUITY; // Janela
input int               InpCustomStartH  = 10;          // Custom início (h)
input int               InpCustomStartM  = 15;          // Custom início (min)
input int               InpCustomEndH    = 16;          // Custom fim (h)
input int               InpCustomEndM    = 45;          // Custom fim (min)
input int               InpSkipOpenMin   = 15;          // Pular minutos pós-abertura
input bool              InpSkipFridayLate= true;        // Bloquear sexta tarde
input int               InpFridayCutH    = 16;          // Corte sexta (h)
input int               InpFridayCutM    = 30;          // Corte sexta (min)

input group "=== Risco ==="
input double            InpRiskPercent   = 0.5;         // Risco % equity / trade (B3: comece baixo)
input double            InpMaxDailyLoss  = 2.0;         // Perda máx. diária (%)
input int               InpMaxPositions  = 1;           // Máx. posições
input bool              InpReverseOnSignal= true;       // Fecha e inverte no sinal oposto

input group "=== Execução ==="
input ulong             InpMagic         = 20260803;    // Magic number
input int               InpDeviation     = 50;          // Slippage (pontos) — ações B3 variam
input bool              InpOnlyNewBar    = true;        // Só em barra nova

CRiskManager    g_risk;
CSignalEngine   g_momentum;
CMeanReversion  g_meanrev;
CSessionFilter  g_session;
CTradeManager   g_trade;
datetime        g_last_bar = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpStrategy == STRATEGY_MOMENTUM && InpFastEMA >= InpSlowEMA)
     {
      Print("Fast EMA deve ser < Slow EMA");
      return INIT_PARAMETERS_INCORRECT;
     }

   g_risk.Configure(InpRiskPercent, InpMaxDailyLoss, InpMaxPositions);
   g_trade.Configure(InpMagic, InpDeviation, "QuantStarter");
   g_session.Configure(InpSession,
                       InpCustomStartH, InpCustomStartM,
                       InpCustomEndH, InpCustomEndM,
                       InpSkipOpenMin, InpSkipFridayLate,
                       InpFridayCutH, InpFridayCutM);

   if(InpStrategy == STRATEGY_MOMENTUM)
     {
      if(!g_momentum.Init(_Symbol, _Period, InpFastEMA, InpSlowEMA,
                          InpATRPeriod, InpMinATRPoints))
         return INIT_FAILED;
     }
   else
     {
      if(!g_meanrev.Init(_Symbol, _Period, InpBBPeriod, InpBBDeviation,
                         InpRSIPeriod, InpRSI_OS, InpRSI_OB, InpATRPeriod))
         return INIT_FAILED;
     }

   PrintFormat("QuantStarter v1.20 B3 | %s %s | mode=%s | risk=%.2f%% | %s",
               _Symbol, EnumToString(_Period),
               EnumToString(InpStrategy), InpRiskPercent,
               EnumToString(InpSession));
   Print("Dica: rode SymbolDiagnostics no gráfico para validar tick value (WIN/WDO/ações).");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   g_momentum.Release();
   g_meanrev.Release();
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(InpOnlyNewBar && !IsNewBar())
      return;

   if(!g_session.IsTradable())
      return;

   ENUM_TRADE_SIGNAL signal = SIGNAL_NONE;
   double atr = 0.0;

   if(InpStrategy == STRATEGY_MOMENTUM)
     {
      signal = g_momentum.Evaluate();
      atr    = g_momentum.LastATR();
     }
   else
     {
      signal = g_meanrev.Evaluate();
      atr    = g_meanrev.LastATR();
     }

   if(signal == SIGNAL_NONE || atr <= 0.0)
      return;

   double sl_dist = atr * InpATR_SL;
   double tp_dist = atr * InpATR_TP;
   double lots    = g_risk.LotSize(_Symbol, sl_dist);
   if(lots <= 0.0)
     {
      Print("[EA] Lote inválido — rode SymbolDiagnostics e confira margem/símbolo B3");
      return;
     }

   if(signal == SIGNAL_BUY)
     {
      if(InpReverseOnSignal)
         g_trade.CloseAll(_Symbol);
      if(!g_risk.CanOpenTrade(_Symbol, g_trade.Magic()))
         return;
      g_trade.OpenBuy(_Symbol, lots, sl_dist, tp_dist);
     }
   else if(signal == SIGNAL_SELL)
     {
      if(InpReverseOnSignal)
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
