import { useState, useEffect } from "react";
import "@/App.css";
import axios from "axios";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const CURRENCY_INFO = {
  USD: { name: "Dolar", symbol: "$" },
  EUR: { name: "Euro", symbol: "€" },
  GBP: { name: "Sterlin", symbol: "£" },
  CHF: { name: "Frank", symbol: "CHF" },
  XAU: { name: "Altın", symbol: "🪙" }
};

const CURRENCIES = ['USD', 'EUR', 'GBP', 'CHF', 'XAU'];

function App() {
  const [rates, setRates] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchRates = async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      
      const response = await axios.get(`${API}/rates`);
      setRates(response.data);
      setLastUpdate(new Date(response.data.timestamp));
      
      if (isRefresh) {
        toast.success("Kurlar güncellendi");
      }
    } catch (error) {
      console.error("Error fetching rates:", error);
      toast.error("Kurlar alınamadı");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRates();
    if (autoRefresh) {
      const interval = setInterval(() => fetchRates(true), 1000);
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const getBestRate = (currency, type) => {
    if (!rates || !rates.sources) return null;
    
    const validRates = rates.sources
      .filter(source => source.rates[currency])
      .map(source => ({
        source: source.source,
        rate: source.rates[currency][type]
      }));
    
    if (validRates.length === 0) return null;
    
    const best = type === 'buy' 
      ? validRates.reduce((min, curr) => curr.rate < min.rate ? curr : min)
      : validRates.reduce((max, curr) => curr.rate > max.rate ? curr : max);
    
    return best;
  };

  const isBestRate = (source, currency, type, rate) => {
    const best = getBestRate(currency, type);
    return best && best.source === source && best.rate === rate;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 animate-spin mx-auto text-amber-600 mb-4" />
          <p className="text-lg" data-testid="loading-text">Kurlar yükleniyor...</p>
        </div>
      </div>
    );
  }

  // Split sources into main currencies and gold ounces
  const mainSources = rates?.sources?.slice(0, 4) || [];
  const goldOunceSources = rates?.sources?.slice(4, 6) || [];

  return (
    <div className="App" data-testid="app-container">
      {/* Header */}
      <header className="app-header" data-testid="app-header">
        <div className="header-content">
          <div className="header-left">
            <h1 className="app-title" data-testid="app-title">Döviz Karşılaştırma</h1>
            {lastUpdate && (
              <p className="last-update" data-testid="last-update">
                Son güncelleme: {lastUpdate.toLocaleString('tr-TR')}
              </p>
            )}
          </div>
          <div className="header-actions">
            <Button
              onClick={() => setAutoRefresh(!autoRefresh)}
              variant={autoRefresh ? "default" : "outline"}
              className={autoRefresh ? "toggle-btn active" : "toggle-btn"}
              data-testid="auto-refresh-toggle"
            >
              {autoRefresh ? "Otomatik Yenileme Açık" : "Otomatik Yenileme Kapalı"}
            </Button>
            <Button
              onClick={() => fetchRates(true)}
              disabled={refreshing}
              className="refresh-btn"
              data-testid="refresh-button"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content - Compact Table View */}
      <main className="main-content" data-testid="main-content">
        {/* Main Currency Exchange Rates */}
        <div className="rates-table-container">
          <div className="table-title">Döviz Kurları</div>
          <table className="rates-table">
            <thead>
              <tr>
                <th className="source-header">Kaynak</th>
                {CURRENCIES.map(currency => (
                  <th key={currency} className="currency-header">
                    <div className="currency-header-content">
                      <span className="currency-symbol">{CURRENCY_INFO[currency].symbol}</span>
                      <span className="currency-name">{CURRENCY_INFO[currency].name}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {mainSources.map((source, idx) => (
                <tr key={idx} className="source-row" data-testid={`source-row-${source.source.replace(/\s+/g, '-')}`}>
                  <td className="source-cell">
                    <div className="source-name">{source.source}</div>
                    <div className={`source-status ${source.status}`}>
                      {source.status === 'success' ? '●' : '○'}
                    </div>
                  </td>
                  {CURRENCIES.map(currency => (
                    <td key={currency} className="rate-cell" data-testid={`rate-${currency}-${idx}`}>
                      {source.rates[currency] ? (
                        <div className="rate-content">
                          <div className="rate-row">
                            <span className="rate-label">A:</span>
                            <span 
                              className={`rate-value ${isBestRate(source.source, currency, 'buy', source.rates[currency].buy) ? 'best-rate' : ''}`}
                              data-testid={`buy-${currency}-${idx}`}
                            >
                              {currency === 'XAU' 
                                ? source.rates[currency].buy.toFixed(2)
                                : source.rates[currency].buy.toFixed(4)
                              }
                            </span>
                          </div>
                          <div className="rate-row">
                            <span className="rate-label">S:</span>
                            <span 
                              className={`rate-value ${isBestRate(source.source, currency, 'sell', source.rates[currency].sell) ? 'best-rate' : ''}`}
                              data-testid={`sell-${currency}-${idx}`}
                            >
                              {currency === 'XAU'
                                ? source.rates[currency].sell.toFixed(2)
                                : source.rates[currency].sell.toFixed(4)
                              }
                            </span>
                          </div>
                        </div>
                      ) : (
                        <div className="no-data">-</div>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Gold Ounce Rates - Separate Section */}
        <div className="gold-ounce-section">
          <div className="table-title">Altın Ons Kurları (XAU/USD)</div>
          <div className="gold-combined-card">
            {goldOunceSources[0]?.rates['XAU'] && goldOunceSources[1]?.rates['XAU'] ? (
              <>
                <div className="gold-sources-row">
                  {/* Istanbul */}
                  <div className="gold-source-item">
                    <div className="gold-source-header">
                      <h3 className="gold-source-name">{goldOunceSources[0].source}</h3>
                      <div className={`source-status ${goldOunceSources[0].status}`}>
                        {goldOunceSources[0].status === 'success' ? '●' : '○'}
                      </div>
                    </div>
                    <div className="gold-rates-inline">
                      <div className="gold-rate-item-inline">
                        <span className="gold-rate-label">Alış</span>
                        <span className="gold-rate-value">${goldOunceSources[0].rates['XAU'].buy.toFixed(2)}</span>
                      </div>
                      <div className="gold-rate-divider-inline"></div>
                      <div className="gold-rate-item-inline">
                        <span className="gold-rate-label">Satış</span>
                        <span className="gold-rate-value">${goldOunceSources[0].rates['XAU'].sell.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>

                  {/* London */}
                  <div className="gold-source-item">
                    <div className="gold-source-header">
                      <h3 className="gold-source-name">{goldOunceSources[1].source}</h3>
                      <div className={`source-status ${goldOunceSources[1].status}`}>
                        {goldOunceSources[1].status === 'success' ? '●' : '○'}
                      </div>
                    </div>
                    <div className="gold-rates-inline">
                      <div className="gold-rate-item-inline">
                        <span className="gold-rate-label">Alış</span>
                        <span className="gold-rate-value">${goldOunceSources[1].rates['XAU'].buy.toFixed(2)}</span>
                      </div>
                      <div className="gold-rate-divider-inline"></div>
                      <div className="gold-rate-item-inline">
                        <span className="gold-rate-label">Satış</span>
                        <span className="gold-rate-value">${goldOunceSources[1].rates['XAU'].sell.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Single Sell Difference */}
                <div className="gold-spread-combined">
                  {(() => {
                    const istanbulSell = goldOunceSources[0].rates['XAU'].sell;
                    const londonSell = goldOunceSources[1].rates['XAU'].sell;
                    const sellDiff = (istanbulSell - londonSell).toFixed(2);
                    const sellDiffPercent = ((sellDiff / londonSell) * 100).toFixed(3);
                    const sellDiffTRY = (sellDiff * 31.99).toFixed(2);
                    
                    return (
                      <>
                        <div className="spread-label-group">
                          <span className="spread-label">Satış Farkı (İstanbul - Londra):</span>
                          <div className="spread-values">
                            <span className={`spread-amount ${sellDiff > 0 ? 'positive' : 'negative'}`}>
                              {sellDiff > 0 ? '+' : ''}${sellDiff}
                            </span>
                            <span className="spread-percent">({sellDiff > 0 ? '+' : ''}{sellDiffPercent}%)</span>
                          </div>
                        </div>
                        <div className="spread-try">
                          <span className={`spread-try-amount ${sellDiff > 0 ? 'positive' : 'negative'}`}>
                            {sellDiff > 0 ? '+' : ''}₺{sellDiffTRY} TRY
                          </span>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </>
            ) : (
              <div className="no-data">Veri yok</div>
            )}
          </div>
        </div>

        <div className="legend">
          <span className="legend-item"><span className="best-indicator"></span> En iyi kur</span>
          <span className="legend-item">A: Alış</span>
          <span className="legend-item">S: Satış</span>
        </div>
      </main>
    </div>
  );
}

export default App;