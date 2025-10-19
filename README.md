# 📊 Döviz Karşılaştırma - Exchange Rate Comparison

Real-time currency and gold exchange rate comparison application with web, mobile (PWA), and desktop support.

## 🌟 Features

- **Real-time Exchange Rates**: USD, EUR, GBP, CHF, and XAU (Gold) from 4 Turkish exchange bureaus
- **Auto-refresh**: Rates update every second (can be toggled)
- **Best Rate Highlighting**: Green indicators show the best buy/sell rates
- **Gold Ounce Comparison**: Compare Istanbul and London gold ounce prices (XAU/USD)
- **Built-in Calculator**: Standalone general-purpose calculator
- **Responsive Design**: Works perfectly on desktop, tablet, and mobile
- **PWA Support**: Install on mobile devices as a native-like app
- **Desktop Apps**: Native applications for Windows and Mac
- **Offline Support**: Service worker enables offline functionality

## 🚀 Quick Start

### Prerequisites

**Backend:**
- Python 3.8+
- FastAPI
- Playwright
- MongoDB

**Frontend:**
- Node.js 14+
- Yarn
- React 19

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd doviz-karsilastirma
```

2. **Backend Setup**
```bash
cd backend
pip install -r requirements.txt
playwright install chromium
python server.py
```

3. **Frontend Setup**
```bash
cd frontend
yarn install
yarn start
```

The app will open at `http://localhost:3000`

## 📱 PWA (Progressive Web App)

### Install on iOS
1. Open the app in Safari
2. Tap the Share button (↑)
3. Select "Add to Home Screen"
4. Tap "Add"

### Install on Android
1. Open the app in Chrome
2. Tap the menu (⋮)
3. Select "Install app" or "Add to home screen"
4. Tap "Install"

## 💻 Desktop Applications

### Build Desktop Apps

**For Development:**
```bash
cd frontend
yarn electron-dev
```

**Build for Windows:**
```bash
yarn electron-build-win
```

**Build for Mac:**
```bash
yarn electron-build-mac
```

**Build for Linux:**
```bash
yarn electron-build-linux
```

### Desktop Installation

See `/frontend/public/user-guide.html` for detailed installation instructions.

## 📖 Documentation

Full user guide is available at `/frontend/public/user-guide.html`

## 🛠️ Tech Stack

**Frontend:**
- React 19, Tailwind CSS, Electron

**Backend:**
- FastAPI, Playwright, MongoDB

## 📄 License

MIT License
