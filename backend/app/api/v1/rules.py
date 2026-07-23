"""AML Monitor — Rule management API endpoints.

CRUD for configurable detection rules.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.models.rule import Rule
from app.schemas.rule import (
    RuleCreate,
    RuleListResponse,
    RuleResponse,
    RuleUpdate,
)

router = APIRouter(prefix="/rules", tags=["rules"])


def _build_response(rule: Rule) -> RuleResponse:
    """Convert a Rule ORM instance to a RuleResponse."""
    return RuleResponse(
        id=str(rule.id),
        name=rule.name,
        slug=rule.slug,
        description=rule.description,
        detector_type=rule.detector_type,
        config=rule.config,
        weight=rule.weight,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/", response_model=RuleListResponse)
async def list_rules(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RuleListResponse:
    """List all rules."""
    result = await db.execute(select(Rule).order_by(Rule.created_at))
    rules = list(result.scalars().all())
    return RuleListResponse(
        rules=[_build_response(r) for r in rules],
        total=len(rules),
    )


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RuleResponse:
    """Get a single rule by ID."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule not found: {rule_id}",
        )
    return _build_response(rule)


@router.post("/", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RuleResponse:
    """Create a new rule."""
    # Check slug uniqueness
    result = await db.execute(select(Rule).where(Rule.slug == payload.slug))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule with slug '{payload.slug}' already exists",
        )

    rule = Rule(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        detector_type=payload.detector_type,
        config=payload.config,
        weight=payload.weight,
        is_active=payload.is_active,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return _build_response(rule)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    payload: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RuleResponse:
    """Update an existing rule."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule not found: {rule_id}",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.flush()
    await db.refresh(rule)
    return _build_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Delete a rule."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule not found: {rule_id}",
        )
    await db.delete(rule)
    await db.commit()
    return None