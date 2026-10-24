//+------------------------------------------------------------------+
//| ExecEngine.mqh — execução + trailing ATR                         |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#ifndef EXEC_ENGINE_MQH
#define EXEC_ENGINE_MQH

#include <Trade\Trade.mqh>

class CExecEngine
  {
private:
   CTrade m_trade;
   ulong  m_magic;
   int    m_slip;
   string m_cmt;

   void NormStops(const string symbol, const ENUM_ORDER_TYPE type,
                  const double price, double &sl, double &tp)
     {
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      double min_dist = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL) * point;
      if(sl > 0.0)
        {
         if(type == ORDER_TYPE_BUY && price - sl < min_dist) sl = price - min_dist;
         if(type == ORDER_TYPE_SELL && sl - price < min_dist) sl = price + min_dist;
         sl = NormalizeDouble(sl, digits);
        }
      if(tp > 0.0)
        {
         if(type == ORDER_TYPE_BUY && tp - price < min_dist) tp = price + min_dist;
         if(type == ORDER_TYPE_SELL && price - tp < min_dist) tp = price - min_dist;
         tp = NormalizeDouble(tp, digits);
        }
     }

public:
   void Configure(const ulong magic, const int slip, const string cmt)
     {
      m_magic = magic;
      m_slip = slip;
      m_cmt = cmt;
      m_trade.SetExpertMagicNumber(magic);
      m_trade.SetDeviationInPoints(slip);
      m_trade.SetTypeFillingBySymbol(_Symbol);
     }

   ulong Magic() const { return m_magic; }

   bool Buy(const string symbol, const double lots, const double sl_d, const double tp_d)
     {
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      double sl = ask - sl_d, tp = ask + tp_d;
      NormStops(symbol, ORDER_TYPE_BUY, ask, sl, tp);
      bool ok = m_trade.Buy(lots, symbol, ask, sl, tp, m_cmt);
      if(!ok) Print("[Exec] BUY: ", m_trade.ResultRetcodeDescription());
      return ok;
     }

   bool Sell(const string symbol, const double lots, const double sl_d, const double tp_d)
     {
      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double sl = bid + sl_d, tp = bid - tp_d;
      NormStops(symbol, ORDER_TYPE_SELL, bid, sl, tp);
      bool ok = m_trade.Sell(lots, symbol, bid, sl, tp, m_cmt);
      if(!ok) Print("[Exec] SELL: ", m_trade.ResultRetcodeDescription());
      return ok;
     }

   void Trail(const string symbol, const double atr, const double trail_atr_mult)
     {
      if(atr <= 0.0 || trail_atr_mult <= 0.0)
         return;
      double trail = atr * trail_atr_mult;
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong t = PositionGetTicket(i);
         if(t == 0 || !PositionSelectByTicket(t))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != symbol)
            continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC) != m_magic)
            continue;

         long type = PositionGetInteger(POSITION_TYPE);
         double sl = PositionGetDouble(POSITION_SL);
         double tp = PositionGetDouble(POSITION_TP);
         double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
         double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

         if(type == POSITION_TYPE_BUY)
           {
            double nsl = NormalizeDouble(bid - trail, digits);
            if(nsl > sl && nsl < bid)
               m_trade.PositionModify(t, nsl, tp);
           }
         else if(type == POSITION_TYPE_SELL)
           {
            double nsl = NormalizeDouble(ask + trail, digits);
            if((sl == 0.0 || nsl < sl) && nsl > ask)
               m_trade.PositionModify(t, nsl, tp);
           }
        }
     }
  };

#endif
