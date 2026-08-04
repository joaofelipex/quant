//+------------------------------------------------------------------+
//| QuantStarter.mq5                                                 |
//| EA quant Clear/B3 — perfil principal: mini índice (WIN)          |
//| Também: ações e opções (direcional simples; ver aviso)           |
//+------------------------------------------------------------------+
#property copyright "Quant Starter"
#property version   "1.30"
#property strict
#property description "Clear B3: WIN / ações / opções — EMA ou MeanRev + sessão + risco"

#include "Include\RiskManager.mqh"
#include "Include\SignalEngine.mqh"
#include "Include\MeanReversion.mqh"
#include "Include\SessionFilter.mqh"
#include "Include\TradeManager.mqh"

enum ENUM_STRATEGY_MODE
  {
   STRATEGY_MOMENTUM = 0,       // Cruzamento EMA
   STRATEGY_MEAN_REVERSION = 1  // Bollinger + RSI
  };

enum ENUM_ASSET_PROFILE
  {
   PROFILE_WIN = 0,             // Mini índice (principal)
   PROFILE_EQUITY = 1,          // Ações / BDRs
   PROFILE_OPTIONS = 2          // Opções (só direcional / risco menor)
  };

input group "=== Perfil Clear ==="
input ENUM_ASSET_PROFILE InpProfile      = PROFILE_WIN; // Ativo principal
input bool              InpAutoSession   = true;        // Sessão automática do perfil
input bool              InpAutoTune      = true;        // Ajusta ATR mín. / slip sugeridos

input group "=== Estratégia ==="
input ENUM_STRATEGY_MODE InpStrategy     = STRATEGY_MOMENTUM; // Modo
input int               InpFastEMA       = 9;           // EMA rápida
input int               InpSlowEMA       = 21;          // EMA lenta
input int               InpBBPeriod      = 20;          // Bollinger período
input double            InpBBDeviation   = 2.0;         // Bollinger desvio
input int               InpRSIPeriod     = 14;          // RSI período
input double            InpRSI_OS        = 30.0;        // RSI oversold
input double            InpRSI_OB        = 70.0;        // RSI overbought
input int               InpATRPeriod     = 14;          // Período ATR
input double            InpATR_SL        = 1.5;         // SL = ATR * fator
input double            InpATR_TP        = 2.0;         // TP = ATR * fator
input double            InpMinATRPoints  = 80;          // ATR mín. pontos (WIN default 80)

input group "=== Sessão B3 (se AutoSession=false) ==="
input ENUM_TRADE_SESSION InpSession      = SESSION_B3_FUTURES_DAY; // Janela manual
input int               InpCustomStartH  = 10;          // Custom início (h)
input int               InpCustomStartM  = 15;          // Custom início (min)
input int               InpCustomEndH    = 16;          // Custom fim (h)
input int               InpCustomEndM    = 45;          // Custom fim (min)
input int               InpSkipOpenMin   = 10;          // Pular min. pós-abertura (WIN: 10)
input bool              InpSkipFridayLate= true;        // Bloquear sexta tarde
input int               InpFridayCutH    = 16;          // Corte sexta (h)
input int               InpFridayCutM    = 30;          // Corte sexta (min)

input group "=== Risco ==="
input double            InpRiskPercent   = 0.5;         // Risco % equity / trade
input double            InpMaxDailyLoss  = 2.0;         // Perda máx. diária (%)
input int               InpMaxPositions  = 1;           // Máx. posições
input bool              InpReverseOnSignal= true;       // Inverter no sinal oposto (desligue em opções)

input group "=== Execução ==="
input ulong             InpMagic         = 20260803;    // Magic number
input int               InpDeviation     = 30;          // Slippage (pontos)
input bool              InpOnlyNewBar    = true;        // Só em barra nova

CRiskManager    g_risk;
CSignalEngine   g_momentum;
CMeanReversion  g_meanrev;
CSessionFilter  g_session;
CTradeManager   g_trade;
datetime        g_last_bar = 0;

double          g_min_atr_points;
int             g_deviation;
double          g_risk_percent;
bool            g_reverse;
ENUM_TRADE_SESSION g_session_mode;
int             g_skip_open;

//+------------------------------------------------------------------+
bool LooksLikeOptionSymbol(const string sym)
  {
   // Heurística B3: opções de ação costumam ter letras de série no meio
   // (ex.: PETRA340, VALEB120). WIN/WDO e tickers curtos de ação não.
   string u = sym;
   StringToUpper(u);
   if(StringFind(u, "WIN") == 0 || StringFind(u, "WDO") == 0)
      return false;
   if(StringFind(u, "$") >= 0)
      return false;
   int len = StringLen(u);
   if(len < 6 || len > 12)
      return false;
   // ação típica 5 chars (PETR4); opção geralmente > 5 com dígitos no final
   bool has_digit = false;
   for(int i = 0; i < len; i++)
     {
      ushort c = StringGetCharacter(u, i);
      if(c >= '0' && c <= '9')
         has_digit = true;
     }
   return (len >= 6 && has_digit);
  }

