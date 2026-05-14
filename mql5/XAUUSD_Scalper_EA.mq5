//+------------------------------------------------------------------+
//| XAUUSD_Scalper_EA.mq5                                            |
//| Author: Dr. Sandeep Grover                                       |
//| Strategy: Three-layer scalping (Trend + RSI/Stoch + ATR gate)   |
//+------------------------------------------------------------------+
#property copyright "Dr. Sandeep Grover"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//── Input parameters ─────────────────────────────────────────────────────────
input int    EMA_Fast        = 20;       // Fast EMA period
input int    EMA_Slow        = 50;       // Slow EMA period
input int    RSI_Period      = 7;        // RSI period
input int    RSI_OS          = 30;       // RSI oversold threshold
input int    RSI_OB          = 70;       // RSI overbought threshold
input int    Stoch_K         = 5;        // Stochastic %K period
input int    Stoch_D         = 3;        // Stochastic %D smoothing
input int    Stoch_Slowing   = 3;        // Stochastic slowing
input int    ATR_Period      = 14;       // ATR period for SL/TP
input double SL_ATR_Mult     = 1.0;     // Stop-loss ATR multiplier
input double TP_ATR_Mult     = 1.5;     // Take-profit ATR multiplier
input int    Max_Concurrent  = 2;        // Max open positions
input double Lot_Size        = 0.01;     // Fixed lot size (use risk % in live)
input int    Session_Start_H = 7;        // Session open (UTC hour)
input int    Session_End_H   = 17;       // Session close (UTC hour)
input int    Magic_Number    = 202400001;

//── Global objects ────────────────────────────────────────────────────────────
CTrade  trade;
int     h_ema_fast, h_ema_slow, h_rsi, h_stoch, h_atr;

//── Initialisation ────────────────────────────────────────────────────────────
int OnInit()
{
    h_ema_fast = iMA(_Symbol, PERIOD_M5, EMA_Fast, 0, MODE_EMA, PRICE_CLOSE);
    h_ema_slow = iMA(_Symbol, PERIOD_M5, EMA_Slow, 0, MODE_EMA, PRICE_CLOSE);
    h_rsi      = iRSI(_Symbol, PERIOD_M5, RSI_Period, PRICE_CLOSE);
    h_stoch    = iStochastic(_Symbol, PERIOD_M5, Stoch_K, Stoch_D, Stoch_Slowing,
                              MODE_SMA, STO_LOWHIGH);
    h_atr      = iATR(_Symbol, PERIOD_M5, ATR_Period);

    if (h_ema_fast == INVALID_HANDLE || h_ema_slow == INVALID_HANDLE ||
        h_rsi == INVALID_HANDLE || h_stoch == INVALID_HANDLE || h_atr == INVALID_HANDLE)
    {
        Print("Indicator handle error — check symbol & terminal data.");
        return INIT_FAILED;
    }

    trade.SetExpertMagicNumber(Magic_Number);
    trade.SetDeviationInPoints(20);
    return INIT_SUCCEEDED;
}

//── Helpers ────────────────────────────────────────────────────────────────────
bool InTradingSession()
{
    MqlDateTime dt;
    TimeToStruct(TimeCurrent(), dt);
    return dt.hour >= Session_Start_H && dt.hour < Session_End_H;
}

int OpenPositionCount()
{
    int count = 0;
    for (int i = PositionsTotal() - 1; i >= 0; i--)
        if (PositionSelectByTicket(PositionGetTicket(i)) &&
            PositionGetString(POSITION_SYMBOL) == _Symbol &&
            PositionGetInteger(POSITION_MAGIC) == Magic_Number)
            count++;
    return count;
}

double GetIndicator(int handle, int buffer, int shift = 1)
{
    double buf[1];
    if (CopyBuffer(handle, buffer, shift, 1, buf) != 1) return EMPTY_VALUE;
    return buf[0];
}

//── Main tick ──────────────────────────────────────────────────────────────────
void OnTick()
{
    if (!InTradingSession())              return;
    if (OpenPositionCount() >= Max_Concurrent) return;

    // Layer 1: Trend
    double ema_fast = GetIndicator(h_ema_fast, 0);
    double ema_slow = GetIndicator(h_ema_slow, 0);
    bool   trend_up   = ema_fast > ema_slow;
    bool   trend_down = ema_fast < ema_slow;

    // Layer 2: Entry trigger
    double rsi_val  = GetIndicator(h_rsi, 0);
    double stoch_k  = GetIndicator(h_stoch, 0);  // MAIN_LINE
    double stoch_d  = GetIndicator(h_stoch, 1);  // SIGNAL_LINE
    double stoch_k1 = GetIndicator(h_stoch, 0, 2); // prior bar

    bool long_trigger  = rsi_val < RSI_OS && stoch_k < 20 && stoch_k > stoch_d;
    bool short_trigger = rsi_val > RSI_OB && stoch_k > 80 && stoch_k < stoch_d;

    // Layer 3: ATR volatility gate + SL/TP
    double atr_val = GetIndicator(h_atr, 0);
    if (atr_val == EMPTY_VALUE || atr_val <= 0) return;

    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

    // LONG entry
    if (trend_up && long_trigger)
    {
        double sl = ask - SL_ATR_Mult * atr_val;
        double tp = ask + TP_ATR_Mult * atr_val;
        trade.Buy(Lot_Size, _Symbol, ask, sl, tp, "XAUUSD_Scalper_Long");
    }

    // SHORT entry
    if (trend_down && short_trigger)
    {
        double sl = bid + SL_ATR_Mult * atr_val;
        double tp = bid - TP_ATR_Mult * atr_val;
        trade.Sell(Lot_Size, _Symbol, bid, sl, tp, "XAUUSD_Scalper_Short");
    }
}

void OnDeinit(const int reason) {}
//+------------------------------------------------------------------+
