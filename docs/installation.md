# Installation

Choose **Docker on a Raspberry Pi** for production-style self-hosting, or **local development** if you are hacking on the code.

## Deploy on Raspberry Pi (Docker)

Single container (nginx + FastAPI) for **linux/arm64** (Pi 4/5). Only port **8080** is published; the API listens on loopback inside the container and is reached via nginx (`/graphql`, `/health`).

Prefer building **on the Pi** so you avoid slow QEMU cross-builds from x86/Windows.

### 1. Prepare host data

Clone the repo on the Pi, then create bind-mounted data (survives image updates):

```bash
mkdir -p data
cp settings/config.example.yaml data/config.yaml
# Edit data/config.yaml with your credentials

# Optional: reuse an existing database
# cp /path/to/portfolio.db data/portfolio.db

# If you have no DB yet, create an empty *file* so Docker does not mount a directory:
touch data/portfolio.db
```

### 2. Build and start

```bash
docker compose up -d --build
```

### 3. Open the UI

Open `http://<pi-ip>:8080`

### 4. Update later without losing data

```bash
git pull
docker compose up -d --build
```

### Host mounts

| Host | Container |
|------|-----------|
| `./data/portfolio.db` | `/app/portfolio.db` |
| `./data/config.yaml` | `/app/settings/config.yaml` |

---

## Local development

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm or yarn

### Backend setup

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

4. Configure API keys and wallet addresses:

```bash
cd ../settings
cp config.example.yaml config.yaml
# Edit config.yaml with your actual credentials
```

5. Start the backend (creates the SQLite database on first run):

```bash
cd ../backend
python -m src.main
```

- Backend: `http://localhost:8000`
- GraphQL: `http://localhost:8000/graphql`

### Frontend setup

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

Frontend: `http://localhost:5173` (proxies GraphQL to the backend on port 8000)

---

Next: [Configuration](configuration.md) · [Usage](usage.md) · [Troubleshooting](troubleshooting.md)

← [Docs hub](README.md)
