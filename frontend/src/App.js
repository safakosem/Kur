import { useState, useEffect } from "react";
import "@/App.css";
import axios from "axios";
import { RefreshCw, TrendingUp, TrendingDown, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const CURRENCY_NAMES = {
  USD: "US Dollar",
  EUR: "Euro",
  GBP: "British Pound",
  CHF: "Swiss Franc",
  XAU: "Gold (Troy Ounce)"
};

const CURRENCY_SYMBOLS = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  CHF: "CHF",
  XAU: "🪙"
};

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
        toast.success("Rates updated successfully");
      }
    } catch (error) {
      console.error("Error fetching rates:", error);
      toast.error("Failed to fetch rates");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRates();
    // Auto-refresh every 1 second if enabled
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
    
    // For buying, customer wants lowest price (best for them to buy)
    // For selling, customer wants highest price (best for them to sell)
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
          <p className="text-lg" data-testid="loading-text">Loading exchange rates...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="App min-h-screen">
      {/* Header */}
      <header className="header-section" data-testid="app-header">
        <div className="container mx-auto px-4 py-8">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-2" data-testid="app-title">
                Döviz Karşılaştırma
              </h1>
              <p className="text-base sm:text-lg opacity-90" data-testid="app-subtitle">
                Anlık kur fiyatlarını karşılaştırın
              </p>
            </div>
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
          {lastUpdate && (
            <p className="text-sm mt-4 opacity-75" data-testid="last-update">
              Son güncelleme: {lastUpdate.toLocaleString('tr-TR')}
            </p>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8" data-testid="main-content">
        {/* Currency Sections */}
        {Object.keys(CURRENCY_NAMES).map(currency => (
          <div key={currency} className="mb-12" data-testid={`currency-section-${currency}`}>
            <div className="currency-header">
              <span className="currency-symbol">{CURRENCY_SYMBOLS[currency]}</span>
              <h2 className="text-2xl font-bold">{CURRENCY_NAMES[currency]}</h2>
              <span className="currency-code">{currency}/TRY</span>
            </div>

            <div className="rates-grid">
              {rates?.sources?.map((source, idx) => (
                <Card 
                  key={idx} 
                  className={`rate-card ${source.status === 'error' ? 'error-card' : ''}`}
                  data-testid={`rate-card-${currency}-${source.source.replace(/\s+/g, '-')}`}
                >
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span className="text-lg" data-testid={`source-name-${idx}`}>{source.source}</span>
                      {source.status === 'error' ? (
                        <Badge variant="destructive" data-testid={`status-error-${idx}`}>
                          <AlertCircle className="w-3 h-3 mr-1" />
                          Hata
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="success-badge" data-testid={`status-success-${idx}`}>
                          Aktif
                        </Badge>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {source.status === 'error' ? (
                      <p className="text-sm text-muted-foreground" data-testid={`error-message-${idx}`}>
                        Veri alınamadı
                      </p>
                    ) : source.rates[currency] ? (
                      <div className="rate-display">
                        <div className="rate-item">
                          <span className="rate-label">Alış</span>
                          <div className="rate-value-container">
                            <span 
                              className={`rate-value ${isBestRate(source.source, currency, 'buy', source.rates[currency].buy) ? 'best-rate' : ''}`}
                              data-testid={`buy-rate-${idx}`}
                            >
                              ₺{source.rates[currency].buy.toFixed(4)}
                            </span>
                            {isBestRate(source.source, currency, 'buy', source.rates[currency].buy) && (
                              <TrendingDown className="w-4 h-4 text-green-600 ml-2" data-testid={`best-buy-icon-${idx}`} />
                            )}
                          </div>
                        </div>
                        <div className="rate-divider"></div>
                        <div className="rate-item">
                          <span className="rate-label">Satış</span>
                          <div className="rate-value-container">
                            <span 
                              className={`rate-value ${isBestRate(source.source, currency, 'sell', source.rates[currency].sell) ? 'best-rate' : ''}`}
                              data-testid={`sell-rate-${idx}`}
                            >
                              ₺{source.rates[currency].sell.toFixed(4)}
                            </span>
                            {isBestRate(source.source, currency, 'sell', source.rates[currency].sell) && (
                              <TrendingUp className="w-4 h-4 text-green-600 ml-2" data-testid={`best-sell-icon-${idx}`} />
                            )}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground" data-testid={`no-data-${idx}`}>
                        Bu kur için veri yok
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ))}
      </main>

      {/* Footer */}
      <footer className="footer-section" data-testid="app-footer">
        <div className="container mx-auto px-4 py-6 text-center">
          <p className="text-sm opacity-75">
            Kurlar kaynaklardan anlık olarak çekilmektedir. Lütfen işlem yapmadan önce ilgili kurumla doğrulayın.
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;