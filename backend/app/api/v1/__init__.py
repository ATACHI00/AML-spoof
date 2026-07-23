"""AML Monitor — API v1 routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.transactions import router as transactions_router
from app.api.v1.rules import router as rules_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.sanctions import router as sanctions_router
from app.api.v1.ml import router as ml_router
from app.api.v1.graph import router as graph_router
from app.api.v1.audit import router as audit_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.exchanges import router as exchanges_router
from app.api.v1.wallets import router as wallets_router

router = APIRouter()
router.include_router(transactions_router)
router.include_router(rules_router)
router.include_router(alerts_router)
router.include_router(sanctions_router)
router.include_router(ml_router)
router.include_router(graph_router)
router.include_router(audit_router)
router.include_router(compliance_router)
router.include_router(exchanges_router)
router.include_router(wallets_router)