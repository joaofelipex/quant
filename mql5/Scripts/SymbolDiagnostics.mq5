//+------------------------------------------------------------------+
//| SymbolDiagnostics.mq5                                            |
//| Script: imprime specs do símbolo (útil antes de calibrar risco)  |
//| Copie para: <Dados>\MQL5\Scripts\  |  arraste no gráfico          |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property version   "1.00"
#property script_show_inputs

//+------------------------------------------------------------------+
void OnStart()
  {
   string s = _Symbol;
   Print("========== DIAGNÓSTICO ==========");
   PrintFormat("Símbolo      : %s", s);
   PrintFormat("Descrição    : %s", SymbolInfoString(s, SYMBOL_DESCRIPTION));
   PrintFormat("Digits       : %d", (int)SymbolInfoInteger(s, SYMBOL_DIGITS));
   PrintFormat("Point        : %g", SymbolInfoDouble(s, SYMBOL_POINT));
   PrintFormat("Tick size    : %g", SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE));
   PrintFormat("Tick value   : %g", SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE));
   PrintFormat("Contract size: %g", SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE));
   PrintFormat("Vol min/step : %g / %g",
               SymbolInfoDouble(s, SYMBOL_VOLUME_MIN),
               SymbolInfoDouble(s, SYMBOL_VOLUME_STEP));
   PrintFormat("Vol max      : %g", SymbolInfoDouble(s, SYMBOL_VOLUME_MAX));
   PrintFormat("Stops level  : %d", (int)SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL));
   PrintFormat("Spread       : %d", (int)SymbolInfoInteger(s, SYMBOL_SPREAD));
   PrintFormat("Account currency: %s", AccountInfoString(ACCOUNT_CURRENCY));
   PrintFormat("Equity       : %.2f", AccountInfoDouble(ACCOUNT_EQUITY));
   Print("=================================");
   Alert("Diagnóstico impresso no Experts log (aba Toolbox > Experts)");
  }
//+------------------------------------------------------------------+
