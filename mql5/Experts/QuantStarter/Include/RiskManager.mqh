//+------------------------------------------------------------------+
//| RiskManager.mqh                                                  |
//| Gestão de risco: tamanho de posição, stops e limites diários     |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property strict

#ifndef RISK_MANAGER_MQH
#define RISK_MANAGER_MQH

class CRiskManager
  {
private:
   double            m_risk_percent;      // % do equity por trade
   double            m_max_daily_loss;    // % máximo de perda no dia
   int               m_max_positions;     // posições abertas simultâneas
   double            m_day_start_equity;
   int               m_day_stamp;         // YYYYMMDD do início do dia

   int               DayStamp()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.year * 10000 + dt.mon * 100 + dt.day;
     }

   void              ResetDayIfNeeded()
     {
      int stamp = DayStamp();
      if(stamp != m_day_stamp)
        {
         m_day_stamp = stamp;
         m_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
        }
     }

public:
                     CRiskManager(void)
     {
      m_risk_percent   = 1.0;
      m_max_daily_loss = 3.0;
      m_max_positions  = 1;
      m_day_start_equity = 0.0;
      m_day_stamp = 0;
     }

   void              Configure(const double risk_percent,
                               const double max_daily_loss,
                               const int max_positions)
     {
      m_risk_percent   = MathMax(0.01, risk_percent);
      m_max_daily_loss = MathMax(0.1, max_daily_loss);
      m_max_positions  = MathMax(1, max_positions);
     }

   bool              CanOpenTrade(const string symbol, const ulong magic)
     {
      ResetDayIfNeeded();

      if(m_day_start_equity > 0.0)
        {
         double equity = AccountInfoDouble(ACCOUNT_EQUITY);
         double dd = 100.0 * (m_day_start_equity - equity) / m_day_start_equity;
         if(dd >= m_max_daily_loss)
           {
            PrintFormat("[Risk] Limite diário atingido: %.2f%% >= %.2f%%",
                        dd, m_max_daily_loss);
            return false;
           }
        }

      int open_count = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != symbol)
            continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC) != magic)
            continue;
         open_count++;
        }

      if(open_count >= m_max_positions)
        {
         PrintFormat("[Risk] Máximo de posições (%d) já aberto", m_max_positions);
         return false;
        }
      return true;
     }

   // volume em lotes a partir do risco e distância do stop (em preço)
   double            LotSize(const string symbol,
                             const double stop_distance_price)
     {
      if(stop_distance_price <= 0.0)
         return 0.0;

      double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
      double risk_money = equity * (m_risk_percent / 100.0);

      double tick_size  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
      double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
      double lot_step   = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
      double vol_min    = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
      double vol_max    = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);

      if(tick_size <= 0.0 || tick_value <= 0.0 || lot_step <= 0.0)
         return 0.0;

      double loss_per_lot = (stop_distance_price / tick_size) * tick_value;
      if(loss_per_lot <= 0.0)
         return 0.0;

      double lots = risk_money / loss_per_lot;
      lots = MathFloor(lots / lot_step) * lot_step;
      lots = MathMax(vol_min, MathMin(vol_max, lots));
      return lots;
     }

   double            StopDistanceByATR(const string symbol,
                                       const ENUM_TIMEFRAMES tf,
                                       const int atr_period,
                                       const double atr_mult)
     {
      int handle = iATR(symbol, tf, atr_period);
      if(handle == INVALID_HANDLE)
         return 0.0;

      double atr[];
      ArraySetAsSeries(atr, true);
      if(CopyBuffer(handle, 0, 1, 1, atr) < 1)
        {
         IndicatorRelease(handle);
         return 0.0;
        }
      IndicatorRelease(handle);
      return atr[0] * atr_mult;
     }
  };

#endif
//+------------------------------------------------------------------+
