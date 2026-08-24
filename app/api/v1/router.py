"""API v1 router aggregator."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.customers import router as customers_router
from app.api.v1.disputes import router as disputes_router
from app.api.v1.escalations import router as escalations_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(disputes_router)
api_router.include_router(customers_router)
api_router.include_router(escalations_router)
