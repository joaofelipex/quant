//+------------------------------------------------------------------+
//| TradeManager.mqh                                                 |
//| Execução de ordens com SL/TP baseados em ATR                     |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property strict

#ifndef TRADE_MANAGER_MQH
#define TRADE_MANAGER_MQH

#include <Trade\Trade.mqh>

class CTradeManager
  {
private:
   CTrade            m_trade;
   ulong             m_magic;
   int               m_deviation;
   string            m_comment;

public:
                     CTradeManager(void)
     {
      m_magic = 20260803;
      m_deviation = 20;
      m_comment = "QuantStarter";
     }

   void              Configure(const ulong magic,
                               const int deviation,
                               const string comment)
     {
      m_magic = magic;
      m_deviation = deviation;
      m_comment = comment;
      m_trade.SetExpertMagicNumber(m_magic);
      m_trade.SetDeviationInPoints(m_deviation);
      m_trade.SetTypeFillingBySymbol(_Symbol);
     }

   ulong             Magic(void) const { return m_magic; }

   bool              OpenBuy(const string symbol,
                             const double lots,
                             const double sl_distance,
                             const double tp_distance)
     {
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      double sl  = (sl_distance > 0.0) ? ask - sl_distance : 0.0;
      double tp  = (tp_distance > 0.0) ? ask + tp_distance : 0.0;
      NormalizeStops(symbol, ORDER_TYPE_BUY, ask, sl, tp);

      bool ok = m_trade.Buy(lots, symbol, ask, sl, tp, m_comment);
      if(!ok)
         PrintFormat("[Trade] BUY falhou: %s", m_trade.ResultRetcodeDescription());
      return ok;
     }

   bool              OpenSell(const string symbol,
                              const double lots,
                              const double sl_distance,
                              const double tp_distance)
     {
      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double sl  = (sl_distance > 0.0) ? bid + sl_distance : 0.0;
      double tp  = (tp_distance > 0.0) ? bid - tp_distance : 0.0;
      NormalizeStops(symbol, ORDER_TYPE_SELL, bid, sl, tp);

      bool ok = m_trade.Sell(lots, symbol, bid, sl, tp, m_comment);
      if(!ok)
         PrintFormat("[Trade] SELL falhou: %s", m_trade.ResultRetcodeDescription());
      return ok;
     }

   bool              CloseAll(const string symbol)
     {
      bool all_ok = true;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != symbol)
            continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC) != m_magic)
            continue;
         if(!m_trade.PositionClose(ticket))
           {
            all_ok = false;
            PrintFormat("[Trade] Close #%d falhou: %s",
                        ticket, m_trade.ResultRetcodeDescription());
           }
        }
      return all_ok;
     }

private:
   void              NormalizeStops(const string symbol,
                                    const ENUM_ORDER_TYPE type,
                                    const double price,
                                    double &sl,
                                    double &tp)
     {
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      int stops_level = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      double min_dist = stops_level * point;

      if(sl > 0.0)
        {
         if(type == ORDER_TYPE_BUY && (price - sl) < min_dist)
            sl = price - min_dist;
         if(type == ORDER_TYPE_SELL && (sl - price) < min_dist)
            sl = price + min_dist;
         sl = NormalizeDouble(sl, digits);
        }
      if(tp > 0.0)
        {
         if(type == ORDER_TYPE_BUY && (tp - price) < min_dist)
            tp = price + min_dist;
         if(type == ORDER_TYPE_SELL && (price - tp) < min_dist)
            tp = price - min_dist;
         tp = NormalizeDouble(tp, digits);
        }
     }
  };

#endif
//+------------------------------------------------------------------+
