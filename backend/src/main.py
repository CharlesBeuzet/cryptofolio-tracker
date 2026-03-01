"""Main FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from .graphql.schema import schema
from .models.database import init_db
from .services.scheduler import DataUpdateScheduler

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(title="Crypto Portfolio Tracker API")

# Configure CORS for localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite and React default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GraphQL endpoint
graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")

# Initialize and start scheduler
scheduler = DataUpdateScheduler()
scheduler.start()


@app.get("/")
def root():
    """Root endpoint."""
    return {"message": "Crypto Portfolio Tracker API", "graphql": "/graphql"}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

