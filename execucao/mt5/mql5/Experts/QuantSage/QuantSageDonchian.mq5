//+------------------------------------------------------------------+
//| QuantSageDonchian.mq5                                             |
//| EMA + Donchian breakout + regime ER (estrategia validada em      |
//| Python no WIN: PF 1.58 treino / 1.45 out-of-sample).              |
//| Reaproveita sessao/risco/execucao do QuantSage original.          |
//|                                                                    |
//| NAO TESTADO em compilacao MQL5 real - revisar erros no MetaEditor|
//| antes de rodar, mesmo em simulador.                               |
//|                                                                    |
//| Anexe pelo Navegador (NAO pelo debugger F5 do MetaEditor).       |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#property version   "1.00"
#property strict
#property description "QuantSageDonchian: EMA+Donchian+regime ER, risco B3"

#include "Include\SessionB3.mqh"
#include "Include\RiskEngine.mqh"
#include "Include\DonchianEdgeEngine.mqh"
#include "Include\ExecEngine.mqh"

input group "=== Perfil ==="
input ENUM_QS_SESSION   InpSession       = QS_SESSION_FUTURES_DAY;
input int               InpSkipOpenMin   = 10;
input int               InpNoNewBeforeEnd= 20;
input bool              InpSkipFridayLate= true;
input int               InpFridayH       = 16;
input int               InpFridayM       = 30;

input group "=== Estrategia (validada em Python no WIN) ==="
input int               InpEMAFast       = 9;
input int               InpEMASlow       = 21;
input int               InpDonchianPeriod= 20;
input int               InpATRPeriod     = 14;
input int               InpERPeriod      = 20;
input double            InpERThreshold   = 0.5;
input double            InpSL_ATR        = 1.5;
input double            InpTP_ATR        = 3.0;    // 1.5 * risco:retorno 2.0
input bool              InpOnlyNewBar    = true;

input group "=== Risco ==="
input double            InpRiskPercent   = 0.5;
input double            InpMaxDailyLoss  = 2.0;
input double            InpMaxSpreadATR  = 0.15;
input int               InpMaxPositions  = 1;
input int               InpMaxLossStreak = 3;

input group "=== Execucao ==="
input ulong             InpMagic         = 26080403;
input int               InpDeviation     = 30;

CSessionB3          g_session;
CRiskEngine         g_risk;
CDonchianEdgeEngine g_edge;
CExecEngine         g_exec;
datetime            g_last_bar = 0;
string              g_last_detail = "boot";
QSDonchianEdge      g_last_edge;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_session.Configure(InpSession, InpSkipOpenMin, InpNoNewBeforeEnd,
                       InpSkipFridayLate, InpFridayH, InpFridayM);
   g_risk.Configure(InpRiskPercent, InpMaxDailyLoss, InpMaxSpreadATR,
                    InpMaxPositions, InpMaxLossStreak);
   g_exec.Configure(InpMagic, InpDeviation, "QuantSageDonchian");

   if(!g_edge.Init(_Symbol, _Period, InpEMAFast, InpEMASlow, InpDonchianPeriod,
                   InpATRPeriod, InpERPeriod, InpERThreshold))
     {
      Print("QuantSageDonchian: falha nos indicadores");
      return INIT_FAILED;
     }

   EventSetTimer(1);
   g_last_detail = "anexado — aguardando";
   RefreshComment();
   PrintFormat("QuantSageDonchian v1.00 | %s %s | ER>=%.2f | risk=%.2f%%",
               _Symbol, EnumToString(_Period), InpERThreshold, InpRiskPercent);
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

   if(!g_session.InSession())
     {
      g_last_detail = "mercado/sessao fechada — EA vivo (use Ctrl+R p/ backtest)";
      RefreshComment();
      return;
     }

   if(!g_session.AllowNewEntries())
     {
      g_last_detail = "sessao OK mas bloqueio de novas entradas (fim do pregao)";
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
void TryEnter(const QSDonchianEdge &e)
  {
   if(e.signal == QSD_SIGNAL_NONE)
     {
      g_last_detail = "sem sinal | " + e.reason;
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
   // score fixo 100: essa estrategia e binaria (rompe ou nao), sem gradiente de confluencia
   double lots = g_risk.LotSize(_Symbol, sl, 100.0, 0.5);
   if(lots <= 0.0)
     {
      g_last_detail = "lote=0 — confira tick value (SymbolDiagnostics)";
      return;
     }

   bool ok = false;
   if(e.signal == QSD_SIGNAL_BUY)
      ok = g_exec.Buy(_Symbol, lots, sl, tp);
   else if(e.signal == QSD_SIGNAL_SELL)
      ok = g_exec.Sell(_Symbol, lots, sl, tp);

   g_last_detail = ok
                   ? StringFormat("ENTRADA %s lote=%.2f | %s",
                                  (e.signal == QSD_SIGNAL_BUY ? "BUY" : "SELL"),
                                  lots, e.reason)
                   : "falha ao enviar ordem (conta/login/mercado?)";
  }

//+------------------------------------------------------------------+
void RefreshComment()
  {
   string algo = TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "AlgoTrading ON" : "AlgoTrading OFF";
   string conn = TerminalInfoInteger(TERMINAL_CONNECTED) ? "conectado" : "DESCONECTADO";

   Comment(
      "======== QuantSageDonchian v1.00 ========\n",
      _Symbol, " | ", EnumToString(_Period), " | ", conn, "\n",
      algo, " | ", g_session.Text(), "\n",
      "ER=", DoubleToString(g_last_edge.er, 2),
      " (limiar ", DoubleToString(InpERThreshold, 2), ")\n",
      "Loss streak: ", IntegerToString(g_risk.LossStreak()), "\n",
      g_last_detail, "\n",
      "Hora servidor: ", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), "\n",
      "==========================================="
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
