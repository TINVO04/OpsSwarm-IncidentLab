from fastapi import APIRouter
from .incidentlab import router as incidentlab_router
from .lab import router as legacy_router

router = APIRouter()
router.include_router(incidentlab_router)
router.include_router(legacy_router)
