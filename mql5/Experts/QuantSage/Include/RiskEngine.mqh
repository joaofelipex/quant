//+------------------------------------------------------------------+
//| RiskEngine.mqh — sizing vol-aware + circuit breakers             |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#ifndef RISK_ENGINE_MQH
#define RISK_ENGINE_MQH

class CRiskEngine
  {
private:
   double m_risk_pct;
   double m_max_daily_loss;
   double m_max_spread_atr;   // spread / ATR máximo
   int    m_max_positions;
   int    m_loss_streak;
   int    m_max_loss_streak;
   double m_day_start_equity;
   int    m_day_stamp;

   int DayStamp()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.year * 10000 + dt.mon * 100 + dt.day;
     }

   void ResetDay()
     {
      int s = DayStamp();
      if(s != m_day_stamp)
        {
         m_day_stamp = s;
         m_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
         m_loss_streak = 0;
        }
     }

public:
   CRiskEngine(): m_risk_pct(0.5), m_max_daily_loss(2.0), m_max_spread_atr(0.15),
                  m_max_positions(1), m_loss_streak(0), m_max_loss_streak(3),
                  m_day_start_equity(0), m_day_stamp(0) {}

   void Configure(const double risk_pct, const double max_daily_loss,
                  const double max_spread_atr, const int max_positions,
                  const int max_loss_streak)
     {
      m_risk_pct = MathMax(0.05, risk_pct);
      m_max_daily_loss = MathMax(0.2, max_daily_loss);
      m_max_spread_atr = MathMax(0.01, max_spread_atr);
      m_max_positions = MathMax(1, max_positions);
      m_max_loss_streak = MathMax(1, max_loss_streak);
     }

   void OnDealClosed(const double profit)
     {
      if(profit < 0.0)
         m_loss_streak++;
      else if(profit > 0.0)
         m_loss_streak = 0;
     }

   bool SpreadOK(const string symbol, const double atr)
     {
      if(atr <= 0.0)
         return false;
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double spread = ask - bid;
      return (spread / atr) <= m_max_spread_atr;
     }

   bool CanOpen(const string symbol, const ulong magic, string &why)
     {
      ResetDay();
      why = "";

      if(m_loss_streak >= m_max_loss_streak)
        {
         why = "cooldown: muitas perdas seguidas";
         return false;
        }

      if(m_day_start_equity > 0.0)
        {
         double eq = AccountInfoDouble(ACCOUNT_EQUITY);
         double dd = 100.0 * (m_day_start_equity - eq) / m_day_start_equity;
         if(dd >= m_max_daily_loss)
           {
            why = StringFormat("perda diaria %.2f%%", dd);
            return false;
           }
        }

      int n = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong t = PositionGetTicket(i);
         if(t == 0 || !PositionSelectByTicket(t))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != symbol)
            continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC) != magic)
            continue;
         n++;
        }
      if(n >= m_max_positions)
        {
         why = "max posicoes";
         return false;
        }
      return true;
     }

   // score 0..100 escala o risco; atr_pct alto reduz tamanho (vol targeting)
   double LotSize(const string symbol, const double stop_dist,
                  const double score, const double atr_pct)
     {
      if(stop_dist <= 0.0)
         return 0.0;

      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      double score_w = MathMax(0.35, MathMin(1.0, score / 100.0));
      // se ATR no topo do percentil, opera menor
      double vol_w = 1.0 - 0.5 * MathMax(0.0, MathMin(1.0, (atr_pct - 0.5) * 2.0));
      double risk_money = equity * (m_risk_pct / 100.0) * score_w * vol_w;

      // streak de loss: reduz 30% por perda após a 1ª
      if(m_loss_streak > 0)
         risk_money *= MathPow(0.7, m_loss_streak);

      double tick_size  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
      double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
      double lot_step   = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
      double vol_min    = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
      double vol_max    = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
      if(tick_size <= 0.0 || tick_value <= 0.0 || lot_step <= 0.0)
         return 0.0;

      double loss_1 = (stop_dist / tick_size) * tick_value;
      if(loss_1 <= 0.0)
         return 0.0;

      double lots = risk_money / loss_1;
      lots = MathFloor(lots / lot_step) * lot_step;
      return MathMax(vol_min, MathMin(vol_max, lots));
     }

   int LossStreak() const { return m_loss_streak; }
  };

#endif
