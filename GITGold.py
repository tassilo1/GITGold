import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import os
import json
import concurrent.futures
import time

# --- 1. CLOUD-SICHERE DATENABFRAGE (CACHING) ---

@st.cache_data(ttl=3600)  # Suchergebnisse für 1 Stunde im Cache
def finde_ticker_liste(suchbegriff):
    if not suchbegriff: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={requests.utils.quote(suchbegriff)}"
    headers = {'User-Agent': 'Mozilla/5.0'} 
    try:
        response = requests.get(url, headers=headers, timeout=5).json()
        ergebnisse = []
        if 'quotes' in response:
            for t in response['quotes']:
                if 'symbol' in t:
                    name = t.get('shortname') or t.get('longname') or 'Unbekannt'
                    exch = t.get('exchDisp') or t.get('exchange') or 'Unbekannt'
                    curr = t.get('currency', '')
                    curr_map = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "CAD": "CAD"}
                    ergebnisse.append({'symbol': t['symbol'], 'name': name, 'exchange': exch, 'currency': curr_map.get(curr, curr)})
        return ergebnisse
    except: return []

@st.cache_data(ttl=900, show_spinner=False)  # Kurse für 15 Minuten speichern (900 Sekunden)
def get_cached_history(ticker, period, interval):
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=86400, show_spinner=False)  # Stammdaten (Sektor etc.) für 24h speichern!
def get_cached_info(ticker):
    try:
        return yf.Ticker(ticker).info
    except:
        return {}

@st.cache_data(ttl=86400, show_spinner=False)  # Dividenden für 24h speichern!
def get_cached_dividends(ticker):
    try:
        return yf.Ticker(ticker).dividends
    except:
        return pd.Series()

# --- 2. HILFSFUNKTIONEN (JSON-BASIERT) ---

