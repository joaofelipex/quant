//+------------------------------------------------------------------+
//| MeanReversion.mqh                                                |
//| Sinal mean reversion: Bollinger + RSI (barra fechada)            |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property strict

#ifndef MEAN_REVERSION_MQH
#define MEAN_REVERSION_MQH

#include "SignalEngine.mqh"   // ENUM_TRADE_SIGNAL

class CMeanReversion
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   int               m_bb_period;
   double            m_bb_dev;
   int               m_rsi_period;
   double            m_rsi_os;     // oversold
   double            m_rsi_ob;     // overbought
   int               m_h_bb;
   int               m_h_rsi;
   int               m_h_atr;

public:
                     CMeanReversion(void)
     {
      m_symbol = "";
      m_tf = PERIOD_CURRENT;
      m_bb_period = 20;
      m_bb_dev = 2.0;
      m_rsi_period = 14;
      m_rsi_os = 30.0;
      m_rsi_ob = 70.0;
      m_h_bb = INVALID_HANDLE;
      m_h_rsi = INVALID_HANDLE;
      m_h_atr = INVALID_HANDLE;
     }

                    ~CMeanReversion(void) { Release(); }

   bool              Init(const string symbol,
                          const ENUM_TIMEFRAMES tf,
                          const int bb_period,
                          const double bb_dev,
                          const int rsi_period,
                          const double rsi_os,
                          const double rsi_ob,
                          const int atr_period)
     {
      Release();
      m_symbol = symbol;
      m_tf = tf;
      m_bb_period = bb_period;
      m_bb_dev = bb_dev;
      m_rsi_period = rsi_period;
      m_rsi_os = rsi_os;
      m_rsi_ob = rsi_ob;

      m_h_bb  = iBands(m_symbol, m_tf, m_bb_period, 0, m_bb_dev, PRICE_CLOSE);
      m_h_rsi = iRSI(m_symbol, m_tf, m_rsi_period, PRICE_CLOSE);
      m_h_atr = iATR(m_symbol, m_tf, atr_period);

      if(m_h_bb == INVALID_HANDLE || m_h_rsi == INVALID_HANDLE ||
         m_h_atr == INVALID_HANDLE)
        {
         Print("[MeanRev] Falha ao criar handles");
         Release();
         return false;
        }
      return true;
     }

   void              Release(void)
     {
      if(m_h_bb  != INVALID_HANDLE) { IndicatorRelease(m_h_bb);  m_h_bb  = INVALID_HANDLE; }
      if(m_h_rsi != INVALID_HANDLE) { IndicatorRelease(m_h_rsi); m_h_rsi = INVALID_HANDLE; }
      if(m_h_atr != INVALID_HANDLE) { IndicatorRelease(m_h_atr); m_h_atr = INVALID_HANDLE; }
     }

   // BUY: close abaixo da banda inferior + RSI oversold
   // SELL: close acima da banda superior + RSI overbought
   ENUM_TRADE_SIGNAL Evaluate(void)
     {
      double upper[], middle[], lower[], rsi[], close[];
      ArraySetAsSeries(upper, true);
      ArraySetAsSeries(middle, true);
      ArraySetAsSeries(lower, true);
      ArraySetAsSeries(rsi, true);
      ArraySetAsSeries(close, true);

      // iBands: 0=BASE, 1=UPPER, 2=LOWER
      if(CopyBuffer(m_h_bb, 1, 1, 1, upper) < 1)
         return SIGNAL_NONE;
      if(CopyBuffer(m_h_bb, 2, 1, 1, lower) < 1)
         return SIGNAL_NONE;
      if(CopyBuffer(m_h_rsi, 0, 1, 1, rsi) < 1)
         return SIGNAL_NONE;
      if(CopyClose(m_symbol, m_tf, 1, 1, close) < 1)
         return SIGNAL_NONE;

      if(close[0] < lower[0] && rsi[0] <= m_rsi_os)
         return SIGNAL_BUY;
      if(close[0] > upper[0] && rsi[0] >= m_rsi_ob)
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
