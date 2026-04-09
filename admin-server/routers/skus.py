"""
SKUs router — /api/v1/skus
Read-only view into the local SKU mirror (synced from Feishu 表1).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

import db
from db.models import Sku
from schemas import SkuOut, PagedResponse

router = APIRouter()


@router.get("", response_model=PagedResponse)
def list_skus(
    name: str | None = Query(None, description="Search sku_name / product_alias / sku_code"),
    category: str | None = Query(None),
    listing_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    with Session(db._get_engine()) as s:
        q = select(Sku)
        if name:
            q = q.where(or_(
                Sku.sku_name.ilike(f"%{name}%"),
                Sku.product_alias.ilike(f"%{name}%"),
                Sku.sku_code.ilike(f"%{name}%"),
            ))
        if category:
            q = q.where(Sku.category == category)
        if listing_status:
            q = q.where(Sku.listing_status == listing_status)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = s.execute(
            q.order_by(Sku.updated_at.desc()).offset((page - 1) * limit).limit(limit)
        ).scalars().all()
        return PagedResponse(
            total=total, page=page, limit=limit,
            items=[SkuOut.model_validate(sk) for sk in items],
        )


@router.get("/{sku_id}", response_model=SkuOut)
def get_sku(sku_id: int):
    with Session(db._get_engine()) as s:
        sku = s.get(Sku, sku_id)
        if sku is None:
            raise HTTPException(404, f"SKU id={sku_id} not found")
        return SkuOut.model_validate(sku)