def lade_portfolio():
    if os.path.exists("meine_aktien.json"):
        try:
            with open("meine_aktien.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    if isinstance(v, str): data[k] = {"ticker": v, "menge": 0.0, "sector": "Unbekannt", "country": "Unbekannt", "currency": ""}
                    else:
                        if "sector" not in v: v["sector"] = "Unbekannt"
                        if "country" not in v: v["country"] = "Unbekannt"
                        if "currency" not in v: v["currency"] = ""
                return data
        except: return {}
    return {}

def speichere_in_portfolio(name, ticker, menge=0.0, sector="Unbekannt", country="Unbekannt", currency=""):
    p = lade_portfolio()
    p[name] = {"ticker": ticker, "menge": menge, "sector": sector, "country": country, "currency": currency}
    with open("meine_aktien.json", "w", encoding="utf-8") as f: json.dump(p, f, ensure_ascii=False, indent=4)
    st.rerun()

def aktualisiere_menge(name, neue_menge):
    p = lade_portfolio()
    if name in p:
        p[name]["menge"] = neue_menge
        with open("meine_aktien.json", "w", encoding="utf-8") as f: json.dump(p, f, ensure_ascii=False, indent=4)
    st.rerun()

def entferne_aus_portfolio(name):
    p = lade_portfolio()
    if name in p:
        del p[name]
        with open("meine_aktien.json", "w", encoding="utf-8") as f: json.dump(p, f, ensure_ascii=False, indent=4)
    st.rerun()

@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- 3. SETUP & SIDEBAR ---

st.set_page_config(page_title="Aktienanalyse Pro", layout="wide")

# --- NEUER CSS FIX: BÜNDIG, KLEINERE SCHRIFT, SILBENTRENNUNG ---
st.markdown("""
    <style>
        [data-testid="stTable"] table {
            width: 100% !important;
            table-layout: fixed !important;
        }
        [data-testid="stTable"] th, [data-testid="stTable"] td {
            text-align: center !important;
            font-size: 0.85em !important;
            padding: 8px 4px !important;
            white-space: normal !important;
        }
        /* Spalte 1 (Name): Mehr Platz, minimal kleinere Schrift, schöne Silbentrennung */
        [data-testid="stTable"] th:nth-child(1), [data-testid="stTable"] td:nth-child(1) {
            width: 25% !important; 
            text-align: left !important;
            font-size: 0.80em !important;
            word-break: normal !important;
            overflow-wrap: break-word !important;
            -webkit-hyphens: auto;
            -moz-hyphens: auto;
            hyphens: auto;
        }
        /* Die letzten beiden Spalten (Empfehlung & Signal) etwas breiter, da Text dort länger sein kann */
        [data-testid="stTable"] th:nth-last-child(1), [data-testid="stTable"] td:nth-last-child(1),
        [data-testid="stTable"] th:nth-last-child(2), [data-testid="stTable"] td:nth-last-child(2) {
            width: 11% !important; 
        }
    </style>
""", unsafe_allow_html=True)

st.title("📈 Professionelles Analyse-Dashboard")

portfolio = lade_portfolio()
st.sidebar.header("⚙️ Steuerung")
modus = st.sidebar.radio("Modus:", ["Mein Portfolio / Watchlist", "Neue Suche"])
query, display_name = "", ""
asset_currency_sym = "" 

if modus == "Mein Portfolio / Watchlist":
    if portfolio:
        display_name = st.sidebar.selectbox("Asset auswählen:", list(portfolio.keys()))
        query = portfolio[display_name]["ticker"]
        akt_menge = portfolio[display_name].get("menge", 0.0)
        asset_currency_sym = portfolio[display_name].get("currency", "")
        
        st.sidebar.markdown("---")
        neue_menge = st.sidebar.number_input("Anzahl im Depot (0 = Watchlist):", min_value=0.0, value=float(akt_menge), step=1.0)
        if st.sidebar.button("💾 Anzahl speichern"): aktualisiere_menge(display_name, neue_menge)
        st.sidebar.markdown("---")
        if st.sidebar.button("🗑️ Aus Liste löschen"): entferne_aus_portfolio(display_name)
    else:
        st.sidebar.info("Portfolio leer. Suche Assets zum Hinzufügen.")
else:
    suche = st.sidebar.text_input("Name/WKN/ISIN:", help="Tipp: Suche nach ISIN für die exaktesten Ergebnisse.")
    if suche:
        treffer = finde_ticker_liste(suche)
        if treffer:
            optionen = [f"{t['name']} ({t['symbol']}) | 🏛️ {t['exchange']} | 🪙 {t['currency']}" for t in treffer]
            auswahl = st.sidebar.selectbox("Börsenplatz auswählen:", optionen)
            selected_ticker = next(t for t in treffer if f"{t['name']} ({t['symbol']}) | 🏛️ {t['exchange']} | 🪙 {t['currency']}" == auswahl)
            
            query = selected_ticker['symbol']
            display_name = selected_ticker['name']
            asset_currency_sym = selected_ticker['currency']
            
            st.sidebar.success(f"Gefunden: {display_name} auf {selected_ticker['exchange']} (in {asset_currency_sym})")
            wn = st.sidebar.text_input("Speichern als:", value=f"{display_name} ({selected_ticker['exchange']})")
            start_menge = st.sidebar.number_input("Anzahl (0 = landet auf Watchlist):", min_value=0.0, value=0.0, step=1.0)
            
            if st.sidebar.button("💾 Speichern"): 
                with st.spinner("Speichere Asset..."):
                    info_data = get_cached_info(query)
                    sec = info_data.get('sector', info_data.get('category', 'Unbekannt'))
                    ctry = info_data.get('country', 'Unbekannt')
                speichere_in_portfolio(wn, query, start_menge, sec, ctry, asset_currency_sym)
        else:
            st.sidebar.warning("Keine Ergebnisse gefunden.")

# --- 4. DYNAMISCHE LOGIK & ANALYSE ---

if query:
    zeitraum = st.sidebar.selectbox("Zeitraum:", ["1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max"], index=2)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Darstellung")
    show_candles = st.sidebar.checkbox("Candlesticks anzeigen", value=True)
    show_line = st.sidebar.checkbox("Linien-Chart anzeigen", value=True)
    
    st.sidebar.subheader("Backtest Parameter")
    tage_backtest = st.sidebar.number_input("Erfolg nach X Tagen prüfen:", min_value=1, max_value=30, value=7)
    
    logic = {
        "1d":  {"int": "5m",  "unit": "Minuten", "buf": "5d"}, "5d":  {"int": "60m", "unit": "Stunden", "buf": "1mo"},
        "1mo": {"int": "1d",  "unit": "Tage",    "buf": "3mo"}, "3mo": {"int": "1d",  "unit": "Tage",    "buf": "6mo"},
        "6mo": {"int": "1d",  "unit": "Tage",    "buf": "1y"}, "1y":  {"int": "1d",  "unit": "Tage",    "buf": "2y"},
        "5y":  {"int": "1d",  "unit": "Tage",    "buf": "max"}, "max": {"int": "1d",  "unit": "Tage",    "buf": "max"}
    }
    
    cfg = logic.get(zeitraum)
    bb_fenster = st.sidebar.slider(f"Bollinger Fenster ({cfg['unit']})", 5, 100, 20)
    block_breite = st.sidebar.slider(f"Zonen Breite ({cfg['unit']})", 1, 20, 5)

    with st.spinner('Lade Kursdaten...'):
        df_full = get_cached_history(query, cfg['buf'], cfg['int'])
        df_crop = get_cached_history(query, zeitraum, cfg['int'])

    if not df_full.empty: df_full = df_full[~df_full.index.duplicated(keep='first')]
    if not df_crop.empty: df_crop = df_crop[~df_crop.index.duplicated(keep='first')]

    if df_full.empty or df_crop.empty:
        st.warning(f"⚠️ Yahoo Finance liefert aktuell keine historischen Kursdaten für das Symbol '{query}'.")
    else:
        try:
            # Berechnungen
            df_full['SMA'] = df_full['Close'].rolling(window=bb_fenster).mean()
            df_full['STD'] = df_full['Close'].rolling(window=bb_fenster).std()
            df_full['Oben'] = df_full['SMA'] + (df_full['STD'] * 2)
            df_full['Unten'] = df_full['SMA'] - (df_full['STD'] * 2)
            
            delta = df_full['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            df_full['RSI'] = 100 - (100 / (1 + (gain/loss.replace(0, 1e-10))))

            df_full['EMA_12'] = df_full['Close'].ewm(span=12, adjust=False).mean()
            df_full['EMA_26'] = df_full['Close'].ewm(span=26, adjust=False).mean()
            df_full['MACD'] = df_full['EMA_12'] - df_full['EMA_26']
            df_full['MACD_Signal'] = df_full['MACD'].ewm(span=9, adjust=False).mean()
            df_full['MACD_Hist'] = df_full['MACD'] - df_full['MACD_Signal']

            df = df_full.loc[df_crop.index[0]:].copy()

            # Metriken
            start_preis = float(df['Close'].iloc[0])
            aktueller_preis = float(df['Close'].iloc[-1])
            perf_abs = aktueller_preis - start_preis
            perf_pct = (perf_abs / start_preis) * 100 if start_preis != 0 else 0
            rsi_val = df['RSI'].iloc[-1]
            rsi_str = f"{rsi_val:.1f}" if pd.notna(rsi_val) else "N/A"

            # Dividende
            div_yield_pct = 0.0
            divs = get_cached_dividends(query)
            if not divs.empty:
                divs.index = pd.to_datetime(divs.index, utc=True)
                cutoff = pd.Timestamp.now(tz='UTC') - pd.DateOffset(years=2)
                div_2y_sum = divs[divs.index >= cutoff].sum()
                if aktueller_preis > 0: div_yield_pct = ((div_2y_sum / 2) / aktueller_preis) * 100

            # Kursziel
            info = get_cached_info(query)
            target_price = info.get('targetMeanPrice')
            if target_price and aktueller_preis > 0:
                est_perf = ((target_price - aktueller_preis) / aktueller_preis) * 100
                est_perf_str = f"{est_perf:+.2f}%"
                target_str = f"Ziel: {target_price:.2f}"
            else:
                est_perf_str = "N/A"
                target_str = "Kein Kursziel"

            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Asset", display_name)
            m2.metric("Kurs", f"{aktueller_preis:.2f} {asset_currency_sym}")
            m3.metric("Performance (Ztr.)", f"{perf_pct:+.2f}%", delta=f"{perf_abs:.2f} {asset_currency_sym}")
            m4.metric("RSI (14)", rsi_str)
            m5.metric("Div. Rendite p.a.", f"{div_yield_pct:.2f}%" if div_yield_pct > 0 else "N/A")
            m6.metric("Analysten-Potenzial", est_perf_str, delta=target_str, delta_color="normal")

            # CHARTING
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.5, 0.1, 0.2, 0.2])
            
            fig.add_trace(go.Scatter(x=df.index, y=df['Unten'], line=dict(color='rgba(255,255,255,0)'), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Oben'], fill='tonexty', fillcolor='rgba(100, 150, 255, 0.07)', line=dict(color='rgba(255,255,255,0)'), name="Bollinger"), row=1, col=1)
            
            if show_candles: fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Candles", increasing_line_color='#00ff00', decreasing_line_color='#ff4b4b', opacity=0.6 if show_line else 1.0), row=1, col=1)
            if show_line: fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name='Trendlinie', line=dict(color='#00BFFF', width=2)), row=1, col=1)

            def draw_zones(starts, color):
                for d in df[starts].index:
                    try:
                        idx = df.index.get_loc(d)
                        if isinstance(idx, slice) or isinstance(idx, pd.Series): return
                        end = df.index[min(idx + block_breite, len(df)-1)]
                        y_h, y_l = float(df['High'].iloc[idx]), float(df['Low'].iloc[idx])
                        fig.add_shape(type="rect", x0=d, y0=y_l, x1=end, y1=y_h, fillcolor=color, line_width=0, layer="below", row=1, col=1)
                        for y in [y_h, (y_h+y_l)/2, y_l]: fig.add_shape(type="line", x0=end, y0=y, x1=df.index[-1], y1=y, line=dict(color=color, width=1, dash="dot"), layer="below", row=1, col=1)
                    except: continue

            draw_zones((df['Close'] > df['Oben']) & (df['Close'].shift(1) <= df['Oben'].shift(1)), "rgba(0, 150, 255, 0.3)") 
            draw_zones((df['Close'] < df['Unten']) & (df['Close'].shift(1) >= df['Unten'].shift(1)), "rgba(255, 50, 50, 0.3)") 

            vol_data = df['Volume'] if 'Volume' in df.columns else [0] * len(df)
            fig.add_trace(go.Bar(x=df.index, y=vol_data, marker_color='rgba(128,128,128,0.5)', name="Volumen"), row=2, col=1)
            
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='orange'), name="RSI"), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,0,0,0.5)", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="rgba(0,255,0,0.5)", row=3, col=1)

            macd_colors = ['rgba(0, 255, 0, 0.5)' if val >= 0 else 'rgba(255, 75, 75, 0.5)' for val in df['MACD_Hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=macd_colors, name="MACD Hist"), row=4, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='#00BFFF', width=1.5), name="MACD"), row=4, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], line=dict(color='#ff9900', width=1.5), name="Signal"), row=4, col=1)

            fig.update_xaxes(showgrid=True, gridcolor='rgba(255,255,255,0.05)', rangeslider_visible=False)
            fig.update_layout(template="plotly_dark", height=1000, showlegend=True, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"Fehler beim Zeichnen des Charts: {e}")

        # --- PORTFOLIO SCANNER ---
        st.markdown("---")
        
        if portfolio:
            with st.expander("Signale, Performance & Backtesting ausklappen", expanded=True):
                signal_data = []
                total_portfolio_wert = 0.0
                total_portfolio_div = 0.0
                
                prog_bar = st.progress(0)
                items_len = len(portfolio)

                st.caption("Lade Analysedaten (gecached für Cloud-Sicherheit)...")
                
                for idx, (p_name, p_data) in enumerate(portfolio.items()):
                    try:
                        p_ticker = p_data["ticker"]
                        p_menge = p_data.get("menge", 0.0)
                        p_sector = p_data.get("sector", "Unbekannt")
                        p_country = p_data.get("country", "Unbekannt")
                        
                        info = get_cached_info(p_ticker)
                        quote_type = info.get('quoteType', '').upper()
                        
                        if quote_type in ['ETF', 'MUTUALFUND']: asset_type = "ETF"
                        elif quote_type == 'EQUITY': asset_type = "Aktie"
                        else: asset_type = "ETF" if "ETF" in p_name.upper() or "FUND" in p_name.upper() else "Aktie"
                        
                        if p_sector == "Unbekannt" or p_country == "Unbekannt" or not p_sector or not p_country:
                            p_sector = info.get('sector', info.get('category', 'Unbekannt'))
                            p_country = info.get('country', 'Unbekannt')
                                
                        if asset_type == "ETF":
                            if p_sector == "Unbekannt" or not p_sector: p_sector = "Diversifiziert (ETF)"
                            if p_country == "Unbekannt" or not p_country: p_country = "Global / Region (ETF)"
                        
                        p_df = get_cached_history(p_ticker, cfg['buf'], cfg['int'])
                        if p_df.empty: continue
                        
                        p_sma = p_df['Close'].rolling(window=bb_fenster).mean()
                        p_std = p_df['Close'].rolling(window=bb_fenster).std()
                        p_up = float(p_sma.iloc[-1] + (p_std.iloc[-1] * 2))
                        p_lo = float(p_sma.iloc[-1] - (p_std.iloc[-1] * 2))
                        
                        p_delta = p_df['Close'].diff()
                        p_gain = (p_delta.where(p_delta > 0, 0)).rolling(window=14).mean()
                        p_loss = (-p_delta.where(p_delta < 0, 0)).rolling(window=14).mean()
                        p_rsi_val = 100 - (100 / (1 + (p_gain/p_loss.replace(0, 1e-10))))
                        cur_rsi = float(p_rsi_val.iloc[-1]) if pd.notna(p_rsi_val.iloc[-1]) else 50.0
                        
                        p_macd = p_df['Close'].ewm(span=12, adjust=False).mean() - p_df['Close'].ewm(span=26, adjust=False).mean()
                        p_macd_sig = p_macd.ewm(span=9, adjust=False).mean()
                        macd_hist = float(p_macd.iloc[-1] - p_macd_sig.iloc[-1])
                        
                        cur_close = float(p_df['Close'].iloc[-1])
                        p_wert = cur_close * p_menge
                        
                        score = 0
                        if cur_rsi < 30: score += 1
                        elif cur_rsi > 70: score -= 1
                        if cur_close < p_lo: score += 1
                        elif cur_close > p_up: score -= 1
                        if macd_hist > 0: score += 1
                        elif macd_hist < 0: score -= 1
                        
                        empf = "Neutral"
                        if score >= 2: empf = "🟢 KAUF"
                        elif score <= -2: empf = "🔴 VERKAUF"
                        elif score == 1: empf = "↗️ Halten (Aufwärts)"
                        elif score == -1: empf = "↘️ Halten (Abwärts)"
                        
                        signal = "Neutral"
                        if cur_close > p_up: signal = "📈 Überkauft (Oben)"
                        elif cur_close < p_lo: signal = "📉 Überverkauft (Dip)"
                        
                        df_1y = get_cached_history(p_ticker, "1y", "1d")
                        perf_1d = perf_1mo = perf_3mo = perf_1y = 0.0
                        erfolg_oben = total_oben = erfolg_unten = total_unten = 0
                        trefferquote = 0.0 
                        
                        if not df_1y.empty and len(df_1y) > bb_fenster:
                            c_curr = float(df_1y['Close'].iloc[-1])
                            perf_1d = ((c_curr - df_1y['Close'].iloc[-2]) / df_1y['Close'].iloc[-2]) * 100 if len(df_1y) >= 2 else 0
                            perf_1mo = ((c_curr - df_1y['Close'].iloc[-min(22, len(df_1y))]) / df_1y['Close'].iloc[-min(22, len(df_1y))]) * 100 if len(df_1y) >= 22 else 0
                            perf_3mo = ((c_curr - df_1y['Close'].iloc[-min(64, len(df_1y))]) / df_1y['Close'].iloc[-min(64, len(df_1y))]) * 100 if len(df_1y) >= 64 else 0
                            perf_1y = ((c_curr - df_1y['Close'].iloc[0]) / df_1y['Close'].iloc[0]) * 100
                            
                            df_1y['SMA_1y'] = df_1y['Close'].rolling(window=bb_fenster).mean()
                            df_1y['STD_1y'] = df_1y['Close'].rolling(window=bb_fenster).std()
                            df_1y['Up_1y'] = df_1y['SMA_1y'] + (df_1y['STD_1y'] * 2)
                            df_1y['Low_1y'] = df_1y['SMA_1y'] - (df_1y['STD_1y'] * 2)
                            
                            df_1y['Break_Up'] = (df_1y['Close'] > df_1y['Up_1y']) & (df_1y['Close'].shift(1) <= df_1y['Up_1y'].shift(1))
                            df_1y['Break_Down'] = (df_1y['Close'] < df_1y['Low_1y']) & (df_1y['Close'].shift(1) >= df_1y['Low_1y'].shift(1))
                            df_1y['Close_future'] = df_1y['Close'].shift(-int(tage_backtest))
                            
                            valid_break_up = df_1y[df_1y['Break_Up']].dropna(subset=['Close_future'])
                            total_oben = len(valid_break_up)
                            erfolg_oben = len(valid_break_up[valid_break_up['Close_future'] > valid_break_up['Close']])
                            
                            valid_break_down = df_1y[df_1y['Break_Down']].dropna(subset=['Close_future'])
                            total_unten = len(valid_break_down)
                            erfolg_unten = len(valid_break_down[valid_break_down['Close_future'] > valid_break_down['Close']])

                            gesamt_signale = total_oben + total_unten
                            if gesamt_signale > 0: trefferquote = (erfolg_oben + erfolg_unten) / gesamt_signale
                        
                        div_yield_pct = 0.0
                        expected_div_abs = 0.0
                        divs = get_cached_dividends(p_ticker)
                        if not divs.empty:
                            divs.index = pd.to_datetime(divs.index, utc=True)
                            cutoff = pd.Timestamp.now(tz='UTC') - pd.DateOffset(years=2)
                            div_2y_sum = divs[divs.index >= cutoff].sum()
                            if cur_close > 0: div_yield_pct = ((div_2y_sum / 2) / cur_close) * 100
                            expected_div_abs = (div_2y_sum / 2) * p_menge
                        
                        dist_type = "Ausschüttend" if div_yield_pct > 0.0 else "Thesaurierend"

                        signal_data.append({
                            "Asset": p_name, "Menge": round(p_menge, 2), "Wert": round(p_wert, 2),
                            "Kurs": round(cur_close, 2), "1T %": round(perf_1d, 2), "1M %": round(perf_1mo, 2),
                            "3M %": round(perf_3mo, 2), "1J %": round(perf_1y, 2), "Div % p.a.": round(div_yield_pct, 2),
                            "Empfehlung": empf, "Signal": signal,
                            f"Break Oben ({int(tage_backtest)}T)": f"{erfolg_oben}/{total_oben}",
                            f"Break Unten ({int(tage_backtest)}T)": f"{erfolg_unten}/{total_unten}",
                            "RSI": round(cur_rsi, 1), "Trefferquote": trefferquote, "AssetType": asset_type,
                            "DistType": dist_type, "Sector": p_sector, "Country": p_country
                        })
                        total_portfolio_wert += p_wert
                        total_portfolio_div += expected_div_abs

                    except Exception as e:
                        pass
                    
                    prog_bar.progress((idx + 1) / items_len)
                    time.sleep(0.3)
                
                prog_bar.empty()
                
                if signal_data:
                    res_df = pd.DataFrame(signal_data)
                    res_df = res_df.sort_values(by="Trefferquote", ascending=False).reset_index(drop=True)
                    
                    df_portfolio = res_df[res_df["Menge"] > 0]
                    df_watchlist = res_df[res_df["Menge"] == 0]
                    
                    # -----------------------------
                    # BEREICH: MEIN PORTFOLIO
                    # -----------------------------
                    st.subheader("💼 Mein Portfolio")
                    
                    if not df_portfolio.empty:
                        c1, c2, c3 = st.columns([0.4, 0.4, 0.2])
                        c1.metric("💰 Gesamtwert Portfolio", f"{total_portfolio_wert:,.2f}")
                        port_yield = (total_portfolio_div / total_portfolio_wert) * 100 if total_portfolio_wert > 0 else 0
                        c2.metric("💵 Erwartete Jahresdividende", f"{total_portfolio_div:,.2f}", f"Ø {port_yield:.2f}% Rendite")
                        
                        csv_data_port = convert_df_to_csv(df_portfolio.drop(columns=["AssetType", "DistType"]))
                        c3.download_button(label="📥 Portfolio als CSV", data=csv_data_port, file_name='portfolio_analyse.csv', mime='text/csv')
                        st.write("")
                        
                    def style_signal(v):
                        if "Überkauft" in str(v): return 'color: #ff4b4b; font-weight: bold'
                        if "Überverkauft" in str(v): return 'color: #00ff00; font-weight: bold'
                        return ''
                        
                    def style_empf(v):
                        if "KAUF" in str(v): return 'color: #00ff00; font-weight: bold'
                        if "VERKAUF" in str(v): return 'color: #ff4b4b; font-weight: bold'
                        if "Aufwärts" in str(v): return 'color: #a8ffb2;'
                        if "Abwärts" in str(v): return 'color: #ffa8a8;'
                        return ''
                    
                    def style_perf(v):
                        if isinstance(v, (int, float)):
                            if v > 0: return 'color: #00ff00'
                            if v < 0: return 'color: #ff4b4b'
                        return ''
                    
                    def render_table(df_subset, is_watchlist=False):
                        if df_subset.empty: return
                        cols_to_drop = ["Trefferquote", "AssetType", "DistType", "Sector", "Country"]
                        if is_watchlist: cols_to_drop.append("Wert")
                            
                        df_show = df_subset.drop(columns=cols_to_drop, errors='ignore')
                        
                        try:
                            styled_df = df_show.style.hide(axis="index") \
                                                     .map(style_signal, subset=['Signal']) \
                                                     .map(style_empf, subset=['Empfehlung']) \
                                                     .map(style_perf, subset=['1T %', '1M %', '3M %', '1J %']) \
                                                     .format(precision=2)
                        except AttributeError:
                            styled_df = df_show.style.hide_index() \
                                                     .applymap(style_signal, subset=['Signal']) \
                                                     .applymap(style_empf, subset=['Empfehlung']) \
                                                     .applymap(style_perf, subset=['1T %', '1M %', '3M %', '1J %']) \
                                                     .format(precision=2)
                        
                        st.table(styled_df)

                    if not df_portfolio.empty:
                        for a_type in ["Aktie", "ETF"]:
                            st.markdown(f"### 🏢 {a_type}n" if a_type == "Aktie" else f"### 📦 {a_type}s")
                            for d_type in ["Ausschüttend", "Thesaurierend"]:
                                subset = df_portfolio[(df_portfolio["AssetType"] == a_type) & (df_portfolio["DistType"] == d_type)]
                                if not subset.empty:
                                    emoji = "💸" if d_type == "Ausschüttend" else "🔄"
                                    st.markdown(f"**{emoji} {d_type}**")
                                    render_table(subset, is_watchlist=False)
                            if df_portfolio[df_portfolio["AssetType"] == a_type].empty:
                                st.caption(f"Keine {a_type}n im Portfolio vorhanden.")
                            st.write("") 
                    else: st.info("Dein Portfolio ist noch leer. Füge Aktien mit einer Anzahl > 0 hinzu.")

                    # -----------------------------
                    # BEREICH: WATCHLIST
                    # -----------------------------
                    st.markdown("---")
                    st.subheader("👀 Watchlist (Anzahl = 0)")
                    
                    if not df_watchlist.empty:
                        for a_type in ["Aktie", "ETF"]:
                            st.markdown(f"### 🏢 {a_type}n" if a_type == "Aktie" else f"### 📦 {a_type}s")
                            for d_type in ["Ausschüttend", "Thesaurierend"]:
                                subset = df_watchlist[(df_watchlist["AssetType"] == a_type) & (df_watchlist["DistType"] == d_type)]
                                if not subset.empty:
                                    emoji = "💸" if d_type == "Ausschüttend" else "🔄"
                                    st.markdown(f"**{emoji} {d_type}**")
                                    render_table(subset, is_watchlist=True)
                            if df_watchlist[df_watchlist["AssetType"] == a_type].empty:
                                st.caption(f"Keine {a_type}n auf der Watchlist.")
                            st.write("") 
                    else: st.info("Deine Watchlist ist leer.")

            # -----------------------------
            # BEREICH: PORTFOLIO-ZUSAMMENSETZUNG
            # -----------------------------
            if signal_data and not df_portfolio.empty:
                st.markdown("---")
                st.subheader("📊 Portfolio-Zusammensetzung")
                
                def create_donut(df, column, title):
                    if df["Wert"].sum() > 0:
                        counts = df.groupby(column)["Wert"].sum()
                        title_suffix = " (nach Wert)"
                    else:
                        counts = df[column].value_counts()
                        title_suffix = " (nach Anzahl)"

                    fig_donut = go.Figure(data=[go.Pie(labels=counts.index, values=counts.values, hole=.4)])
                    fig_donut.update_layout(title_text=title + title_suffix, template="plotly_dark", margin=dict(t=50, b=20, l=20, r=20), height=350, showlegend=False)
                    fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                    return fig_donut

                c1, c2 = st.columns(2)
                c3, c4 = st.columns(2)
                c1.plotly_chart(create_donut(df_portfolio, "AssetType", "ETFs vs. Aktien"), use_container_width=True)
                c2.plotly_chart(create_donut(df_portfolio, "DistType", "Ausschüttend vs. Thesaurierend"), use_container_width=True)
                c3.plotly_chart(create_donut(df_portfolio, "Sector", "Sektoren / Kategorien"), use_container_width=True)
                c4.plotly_chart(create_donut(df_portfolio, "Country", "Herkunftsländer"), use_container_width=True)
