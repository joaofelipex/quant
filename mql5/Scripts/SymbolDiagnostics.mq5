//+------------------------------------------------------------------+
//| SymbolDiagnostics.mq5                                            |
//| Specs do símbolo B3 + exemplo de risco em R$                     |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property version   "1.20"
#property script_show_inputs

input double InpExampleStopPoints = 100; // Stop de exemplo (em pontos do símbolo)
input double InpRiskPercent       = 0.5; // % equity para simular lote

//+------------------------------------------------------------------+
void OnStart()
  {
   string s = _Symbol;
   double point      = SymbolInfoDouble(s, SYMBOL_POINT);
   double tick_size  = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE);
   double vol_min    = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN);
   double vol_step   = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   double vol_max    = SymbolInfoDouble(s, SYMBOL_VOLUME_MAX);
   double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
   string currency   = AccountInfoString(ACCOUNT_CURRENCY);

   Print("========== DIAGNÓSTICO B3 ==========");
   PrintFormat("Símbolo      : %s", s);
   PrintFormat("Descrição    : %s", SymbolInfoString(s, SYMBOL_DESCRIPTION));
   PrintFormat("Digits/Point : %d / %g", (int)SymbolInfoInteger(s, SYMBOL_DIGITS), point);
   PrintFormat("Tick size    : %g", tick_size);
   PrintFormat("Tick value   : %g %s", tick_value, currency);
   PrintFormat("Contract size: %g", SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE));
   PrintFormat("Vol min/step : %g / %g", vol_min, vol_step);
   PrintFormat("Vol max      : %g", vol_max);
   PrintFormat("Stops level  : %d", (int)SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL));
   PrintFormat("Spread       : %d", (int)SymbolInfoInteger(s, SYMBOL_SPREAD));
   PrintFormat("Conta        : %s | Equity %.2f", currency, equity);

   // valor em R$ de 1 ponto (aproximado via tick)
   double value_per_point = 0.0;
   if(tick_size > 0.0 && point > 0.0)
      value_per_point = tick_value * (point / tick_size);

   PrintFormat("≈ R$ por ponto (1 lote): %.4f", value_per_point);

   if(InpExampleStopPoints > 0.0 && tick_size > 0.0 && tick_value > 0.0)
     {
      double stop_price = InpExampleStopPoints * point;
      double loss_1lot  = (stop_price / tick_size) * tick_value;
      double risk_money = equity * (InpRiskPercent / 100.0);
      double lots = (loss_1lot > 0.0) ? risk_money / loss_1lot : 0.0;
      if(vol_step > 0.0)
         lots = MathFloor(lots / vol_step) * vol_step;
      lots = MathMax(vol_min, MathMin(vol_max, lots));

      PrintFormat("--- Simulação risco ---");
      PrintFormat("Stop %g pts → perda ~%.2f %s por 1.00 lote",
                  InpExampleStopPoints, loss_1lot, currency);
      PrintFormat("Risco %.2f%% (%.2f %s) → lote sugerido ~%.2f",
                  InpRiskPercent, risk_money, currency, lots);
     }

   Print("Dicas B3:");
   Print("  WIN  → sessão Futures Day; ponto/tick costumam diferir de FX");
   Print("  WDO  → idem; confira tick value antes de liberar risco");
   Print("  Ações→ sessão Equity; volume mínimo geralmente 100 (lote padrão)");
   Print("  Nome do símbolo muda por broker (WIN$, WINJ26, PETR4, etc.)");
   Print("===================================");
   Alert("Diagnóstico B3 no log Experts (Toolbox)");
  }
//+------------------------------------------------------------------+
