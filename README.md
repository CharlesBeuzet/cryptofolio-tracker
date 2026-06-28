# Crypto Portfolio Tracker

A lightweight crypto portfolio tracking application designed to run on Raspberry Pi 5. Track your positions across multiple exchanges (Binance, Coinbase) and hot wallets.

## Features

- **Portfolio Overview**: View total portfolio value, today's P&L, asset distribution, and position rankings
- **Performance Analysis**: Track portfolio value evolution over time with BTC comparison
- **Position Details**: In-depth analysis of individual positions with order history
- **Multi-Source Tracking**: Aggregate data from Binance, Coinbase, and hot wallets
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

## Setup Instructions

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
- **Coinbase**: API key, secret, and passphrase
- **Hot Wallets**: Ethereum addresses and token contracts to track

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
    }
  }
}
```

## Security Notes

- All API keys are stored locally in `settings/config.yaml` (gitignored)
- The backend runs locally and is not exposed to the internet by default
- Use read-only API keys for exchanges when possible
- Hot wallet tracking only requires public addresses (no private keys needed)

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
