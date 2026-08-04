//+------------------------------------------------------------------+
//| QuantStarter.mq5                                                 |
//| EA quant: momentum (EMA) ou mean reversion (BB+RSI)              |
//| + filtro de sessão + ATR stops + risco % equity                  |
//|                                                                  |
//| Instalação: copie Experts\QuantStarter para MQL5\Experts\        |
//| Compile no MetaEditor (F7) → Strategy Tester (Ctrl+R)            |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property version   "1.10"
#property strict
#property description "EA quant: EMA/MeanRev + sessão + ATR + risk %"

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
input int               InpFastEMA       = 12;          // EMA rápida (momentum)
input int               InpSlowEMA       = 26;          // EMA lenta (momentum)
input int               InpBBPeriod      = 20;          // Bollinger período
input double            InpBBDeviation   = 2.0;         // Bollinger desvio
input int               InpRSIPeriod     = 14;          // RSI período
input double            InpRSI_OS        = 30.0;        // RSI oversold
input double            InpRSI_OB        = 70.0;        // RSI overbought
input int               InpATRPeriod     = 14;          // Período ATR
input double            InpATR_SL        = 1.5;         // SL = ATR * fator
input double            InpATR_TP        = 2.5;         // TP = ATR * fator
input double            InpMinATRPoints  = 50;          // ATR mín. (pontos) — só momentum

input group "=== Sessão (hora do servidor) ==="
input ENUM_TRADE_SESSION InpSession      = SESSION_OVERLAP; // Janela
input int               InpLondonStart   = 8;           // Londres início
input int               InpLondonEnd     = 17;          // Londres fim
input int               InpNYStart       = 13;          // NY início
input int               InpNYEnd         = 22;          // NY fim
input bool              InpSkipFridayLate= true;        // Bloquear sexta tarde
input int               InpFridayCutoff  = 16;          // Corte sexta (hora)

input group "=== Risco ==="
input double            InpRiskPercent   = 1.0;         // Risco % equity / trade
input double            InpMaxDailyLoss  = 3.0;         // Perda máx. diária (%)
input int               InpMaxPositions  = 1;           // Máx. posições
input bool              InpReverseOnSignal= true;       // Fecha e inverte no sinal oposto

input group "=== Execução ==="
input ulong             InpMagic         = 20260803;    // Magic number
input int               InpDeviation     = 20;          // Slippage (pontos)
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
   g_session.Configure(InpSession, InpLondonStart, InpLondonEnd,
                       InpNYStart, InpNYEnd, InpSkipFridayLate, InpFridayCutoff);

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

   PrintFormat("QuantStarter v1.10 | %s %s | mode=%s | risk=%.2f%% | %s",
               _Symbol, EnumToString(_Period),
               EnumToString(InpStrategy), InpRiskPercent,
               EnumToString(InpSession));
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
      Print("[EA] Lote inválido — verifique margem/símbolo");
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
