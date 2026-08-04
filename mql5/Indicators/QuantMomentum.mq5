//+------------------------------------------------------------------+
//| QuantMomentum.mq5                                                |
//| Indicador visual do sinal (EMA fast/slow + setas de cruzamento)  |
//| Copie para: <Dados>\MQL5\Indicators\                             |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

#property indicator_label1  "EMA Fast"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_width1  2

#property indicator_label2  "EMA Slow"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrOrangeRed
#property indicator_width2  2

#property indicator_label3  "Buy"
#property indicator_type3   DRAW_ARROW
#property indicator_color3  clrLime
#property indicator_width3  2

#property indicator_label4  "Sell"
#property indicator_type4   DRAW_ARROW
#property indicator_color4  clrRed
#property indicator_width4  2

input int InpFastEMA = 12;
input int InpSlowEMA = 26;

double g_fast[];
double g_slow[];
double g_buy[];
double g_sell[];
int    g_h_fast = INVALID_HANDLE;
int    g_h_slow = INVALID_HANDLE;

//+------------------------------------------------------------------+
int OnInit()
  {
   SetIndexBuffer(0, g_fast, INDICATOR_DATA);
   SetIndexBuffer(1, g_slow, INDICATOR_DATA);
   SetIndexBuffer(2, g_buy,  INDICATOR_DATA);
   SetIndexBuffer(3, g_sell, INDICATOR_DATA);

   // buffers no sentido cronológico (0 = barra mais antiga)
   ArraySetAsSeries(g_fast, false);
   ArraySetAsSeries(g_slow, false);
   ArraySetAsSeries(g_buy, false);
   ArraySetAsSeries(g_sell, false);

   PlotIndexSetInteger(2, PLOT_ARROW, 233);
   PlotIndexSetInteger(3, PLOT_ARROW, 234);
   PlotIndexSetDouble(2, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   PlotIndexSetDouble(3, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   g_h_fast = iMA(_Symbol, _Period, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_h_slow = iMA(_Symbol, _Period, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(g_h_fast == INVALID_HANDLE || g_h_slow == INVALID_HANDLE)
      return INIT_FAILED;

   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("QuantMomentum(%d,%d)", InpFastEMA, InpSlowEMA));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_h_fast != INVALID_HANDLE) IndicatorRelease(g_h_fast);
   if(g_h_slow != INVALID_HANDLE) IndicatorRelease(g_h_slow);
  }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   if(rates_total < InpSlowEMA + 3)
      return 0;

   // CopyBuffer preenche no mesmo alinhamento dos buffers (não-série)
   if(CopyBuffer(g_h_fast, 0, 0, rates_total, g_fast) < rates_total)
      return 0;
   if(CopyBuffer(g_h_slow, 0, 0, rates_total, g_slow) < rates_total)
      return 0;

   int start = (prev_calculated > 2) ? prev_calculated - 1 : 1;
   double pad = SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 10.0;

   for(int i = start; i < rates_total; i++)
     {
      g_buy[i]  = EMPTY_VALUE;
      g_sell[i] = EMPTY_VALUE;

      bool cross_up   = (g_fast[i - 1] <= g_slow[i - 1] && g_fast[i] > g_slow[i]);
      bool cross_down = (g_fast[i - 1] >= g_slow[i - 1] && g_fast[i] < g_slow[i]);

      if(cross_up)
         g_buy[i] = low[i] - pad;
      if(cross_down)
         g_sell[i] = high[i] + pad;
     }
   return rates_total;
  }
//+------------------------------------------------------------------+
