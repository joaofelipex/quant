//+------------------------------------------------------------------+
//| SignalEngine.mqh                                                 |
//| Sinais: momentum EMA + filtro de volatilidade (ATR)              |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property strict

#ifndef SIGNAL_ENGINE_MQH
#define SIGNAL_ENGINE_MQH

enum ENUM_TRADE_SIGNAL
  {
   SIGNAL_NONE = 0,
   SIGNAL_BUY  = 1,
   SIGNAL_SELL = -1
  };

class CSignalEngine
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   int               m_fast_ema;
   int               m_slow_ema;
   int               m_atr_period;
   double            m_min_atr_points;   // evita operar em mercado morto
   int               m_h_fast;
   int               m_h_slow;
   int               m_h_atr;

public:
                     CSignalEngine(void)
     {
      m_symbol = "";
      m_tf = PERIOD_CURRENT;
      m_fast_ema = 12;
      m_slow_ema = 26;
      m_atr_period = 14;
      m_min_atr_points = 0.0;
      m_h_fast = INVALID_HANDLE;
      m_h_slow = INVALID_HANDLE;
      m_h_atr  = INVALID_HANDLE;
     }

                    ~CSignalEngine(void)
     {
      Release();
     }

   bool              Init(const string symbol,
                          const ENUM_TIMEFRAMES tf,
                          const int fast_ema,
                          const int slow_ema,
                          const int atr_period,
                          const double min_atr_points)
     {
      Release();
      m_symbol = symbol;
      m_tf = tf;
      m_fast_ema = fast_ema;
      m_slow_ema = slow_ema;
      m_atr_period = atr_period;
      m_min_atr_points = min_atr_points;

      m_h_fast = iMA(m_symbol, m_tf, m_fast_ema, 0, MODE_EMA, PRICE_CLOSE);
      m_h_slow = iMA(m_symbol, m_tf, m_slow_ema, 0, MODE_EMA, PRICE_CLOSE);
      m_h_atr  = iATR(m_symbol, m_tf, m_atr_period);

      if(m_h_fast == INVALID_HANDLE || m_h_slow == INVALID_HANDLE ||
         m_h_atr == INVALID_HANDLE)
        {
         Print("[Signal] Falha ao criar handles de indicadores");
         Release();
         return false;
        }
      return true;
     }

   void              Release(void)
     {
      if(m_h_fast != INVALID_HANDLE) { IndicatorRelease(m_h_fast); m_h_fast = INVALID_HANDLE; }
      if(m_h_slow != INVALID_HANDLE) { IndicatorRelease(m_h_slow); m_h_slow = INVALID_HANDLE; }
      if(m_h_atr  != INVALID_HANDLE) { IndicatorRelease(m_h_atr);  m_h_atr  = INVALID_HANDLE; }
     }

   // usa barra fechada (shift=1) para evitar repaint em live/backtest
   ENUM_TRADE_SIGNAL Evaluate(void)
     {
      double fast[], slow[], atr[];
      ArraySetAsSeries(fast, true);
      ArraySetAsSeries(slow, true);
      ArraySetAsSeries(atr, true);

      if(CopyBuffer(m_h_fast, 0, 1, 3, fast) < 3)
         return SIGNAL_NONE;
      if(CopyBuffer(m_h_slow, 0, 1, 3, slow) < 3)
         return SIGNAL_NONE;
      if(CopyBuffer(m_h_atr, 0, 1, 1, atr) < 1)
         return SIGNAL_NONE;

      double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      if(point <= 0.0)
         return SIGNAL_NONE;

      double atr_points = atr[0] / point;
      if(atr_points < m_min_atr_points)
         return SIGNAL_NONE;   // volatilidade insuficiente

      // cruzamento na barra que acabou de fechar
      bool cross_up   = (fast[1] <= slow[1] && fast[0] > slow[0]);
      bool cross_down = (fast[1] >= slow[1] && fast[0] < slow[0]);

      if(cross_up)
         return SIGNAL_BUY;
      if(cross_down)
         return SIGNAL_SELL;
      return SIGNAL_NONE;
     }

   double            LastATR(void)
     {
      double atr[];
      ArraySetAsSeries(atr, true);
      if(CopyBuffer(m_h_atr, 0, 1, 1, atr) < 1)
         return 0.0;
      return atr[0];
     }
  };

#endif
//+------------------------------------------------------------------+
