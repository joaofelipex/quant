//+------------------------------------------------------------------+
//| SessionFilter.mqh                                                |
//| Filtro de sessão: Londres / Nova York / overlap (hora do servidor)|
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property strict

#ifndef SESSION_FILTER_MQH
#define SESSION_FILTER_MQH

enum ENUM_TRADE_SESSION
  {
   SESSION_ALL = 0,          // Opera o dia inteiro
   SESSION_LONDON = 1,       // Londres
   SESSION_NEWYORK = 2,      // Nova York
   SESSION_OVERLAP = 3,      // Overlap Londres+NY (maior liquidez)
   SESSION_LONDON_NY = 4     // Londres ou NY
  };

class CSessionFilter
  {
private:
   ENUM_TRADE_SESSION m_mode;
   // horários em hora do servidor do broker (ajuste nos inputs)
   int               m_london_start;
   int               m_london_end;
   int               m_ny_start;
   int               m_ny_end;
   bool              m_skip_friday_late;  // evita sexta à tarde
   int               m_friday_cutoff;     // hora de corte na sexta

   int               HourNow()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.hour;
     }

   int               DayOfWeekNow()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.day_of_week; // 0=dom ... 5=sex ... 6=sáb
     }

   bool              InWindow(const int hour, const int start_h, const int end_h)
     {
      // janela [start, end) — se end < start, cruza meia-noite
      if(start_h == end_h)
         return true;
      if(start_h < end_h)
         return (hour >= start_h && hour < end_h);
      return (hour >= start_h || hour < end_h);
     }

public:
                     CSessionFilter(void)
     {
      m_mode = SESSION_OVERLAP;
      // defaults típicos GMT: Londres 08-17, NY 13-22 → overlap 13-17
      // muitos brokers MT5 usam GMT+2/+3 — ajuste pelos inputs do EA
      m_london_start = 8;
      m_london_end   = 17;
      m_ny_start     = 13;
      m_ny_end       = 22;
      m_skip_friday_late = true;
      m_friday_cutoff = 16;
     }

   void              Configure(const ENUM_TRADE_SESSION mode,
                               const int london_start,
                               const int london_end,
                               const int ny_start,
                               const int ny_end,
                               const bool skip_friday_late,
                               const int friday_cutoff)
     {
      m_mode = mode;
      m_london_start = london_start;
      m_london_end   = london_end;
      m_ny_start     = ny_start;
      m_ny_end       = ny_end;
      m_skip_friday_late = skip_friday_late;
      m_friday_cutoff = friday_cutoff;
     }

   bool              IsTradable(void)
     {
      int dow = DayOfWeekNow();
      if(dow == 0 || dow == 6)   // domingo / sábado
         return false;

      int hour = HourNow();

      if(m_skip_friday_late && dow == 5 && hour >= m_friday_cutoff)
         return false;

      if(m_mode == SESSION_ALL)
         return true;

      bool london = InWindow(hour, m_london_start, m_london_end);
      bool ny     = InWindow(hour, m_ny_start, m_ny_end);

      switch(m_mode)
        {
         case SESSION_LONDON:    return london;
         case SESSION_NEWYORK:   return ny;
         case SESSION_OVERLAP:   return (london && ny);
         case SESSION_LONDON_NY: return (london || ny);
         default:                return true;
        }
     }

   string            StatusText(void)
     {
      if(IsTradable())
         return "SESSION_OK";
      return "SESSION_BLOCKED";
     }
  };

#endif
//+------------------------------------------------------------------+
