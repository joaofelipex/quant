//+------------------------------------------------------------------+
//| MathStats.mqh — utilitários estatísticos (barra fechada)         |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#ifndef MATH_STATS_MQH
#define MATH_STATS_MQH

// Kaufman Efficiency Ratio: 0 = ruído puro, 1 = movimento direcional
double MathEfficiencyRatio(const string symbol, const ENUM_TIMEFRAMES tf, const int period)
  {
   if(period < 2)
      return 0.0;
   double close[];
   ArraySetAsSeries(close, true);
   if(CopyClose(symbol, tf, 1, period + 1, close) < period + 1)
      return 0.0;

   double change = MathAbs(close[0] - close[period]);
   double path = 0.0;
   for(int i = 0; i < period; i++)
      path += MathAbs(close[i] - close[i + 1]);
   if(path <= 0.0)
      return 0.0;
   return change / path;
  }

double MathSMA(const double &arr[], const int count)
  {
   if(count <= 0)
      return 0.0;
   double s = 0.0;
   for(int i = 0; i < count; i++)
      s += arr[i];
   return s / count;
  }

double MathStdev(const double &arr[], const int count, const double mean)
  {
   if(count < 2)
      return 0.0;
   double v = 0.0;
   for(int i = 0; i < count; i++)
     {
      double d = arr[i] - mean;
      v += d * d;
     }
   return MathSqrt(v / (count - 1));
  }

// z-score do close fechado vs média/desvio dos closes ANTERIORES (sem autoinclusão)
bool MathCloseZScore(const string symbol, const ENUM_TIMEFRAMES tf,
                     const int period, double &z_out)
  {
   z_out = 0.0;
   if(period < 5)
      return false;
   double close[];
   ArraySetAsSeries(close, true);
   // close[0]=barra fechada atual; close[1..period]=histórico para mean/sd
   if(CopyClose(symbol, tf, 1, period + 1, close) < period + 1)
      return false;
   double hist[];
   ArrayResize(hist, period);
   for(int i = 0; i < period; i++)
      hist[i] = close[i + 1];
   double mean = MathSMA(hist, period);
   double sd = MathStdev(hist, period, mean);
   if(sd <= 0.0)
      return false;
   z_out = (close[0] - mean) / sd;
   return true;
  }

// percentil do ATR atual vs histórico recente (0..1)
bool MathATRPercentile(const int atr_handle, const int lookback, double &pct_out)
  {
   pct_out = 0.5;
   if(atr_handle == INVALID_HANDLE || lookback < 5)
      return false;
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(atr_handle, 0, 1, lookback, atr) < lookback)
      return false;
   double cur = atr[0];
   int below = 0;
   for(int i = 0; i < lookback; i++)
      if(atr[i] <= cur)
         below++;
   pct_out = (double)below / (double)lookback;
   return true;
  }

#endif
