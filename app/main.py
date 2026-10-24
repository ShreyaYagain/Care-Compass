import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db.session import init_db
from app.api import health, triage, caregivers, booking, transcribe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    logger.info("Initializing CareCompass database...")
    init_db()
    yield
    # Shutdown logic if any
    logger.info("Shutting down CareCompass...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.MODEL_VERSION,
    description="CareCompass: AI-powered care navigation and caregiver matching REST API",
    lifespan=lifespan,
)

# CORS Middleware (allows Android emulator, localhost, web)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health.router)
app.include_router(triage.router)
app.include_router(caregivers.router)
app.include_router(booking.router)
app.include_router(transcribe.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to CareCompass API",
        "docs": "/docs",
        "health": "/health",
        "model_version": settings.MODEL_VERSION,
    }
