//+------------------------------------------------------------------+
//| QuantSage.mq5                                                    |
//| Bot quant B3/Clear: regime (ER) + confluência + risco sábio      |
//|                                                                  |
//| Filosofia:                                                       |
//|  - Só opera com edge mensurável (score)                          |
//|  - Trend → follow (EMA+RSI); Range → mean-reversion (z+RSI)      |
//|  - Chaos (ER intermediário) → não opera                          |
//|  - Sizing por risco%, score e volatilidade                       |
//|  - Timer atualiza status mesmo com mercado fechado               |
//|                                                                  |
//| Anexe pelo Navegador (NAO pelo debugger F5 do MetaEditor).       |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#property version   "2.01"
#property strict
#property description "QuantSage: edge score + regime ER + risco B3/Clear"

#include "Include\SessionB3.mqh"
#include "Include\RiskEngine.mqh"
#include "Include\EdgeEngine.mqh"
#include "Include\ExecEngine.mqh"

input group "=== Perfil ==="
input ENUM_QS_SESSION   InpSession       = QS_SESSION_FUTURES_DAY; // WIN default
input int               InpSkipOpenMin   = 10;          // Pular abertura (min)
input int               InpNoNewBeforeEnd= 20;          // Sem novas entradas antes do fim
input bool              InpSkipFridayLate= true;
input int               InpFridayH       = 16;
input int               InpFridayM       = 30;

input group "=== Edge (matemática) ==="
input int               InpERPeriod      = 20;          // Efficiency Ratio lookback
input double            InpERTrend       = 0.35;        // ER >= trend
input double            InpERRange       = 0.22;        // ER <= range
input int               InpEMAFast       = 9;
input int               InpEMASlow       = 21;
input int               InpZPeriod       = 20;          // z-score window
input double            InpZEntry        = 1.8;         // |z| para mean-reversion
input int               InpATRPeriod     = 14;
input int               InpATRLookback   = 50;          // percentil ATR
input double            InpMinScore      = 70;          // score mínimo p/ entrar (0-100)
input double            InpSL_ATR        = 1.4;         // stop = ATR * x
input double            InpTP_ATR        = 2.2;         // take = ATR * x
input double            InpTrailATR      = 1.6;         // trailing (0=off)
input bool              InpOnlyNewBar    = true;

input group "=== Risco ==="
input double            InpRiskPercent   = 0.5;         // % equity base
input double            InpMaxDailyLoss  = 2.0;         // circuit breaker dia
input double            InpMaxSpreadATR  = 0.12;        // spread/ATR máx
input int               InpMaxPositions  = 1;
input int               InpMaxLossStreak = 3;           // cooldown após N losses

input group "=== Execução ==="
input ulong             InpMagic         = 26080402;
input int               InpDeviation     = 30;

CSessionB3   g_session;
CRiskEngine  g_risk;
CEdgeEngine  g_edge;
CExecEngine  g_exec;
datetime     g_last_bar = 0;
string       g_last_detail = "boot";
QSEdge       g_last_edge;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_session.Configure(InpSession, InpSkipOpenMin, InpNoNewBeforeEnd,
                       InpSkipFridayLate, InpFridayH, InpFridayM);
   g_risk.Configure(InpRiskPercent, InpMaxDailyLoss, InpMaxSpreadATR,
                    InpMaxPositions, InpMaxLossStreak);
   g_exec.Configure(InpMagic, InpDeviation, "QuantSage");

   if(!g_edge.Init(_Symbol, _Period, InpERPeriod, InpEMAFast, InpEMASlow,
                   InpZPeriod, InpZEntry, InpATRPeriod, InpATRLookback,
                   InpERTrend, InpERRange))
     {
      Print("QuantSage: falha nos indicadores");
      return INIT_FAILED;
     }

   EventSetTimer(1); // status mesmo sem ticks (mercado fechado)
   g_last_detail = "anexado — aguardando";
   RefreshComment();
   PrintFormat("QuantSage v2.01 | %s %s | score_min=%.0f | risk=%.2f%%",
               _Symbol, EnumToString(_Period), InpMinScore, InpRiskPercent);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      Print("ATENCAO: ligue o botao Algo Trading (verde).");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
   g_edge.Release();
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   RefreshComment();
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   g_last_edge = g_edge.Evaluate();
   if(InpTrailATR > 0.0 && g_last_edge.atr > 0.0)
      g_exec.Trail(_Symbol, g_last_edge.atr, InpTrailATR);

   if(!g_session.InSession())
     {
      g_last_detail = "mercado/sessao fechada — EA vivo (use Ctrl+R p/ backtest)";
      RefreshComment();
      return;
     }

   if(!g_session.AllowNewEntries())
     {
      g_last_detail = "sessao OK mas bloqueio de novas entradas (fim do pregão)";
      RefreshComment();
      return;
     }

   if(InpOnlyNewBar && !IsNewBar())
     {
      g_last_detail = "aguardando nova barra";
      RefreshComment();
      return;
     }

   TryEnter(g_last_edge);
   RefreshComment();
  }

