//+------------------------------------------------------------------+
//| SessionFilter.mqh                                                |
//| Filtro de sessão B3 (hora do servidor — em geral = Brasília)     |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property strict

#ifndef SESSION_FILTER_MQH
#define SESSION_FILTER_MQH

enum ENUM_TRADE_SESSION
  {
   SESSION_ALL = 0,              // Qualquer horário (útil só em teste)
   SESSION_B3_EQUITY = 1,        // Ações/BDRs — pregão regular
   SESSION_B3_FUTURES_DAY = 2,   // WIN/WDO — sessão diurna
   SESSION_B3_FUTURES_FULL = 3,  // WIN/WDO — diurna + noturna
   SESSION_CUSTOM = 4            // Usa só a janela custom abaixo
  };

class CSessionFilter
  {
private:
   ENUM_TRADE_SESSION m_mode;
   int               m_custom_start_min;   // minutos desde 00:00
   int               m_custom_end_min;
   int               m_equity_start_min;
   int               m_equity_end_min;
   int               m_fut_day_start_min;
   int               m_fut_day_end_min;
   int               m_fut_night_start_min;
   int               m_fut_night_end_min;
   int               m_skip_open_min;      // ignora leilão / abertura
   bool              m_skip_friday_late;
   int               m_friday_cutoff_min;

   int               MinutesNow()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.hour * 60 + dt.min;
     }

   int               DayOfWeekNow()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.day_of_week; // 0=dom ... 5=sex ... 6=sáb
     }

   bool              InWindow(const int now_min, const int start_min, const int end_min)
     {
      if(start_min == end_min)
         return true;
      if(start_min < end_min)
         return (now_min >= start_min && now_min < end_min);
      // cruza meia-noite (ex.: noturno WIN)
      return (now_min >= start_min || now_min < end_min);
     }

   static int        HM(const int hour, const int minute)
     {
      return hour * 60 + minute;
     }

public:
                     CSessionFilter(void)
     {
      m_mode = SESSION_B3_EQUITY;
      // Defaults B3 (Brasília). Confira no seu broker — alguns usam GMT.
      m_equity_start_min    = HM(10, 0);   // 10:00 pregão
      m_equity_end_min      = HM(17, 55);  // 17:55
      m_fut_day_start_min    = HM(9, 0);    // WIN/WDO diurno
      m_fut_day_end_min      = HM(18, 25);
      m_fut_night_start_min  = HM(20, 30);  // noturno aproximado
      m_fut_night_end_min    = HM(9, 0);    // até abertura do diurno
      m_custom_start_min     = HM(10, 15);
      m_custom_end_min       = HM(16, 45);
      m_skip_open_min        = 15;          // evita leilão/abertura
      m_skip_friday_late     = true;
      m_friday_cutoff_min    = HM(16, 30);
     }

   void              Configure(const ENUM_TRADE_SESSION mode,
                               const int custom_start_h,
                               const int custom_start_m,
                               const int custom_end_h,
                               const int custom_end_m,
                               const int skip_open_min,
                               const bool skip_friday_late,
                               const int friday_cutoff_h,
                               const int friday_cutoff_m)
     {
      m_mode = mode;
      m_custom_start_min  = HM(custom_start_h, custom_start_m);
      m_custom_end_min    = HM(custom_end_h, custom_end_m);
      m_skip_open_min     = MathMax(0, skip_open_min);
      m_skip_friday_late  = skip_friday_late;
      m_friday_cutoff_min = HM(friday_cutoff_h, friday_cutoff_m);
     }

   bool              IsTradable(void)
     {
      int dow = DayOfWeekNow();
      if(dow == 0 || dow == 6)
         return false;

      int now = MinutesNow();

      if(m_skip_friday_late && dow == 5 && now >= m_friday_cutoff_min)
         return false;

      if(m_mode == SESSION_ALL)
         return true;

      bool ok = false;
      int  open_anchor = 0;

      switch(m_mode)
        {
         case SESSION_B3_EQUITY:
            ok = InWindow(now, m_equity_start_min, m_equity_end_min);
            open_anchor = m_equity_start_min;
            break;
         case SESSION_B3_FUTURES_DAY:
            ok = InWindow(now, m_fut_day_start_min, m_fut_day_end_min);
            open_anchor = m_fut_day_start_min;
            break;
         case SESSION_B3_FUTURES_FULL:
            ok = InWindow(now, m_fut_day_start_min, m_fut_day_end_min) ||
                 InWindow(now, m_fut_night_start_min, m_fut_night_end_min);
            // skip_open só na abertura do diurno
            open_anchor = m_fut_day_start_min;
            if(InWindow(now, m_fut_night_start_min, m_fut_night_end_min) &&
               !InWindow(now, m_fut_day_start_min, m_fut_day_end_min))
               return ok; // noturno: sem skip de abertura diurna
            break;
         case SESSION_CUSTOM:
            ok = InWindow(now, m_custom_start_min, m_custom_end_min);
            open_anchor = m_custom_start_min;
            break;
         default:
            return true;
        }

      if(!ok)
         return false;

      // evita primeiros minutos após a abertura da janela ativa
      if(m_skip_open_min > 0 && now < open_anchor + m_skip_open_min)
         return false;

      return true;
     }

   string            StatusText(void)
     {
      return IsTradable() ? "SESSION_OK" : "SESSION_BLOCKED";
     }
  };

#endif
//+------------------------------------------------------------------+