//+------------------------------------------------------------------+
void ApplyProfile()
  {
   g_min_atr_points = InpMinATRPoints;
   g_deviation      = InpDeviation;
   g_risk_percent   = InpRiskPercent;
   g_reverse        = InpReverseOnSignal;
   g_session_mode   = InpSession;
   g_skip_open      = InpSkipOpenMin;

   if(InpAutoSession)
     {
      if(InpProfile == PROFILE_WIN)
         g_session_mode = SESSION_B3_FUTURES_DAY;
      else
         g_session_mode = SESSION_B3_EQUITY; // ações e opções no pregão
     }

   if(InpAutoTune)
     {
      if(InpProfile == PROFILE_WIN)
        {
         if(InpMinATRPoints <= 0)
            g_min_atr_points = 80;
         if(InpDeviation == 50 || InpDeviation == 30)
            g_deviation = 30;
         g_skip_open = (InpSkipOpenMin == 15 || InpSkipOpenMin == 10) ? 10 : InpSkipOpenMin;
        }
      else if(InpProfile == PROFILE_EQUITY)
        {
         g_min_atr_points = 0; // ações: filtro ATR em pontos é menos útil
         g_deviation = MathMax(InpDeviation, 50);
         g_skip_open = MathMax(InpSkipOpenMin, 15);
        }
      else if(InpProfile == PROFILE_OPTIONS)
        {
         g_min_atr_points = 0;
         g_deviation = MathMax(InpDeviation, 80);
         g_skip_open = MathMax(InpSkipOpenMin, 15);
         g_risk_percent = MathMin(InpRiskPercent, 0.25); // opções: risco menor
         g_reverse = false; // não “inverter” prêmio como se fosse futuro
        }
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpStrategy == STRATEGY_MOMENTUM && InpFastEMA >= InpSlowEMA)
     {
      Print("Fast EMA deve ser < Slow EMA");
      return INIT_PARAMETERS_INCORRECT;
     }

   ApplyProfile();

   if(InpProfile == PROFILE_OPTIONS || LooksLikeOptionSymbol(_Symbol))
     {
      Print("=== AVISO OPÇÕES ===");
      Print("Este EA é direcional (compra/venda de prêmio), sem modelo de Gregas/vencimento.");
      Print("Na Clear, opções complexas costumam ser melhores em outras plataformas.");
      Print("Use perfil OPTIONS só com tamanho pequeno e após SymbolDiagnostics.");
     }

   if(InpProfile == PROFILE_WIN)
     {
      string u = _Symbol;
      StringToUpper(u);
      if(StringFind(u, "WIN") < 0)
         Print("Perfil WIN ativo, mas símbolo não parece WIN — confira Market Watch (WIN$ / WIN$N / WINxy).");
     }

   g_risk.Configure(g_risk_percent, InpMaxDailyLoss, InpMaxPositions);
   g_trade.Configure(InpMagic, g_deviation, "QuantStarter");
   g_session.Configure(g_session_mode,
                       InpCustomStartH, InpCustomStartM,
                       InpCustomEndH, InpCustomEndM,
                       g_skip_open, InpSkipFridayLate,
                       InpFridayCutH, InpFridayCutM);

   if(InpStrategy == STRATEGY_MOMENTUM)
     {
      if(!g_momentum.Init(_Symbol, _Period, InpFastEMA, InpSlowEMA,
                          InpATRPeriod, g_min_atr_points))
         return INIT_FAILED;
     }
   else
     {
      if(!g_meanrev.Init(_Symbol, _Period, InpBBPeriod, InpBBDeviation,
                         InpRSIPeriod, InpRSI_OS, InpRSI_OB, InpATRPeriod))
         return INIT_FAILED;
     }

   PrintFormat("QuantStarter v1.30 Clear | %s %s | profile=%s | mode=%s | risk=%.2f%% | session=%s | slip=%d",
               _Symbol, EnumToString(_Period),
               EnumToString(InpProfile), EnumToString(InpStrategy),
               g_risk_percent, EnumToString(g_session_mode), g_deviation);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   g_momentum.Release();
   g_meanrev.Release();
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(InpOnlyNewBar && !IsNewBar())
      return;

   if(!g_session.IsTradable())
      return;

   ENUM_TRADE_SIGNAL signal = SIGNAL_NONE;
   double atr = 0.0;

   if(InpStrategy == STRATEGY_MOMENTUM)
     {
      signal = g_momentum.Evaluate();
      atr    = g_momentum.LastATR();
     }
   else
     {
      signal = g_meanrev.Evaluate();
      atr    = g_meanrev.LastATR();
     }

   if(signal == SIGNAL_NONE || atr <= 0.0)
      return;

   double sl_dist = atr * InpATR_SL;
   double tp_dist = atr * InpATR_TP;
   double lots    = g_risk.LotSize(_Symbol, sl_dist);
   if(lots <= 0.0)
     {
      Print("[EA] Lote inválido — SymbolDiagnostics no gráfico Clear");
      return;
     }

   if(signal == SIGNAL_BUY)
     {
      if(g_reverse)
         g_trade.CloseAll(_Symbol);
      if(!g_risk.CanOpenTrade(_Symbol, g_trade.Magic()))
         return;
      g_trade.OpenBuy(_Symbol, lots, sl_dist, tp_dist);
     }
   else if(signal == SIGNAL_SELL)
     {
      if(g_reverse)
         g_trade.CloseAll(_Symbol);
      if(!g_risk.CanOpenTrade(_Symbol, g_trade.Magic()))
         return;
      g_trade.OpenSell(_Symbol, lots, sl_dist, tp_dist);
     }
  }

//+------------------------------------------------------------------+
bool IsNewBar()
  {
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == 0)
      return false;
   if(t == g_last_bar)
      return false;
   g_last_bar = t;
   return true;
  }
//+------------------------------------------------------------------+
