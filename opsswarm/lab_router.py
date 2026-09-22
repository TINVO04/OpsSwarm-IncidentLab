from fastapi import APIRouter
from .lab import router as lab_router

router = APIRouter()
router.include_router(lab_router)
