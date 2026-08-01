# Crypto Portfolio Tracker

A lightweight crypto portfolio tracking application designed to run on Raspberry Pi 5. Track your positions across multiple exchanges (Binance, OKX, Coinbase) and hot wallets.

## Features

- **Portfolio Overview**: View total portfolio value, today's P&L, asset distribution, and position rankings
- **Performance Analysis**: Track portfolio value evolution over time with BTC comparison
- **Position Details**: In-depth analysis of individual positions with order history
- **Multi-Source Tracking**: Aggregate data from Binance, OKX, Coinbase, and hot wallets
- **Hourly Updates**: Automatic data synchronization every hour

## Technology Stack

### Backend
- Python 3.11+
- FastAPI with Strawberry GraphQL
- SQLite database
- ccxt for exchange APIs
- web3.py for blockchain wallet queries

### Frontend
- React 18 with TypeScript
- Vite build tool
- Tailwind CSS for styling (SILLAGE design system)
- Apollo Client for GraphQL
- Recharts for data visualization

## Deploy on Raspberry Pi (Docker)

Single container (nginx + FastAPI) for **linux/arm64** (Pi 4/5). Only port **8080** is published; the API listens on loopback inside the container and is reached via nginx (`/graphql`, `/health`).

Prefer building **on the Pi** so you avoid slow QEMU cross-builds from x86/Windows.

1. Clone the repo on the Pi and prepare host data (bind-mounted; survives image updates):

```bash
mkdir -p data
cp settings/config.example.yaml data/config.yaml
# Edit data/config.yaml with your credentials

# Optional: reuse an existing database
# cp /path/to/portfolio.db data/portfolio.db

# If you have no DB yet, create an empty *file* so Docker does not mount a directory:
touch data/portfolio.db
```

2. Build and start:

```bash
docker compose up -d --build
```

3. Open `http://<pi-ip>:8080`

4. Update the app later without losing data:

```bash
git pull
docker compose up -d --build
```

Host mounts: `./data/portfolio.db` → `/app/portfolio.db`, `./data/config.yaml` → `/app/settings/config.yaml`.

## Setup Instructions (local development)

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm or yarn

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure your API keys and wallet addresses:
```bash
cd ../settings
cp config.example.yaml config.yaml
# Edit config.yaml with your actual credentials
```

5. Initialize the database:
```bash
cd ../backend
python -m src.main
# This will create the SQLite database and start the server
```

The backend will run on `http://localhost:8000` and the GraphQL endpoint will be available at `http://localhost:8000/graphql`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The frontend will run on `http://localhost:5173`

## Configuration

Edit `settings/config.yaml` (create from `config.example.yaml`) to configure:

- **Binance**: API key and secret
- **OKX**: API key, secret, and passphrase
- **Coinbase**: API key, secret, and passphrase
- **Ethereum**: public wallet `address` and RPC `hostname` (both required)

**Important**: Never commit `config.yaml` to version control. It contains sensitive API keys.

## Project Structure

```
cryptofolio-tracker/
├── backend/
│   ├── src/
│   │   ├── connectors/     # Data source connectors
│   │   ├── graphql/        # GraphQL schema and resolvers
│   │   ├── models/         # Database models
│   │   ├── services/       # Business logic
│   │   └── main.py         # FastAPI application entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── graphql/        # GraphQL queries and client
│   │   ├── pages/          # Page components
│   │   └── App.tsx
│   └── package.json
└── settings/
    ├── config.example.yaml # Configuration template
    └── config.yaml          # Your actual config (gitignored)
```

## Usage

1. Start the backend server (from `backend/` directory):
```bash
python -m src.main
```

2. Start the frontend development server (from `frontend/` directory):
```bash
npm run dev
```

3. Open your browser to `http://localhost:5173`

4. The scheduler will automatically update portfolio data every hour. You can also manually trigger updates by calling the GraphQL API.

## GraphQL API

The GraphQL endpoint is available at `http://localhost:8000/graphql`. You can use GraphQL Playground or any GraphQL client to explore the API.

Example query:
```graphql
query {
  portfolio {
    totalValue
    todaysPnl
    positions {
      symbol
      quantity
      value
      pnl
      exchange
      tag { id name }
    }
  }
}
```

Conviction tags (per asset × exchange position) are managed via mutations `createTag`, `updateTag`, `deleteTag`, and `setPositionTag`, or in the UI under **Settings**. See `docs/position-tags.md`.

## Security Notes

- All API keys are stored locally in `settings/config.yaml` (gitignored)
- The backend runs locally and is not exposed to the internet by default
- Use read-only API keys for exchanges when possible
- Hot wallet connectors use the same config shape as exchanges; only a public `address` is required (no private keys)

## Performance Considerations for Raspberry Pi 5

- SQLite database (no separate database server)
- Lightweight dependencies
- Efficient data fetching with batch requests
- Frontend code splitting for faster loads
- Hourly updates to reduce API rate limiting

## Troubleshooting

- **Database not found**: Run the backend once to initialize the database
- **Connection errors**: Check that your API keys in `config.yaml` are correct
- **No data showing**: Ensure the scheduler has run at least once (runs hourly, or restart backend)
- **CORS errors**: Make sure backend is running on port 8000 and frontend on 5173

## License

Author: Charles Beuzet
