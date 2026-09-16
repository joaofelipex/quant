//+------------------------------------------------------------------+
//| DonchianEdgeEngine.mqh                                            |
//| EMA trend filter + Donchian breakout + regime ER                  |
//| Estrategia validada em Python (WIN): PF 1.58 treino / 1.45 teste  |
//| NAO TESTADO em compilacao MQL5 real ainda - revisar antes de usar |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#ifndef DONCHIAN_EDGE_ENGINE_MQH
#define DONCHIAN_EDGE_ENGINE_MQH

#include "MathStats.mqh"

enum ENUM_QSD_SIGNAL
  {
   QSD_SIGNAL_NONE = 0,
   QSD_SIGNAL_BUY  = 1,
   QSD_SIGNAL_SELL = -1
  };

struct QSDonchianEdge
  {
   ENUM_QSD_SIGNAL signal;
   double          atr;
   double          er;
   string          reason;
  };

class CDonchianEdgeEngine
  {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   int             m_ema_fast;
   int             m_ema_slow;
   int             m_donchian_period;
   int             m_atr_period;
   int             m_er_period;
   double          m_er_threshold;
   int             m_h_fast;
   int             m_h_slow;
   int             m_h_atr;

public:
   CDonchianEdgeEngine(): m_h_fast(INVALID_HANDLE), m_h_slow(INVALID_HANDLE),
                          m_h_atr(INVALID_HANDLE) {}
   ~CDonchianEdgeEngine() { Release(); }

   bool Init(const string symbol, const ENUM_TIMEFRAMES tf,
             const int ema_fast, const int ema_slow, const int donchian_period,
             const int atr_period, const int er_period, const double er_threshold)
     {
      Release();
      m_symbol = symbol;
      m_tf = tf;
      m_ema_fast = ema_fast;
      m_ema_slow = ema_slow;
      m_donchian_period = donchian_period;
      m_atr_period = atr_period;
      m_er_period = er_period;
      m_er_threshold = er_threshold;

      m_h_fast = iMA(symbol, tf, ema_fast, 0, MODE_EMA, PRICE_CLOSE);
      m_h_slow = iMA(symbol, tf, ema_slow, 0, MODE_EMA, PRICE_CLOSE);
      m_h_atr  = iATR(symbol, tf, atr_period);
      if(m_h_fast == INVALID_HANDLE || m_h_slow == INVALID_HANDLE || m_h_atr == INVALID_HANDLE)
        {
         Release();
         return false;
        }
      return true;
     }

   void Release()
     {
      if(m_h_fast != INVALID_HANDLE) { IndicatorRelease(m_h_fast); m_h_fast = INVALID_HANDLE; }
      if(m_h_slow != INVALID_HANDLE) { IndicatorRelease(m_h_slow); m_h_slow = INVALID_HANDLE; }
      if(m_h_atr  != INVALID_HANDLE) { IndicatorRelease(m_h_atr);  m_h_atr  = INVALID_HANDLE; }
     }

   QSDonchianEdge Evaluate()
     {
      QSDonchianEdge e;
      e.signal = QSD_SIGNAL_NONE;
      e.atr = 0.0;
      e.er = 0.0;
      e.reason = "sem dados";

      double fast[], slow[], atr[];
      ArraySetAsSeries(fast, true);
      ArraySetAsSeries(slow, true);
      ArraySetAsSeries(atr, true);
      if(CopyBuffer(m_h_fast, 0, 1, 1, fast) < 1) return e;
      if(CopyBuffer(m_h_slow, 0, 1, 1, slow) < 1) return e;
      if(CopyBuffer(m_h_atr, 0, 1, 1, atr) < 1) return e;

      e.atr = atr[0];
      e.er = MathEfficiencyRatio(m_symbol, m_tf, m_er_period);

      if(e.er < m_er_threshold)
        {
         e.reason = StringFormat("regime fraco ER=%.2f < %.2f", e.er, m_er_threshold);
         return e;
        }

      // Canal Donchian com as N barras ANTERIORES a barra fechada atual
      // (shift comeca em 2 pra nao incluir a propria barra de sinal, evitando look-ahead)
      double high[], low[], close[];
      ArraySetAsSeries(high, true);
      ArraySetAsSeries(low, true);
      ArraySetAsSeries(close, true);
      if(CopyHigh(m_symbol, m_tf, 2, m_donchian_period, high) < m_donchian_period) return e;
      if(CopyLow(m_symbol, m_tf, 2, m_donchian_period, low) < m_donchian_period) return e;
      if(CopyClose(m_symbol, m_tf, 1, 1, close) < 1) return e;

      double canal_sup = high[ArrayMaximum(high)];
      double canal_inf = low[ArrayMinimum(low)];

      bool trend_up = fast[0] > slow[0];
      bool trend_dn = fast[0] < slow[0];

      if(trend_up && close[0] > canal_sup)
        {
         e.signal = QSD_SIGNAL_BUY;
         e.reason = StringFormat("BUY rompimento %.2f (ER=%.2f)", canal_sup, e.er);
        }
      else if(trend_dn && close[0] < canal_inf)
        {
         e.signal = QSD_SIGNAL_SELL;
         e.reason = StringFormat("SELL rompimento %.2f (ER=%.2f)", canal_inf, e.er);
        }
      else
        {
         e.reason = StringFormat("sem rompimento (ER=%.2f)", e.er);
        }

      return e;
     }
  };

#endif
