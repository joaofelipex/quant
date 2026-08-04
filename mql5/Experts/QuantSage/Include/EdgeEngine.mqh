//+------------------------------------------------------------------+
//| EdgeEngine.mqh — regime + confluência + score de edge            |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#ifndef EDGE_ENGINE_MQH
#define EDGE_ENGINE_MQH

#include "MathStats.mqh"

enum ENUM_QS_REGIME
  {
   QS_REGIME_TREND = 1,
   QS_REGIME_RANGE = 2,
   QS_REGIME_CHAOS = 0
  };

enum ENUM_QS_SIGNAL
  {
   QS_SIGNAL_NONE = 0,
   QS_SIGNAL_BUY = 1,
   QS_SIGNAL_SELL = -1
  };

struct QSEdge
  {
   ENUM_QS_SIGNAL signal;
   ENUM_QS_REGIME regime;
   double         score;      // 0..100
   double         atr;
   double         atr_pct;
   double         er;
   double         z;
   string         reason;
  };

class CEdgeEngine
  {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   int             m_er_period;
   int             m_ema_fast;
   int             m_ema_slow;
   int             m_z_period;
   double          m_z_entry;
   int             m_atr_period;
   int             m_atr_lb;
   double          m_er_trend;
   double          m_er_range;
   int             m_h_fast;
   int             m_h_slow;
   int             m_h_atr;
   int             m_h_rsi;

public:
   CEdgeEngine(): m_h_fast(INVALID_HANDLE), m_h_slow(INVALID_HANDLE),
                  m_h_atr(INVALID_HANDLE), m_h_rsi(INVALID_HANDLE) {}

   ~CEdgeEngine() { Release(); }

   bool Init(const string symbol, const ENUM_TIMEFRAMES tf,
             const int er_period, const int ema_fast, const int ema_slow,
             const int z_period, const double z_entry,
             const int atr_period, const int atr_lb,
             const double er_trend, const double er_range)
     {
      Release();
      m_symbol = symbol;
      m_tf = tf;
      m_er_period = er_period;
      m_ema_fast = ema_fast;
      m_ema_slow = ema_slow;
      m_z_period = z_period;
      m_z_entry = z_entry;
      m_atr_period = atr_period;
      m_atr_lb = atr_lb;
      m_er_trend = er_trend;
      m_er_range = er_range;

      m_h_fast = iMA(symbol, tf, ema_fast, 0, MODE_EMA, PRICE_CLOSE);
      m_h_slow = iMA(symbol, tf, ema_slow, 0, MODE_EMA, PRICE_CLOSE);
      m_h_atr  = iATR(symbol, tf, atr_period);
      m_h_rsi  = iRSI(symbol, tf, 14, PRICE_CLOSE);
      if(m_h_fast == INVALID_HANDLE || m_h_slow == INVALID_HANDLE ||
         m_h_atr == INVALID_HANDLE || m_h_rsi == INVALID_HANDLE)
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
      if(m_h_rsi  != INVALID_HANDLE) { IndicatorRelease(m_h_rsi);  m_h_rsi  = INVALID_HANDLE; }
     }

   QSEdge Evaluate()
     {
      QSEdge e;
      e.signal = QS_SIGNAL_NONE;
      e.regime = QS_REGIME_CHAOS;
      e.score = 0;
      e.atr = 0;
      e.atr_pct = 0.5;
      e.er = 0;
      e.z = 0;
      e.reason = "sem dados";

      double fast[], slow[], atr[], rsi[];
      ArraySetAsSeries(fast, true);
      ArraySetAsSeries(slow, true);
      ArraySetAsSeries(atr, true);
      ArraySetAsSeries(rsi, true);

      if(CopyBuffer(m_h_fast, 0, 1, 3, fast) < 3)
         return e;
      if(CopyBuffer(m_h_slow, 0, 1, 3, slow) < 3)
         return e;
      if(CopyBuffer(m_h_atr, 0, 1, 1, atr) < 1)
         return e;
      if(CopyBuffer(m_h_rsi, 0, 1, 2, rsi) < 2)
         return e;

      e.atr = atr[0];
      e.er = MathEfficiencyRatio(m_symbol, m_tf, m_er_period);
      MathATRPercentile(m_h_atr, m_atr_lb, e.atr_pct);
      MathCloseZScore(m_symbol, m_tf, m_z_period, e.z);

      // --- Regime ---
      if(e.er >= m_er_trend)
         e.regime = QS_REGIME_TREND;
      else if(e.er <= m_er_range)
         e.regime = QS_REGIME_RANGE;
      else
        {
         e.regime = QS_REGIME_CHAOS;
         e.reason = StringFormat("caos ER=%.2f (nao opera)", e.er);
         e.score = 20;
         return e;
        }

      // volatilidade extrema = cautela (não bloqueia, mas score baixo)
      bool vol_spike = (e.atr_pct >= 0.92);

      double score = 0.0;
      string why = "";

      if(e.regime == QS_REGIME_TREND)
        {
         // tendência: alinhamento EMA + pullback (cruzamento recente ou preço reteste)
         bool bull = (fast[0] > slow[0]);
         bool bear = (fast[0] < slow[0]);
         bool cross_up = (fast[1] <= slow[1] && fast[0] > slow[0]);
         bool cross_dn = (fast[1] >= slow[1] && fast[0] < slow[0]);

         score += 25; // regime claro
         score += 20 * MathMin(1.0, (e.er - m_er_trend) / (1.0 - m_er_trend + 1e-9));

         if(bull && (cross_up || (rsi[0] > 50 && rsi[0] < 70 && rsi[0] >= rsi[1])))
           {
            e.signal = QS_SIGNAL_BUY;
            score += cross_up ? 35 : 25;
            why = cross_up ? "trend BUY cross" : "trend BUY pullback RSI";
           }
         else if(bear && (cross_dn || (rsi[0] < 50 && rsi[0] > 30 && rsi[0] <= rsi[1])))
           {
            e.signal = QS_SIGNAL_SELL;
            score += cross_dn ? 35 : 25;
            why = cross_dn ? "trend SELL cross" : "trend SELL pullback RSI";
           }
         else
           {
            why = "trend sem setup";
            score += 10;
           }
        }
      else // RANGE — mean reversion
        {
         score += 25;
         score += 15 * (1.0 - e.er / (m_er_range + 1e-9));

         if(e.z <= -m_z_entry && rsi[0] < 35)
           {
            e.signal = QS_SIGNAL_BUY;
            score += 30 + MathMin(15.0, (-e.z - m_z_entry) * 5.0);
            why = StringFormat("range BUY z=%.2f RSI=%.1f", e.z, rsi[0]);
           }
         else if(e.z >= m_z_entry && rsi[0] > 65)
           {
            e.signal = QS_SIGNAL_SELL;
            score += 30 + MathMin(15.0, (e.z - m_z_entry) * 5.0);
            why = StringFormat("range SELL z=%.2f RSI=%.1f", e.z, rsi[0]);
           }
         else
           {
            why = StringFormat("range sem extremo z=%.2f", e.z);
            score += 8;
           }
        }

      // custo/vol
      if(!vol_spike)
         score += 10;
      else
        {
         score -= 15;
         why += " | vol spike";
        }

      e.score = MathMax(0.0, MathMin(100.0, score));
      e.reason = why;
      if(e.signal != QS_SIGNAL_NONE && e.score < 55)
        {
         // edge fraco: anula
         e.reason = why + " | score baixo";
         e.signal = QS_SIGNAL_NONE;
        }
      return e;
     }
  };

#endif
