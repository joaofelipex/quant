//+------------------------------------------------------------------+
//| SessionB3.mqh — horários B3                                      |
//+------------------------------------------------------------------+
#property copyright "QuantSage"
#ifndef SESSION_B3_MQH
#define SESSION_B3_MQH

enum ENUM_QS_SESSION
  {
   QS_SESSION_ALL = 0,
   QS_SESSION_EQUITY = 1,
   QS_SESSION_FUTURES_DAY = 2,
   QS_SESSION_FUTURES_FULL = 3
  };

class CSessionB3
  {
private:
   ENUM_QS_SESSION   m_mode;
   int               m_skip_open;
   int               m_no_new_before_end; // minutos antes do fim: sem novas entradas
   bool              m_skip_friday_late;
   int               m_friday_cut;

   static int HM(const int h, const int m) { return h * 60 + m; }

   int MinutesNow()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.hour * 60 + dt.min;
     }

   int Dow()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      return dt.day_of_week;
     }

   bool InWin(const int now, const int a, const int b)
     {
      if(a < b) return (now >= a && now < b);
      return (now >= a || now < b);
     }

   void ActiveWindow(int &start_min, int &end_min)
     {
      start_min = HM(9, 0);
      end_min = HM(18, 25);
      if(m_mode == QS_SESSION_EQUITY)
        {
         start_min = HM(10, 0);
         end_min = HM(17, 55);
        }
     }

public:
   void Configure(const ENUM_QS_SESSION mode, const int skip_open,
                  const int no_new_before_end, const bool skip_friday_late,
                  const int friday_h, const int friday_m)
     {
      m_mode = mode;
      m_skip_open = MathMax(0, skip_open);
      m_no_new_before_end = MathMax(0, no_new_before_end);
      m_skip_friday_late = skip_friday_late;
      m_friday_cut = HM(friday_h, friday_m);
     }

   bool InSession()
     {
      if(m_mode == QS_SESSION_ALL)
         return true;
      int dow = Dow();
      if(dow == 0 || dow == 6)
         return false;
      int now = MinutesNow();
      if(m_skip_friday_late && dow == 5 && now >= m_friday_cut)
         return false;

      if(m_mode == QS_SESSION_FUTURES_FULL)
        {
         bool day = InWin(now, HM(9, 0), HM(18, 25));
         bool night = InWin(now, HM(20, 30), HM(9, 0));
         if(!(day || night))
            return false;
         if(day && now < HM(9, 0) + m_skip_open)
            return false;
         return true;
        }

      int st, en;
      ActiveWindow(st, en);
      if(!InWin(now, st, en))
         return false;
      if(now < st + m_skip_open)
         return false;
      return true;
     }

   // permite gerir posição, mas bloqueia novas entradas perto do fim
   bool AllowNewEntries()
     {
      if(!InSession())
         return false;
      if(m_mode == QS_SESSION_ALL)
         return true;
      int now = MinutesNow();
      int st, en;
      ActiveWindow(st, en);
      if(m_mode == QS_SESSION_FUTURES_FULL)
        {
         // no diurno: bloqueia perto de 18:25
         if(InWin(now, HM(9, 0), HM(18, 25)) && now >= HM(18, 25) - m_no_new_before_end)
            return false;
         return true;
        }
      if(now >= en - m_no_new_before_end)
         return false;
      return true;
     }

   string Text()
     {
      if(!InSession())
         return "FORA_SESSAO";
      if(!AllowNewEntries())
         return "SESSAO_SEM_NOVAS";
      return "SESSAO_OK";
     }
  };

#endif