//+------------------------------------------------------------------+
void TryEnter(const QSEdge &e)
  {
   if(e.signal == QS_SIGNAL_NONE)
     {
      g_last_detail = "sem sinal | " + e.reason;
      return;
     }
   if(e.score < InpMinScore)
     {
      g_last_detail = StringFormat("sinal fraco score=%.0f < %.0f | %s",
                                   e.score, InpMinScore, e.reason);
      return;
     }
   if(e.atr <= 0.0)
     {
      g_last_detail = "ATR invalido";
      return;
     }
   if(!g_risk.SpreadOK(_Symbol, e.atr))
     {
      g_last_detail = "spread caro vs ATR — nao entra";
      return;
     }

   string why;
   if(!g_risk.CanOpen(_Symbol, g_exec.Magic(), why))
     {
      g_last_detail = "risco bloqueou: " + why;
      return;
     }

   double sl = e.atr * InpSL_ATR;
   double tp = e.atr * InpTP_ATR;
   double lots = g_risk.LotSize(_Symbol, sl, e.score, e.atr_pct);
   if(lots <= 0.0)
     {
      g_last_detail = "lote=0 — confira tick value (SymbolDiagnostics)";
      return;
     }

   bool ok = false;
   if(e.signal == QS_SIGNAL_BUY)
      ok = g_exec.Buy(_Symbol, lots, sl, tp);
   else if(e.signal == QS_SIGNAL_SELL)
      ok = g_exec.Sell(_Symbol, lots, sl, tp);

   g_last_detail = ok
                   ? StringFormat("ENTRADA %s lote=%.2f score=%.0f | %s",
                                  (e.signal == QS_SIGNAL_BUY ? "BUY" : "SELL"),
                                  lots, e.score, e.reason)
                   : "falha ao enviar ordem (conta/login/mercado?)";
  }

//+------------------------------------------------------------------+
void RefreshComment()
  {
   string algo = TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "AlgoTrading ON" : "AlgoTrading OFF";
   string conn = TerminalInfoInteger(TERMINAL_CONNECTED) ? "conectado" : "DESCONECTADO";
   string reg = "CHAOS";
   if(g_last_edge.regime == QS_REGIME_TREND) reg = "TREND";
   if(g_last_edge.regime == QS_REGIME_RANGE) reg = "RANGE";

   Comment(
      "======== QuantSage v2.01 ========\n",
      _Symbol, " | ", EnumToString(_Period), " | ", conn, "\n",
      algo, " | ", g_session.Text(), "\n",
      "Regime: ", reg,
      " | ER=", DoubleToString(g_last_edge.er, 2),
      " | z=", DoubleToString(g_last_edge.z, 2), "\n",
      "Score=", DoubleToString(g_last_edge.score, 0),
      " (min ", DoubleToString(InpMinScore, 0), ")",
      " | ATR%=", DoubleToString(g_last_edge.atr_pct * 100.0, 0), "%\n",
      "Loss streak: ", IntegerToString(g_risk.LossStreak()), "\n",
      g_last_detail, "\n",
      "Hora servidor: ", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), "\n",
      "==============================="
   );
  }

//+------------------------------------------------------------------+
bool IsNewBar()
  {
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == 0 || t == g_last_bar)
      return false;
   g_last_bar = t;
   return true;
  }

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if((ulong)HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagic)
      return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol)
      return;
   long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
      return;
   double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                   + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
                   + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
   g_risk.OnDealClosed(profit);
  }
//+------------------------------------------------------------------+
