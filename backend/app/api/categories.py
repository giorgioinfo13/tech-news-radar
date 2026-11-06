from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

from app.api.dependencies import (
    PaginationDep,
    ResourceId,
    SessionDep,
    commit_or_conflict,
    get_or_404,
    paginate,
    require_admin,
)
from app.models import Category
from app.schemas import CategoryCreate, CategoryRead, CategoryUpdate, Page

router = APIRouter(prefix="/categories", tags=["categories"])
CONFLICT = "A category with this name or slug already exists"


@router.get("", response_model=Page[CategoryRead])
def list_categories(session: SessionDep, pagination: PaginationDep):
    return paginate(
        session, select(Category).order_by(Category.sort_order, Category.id), pagination
    )


@router.post(
    "", response_model=CategoryRead, status_code=201, dependencies=[Depends(require_admin)]
)
def create_category(data: CategoryCreate, session: SessionDep):
    category = Category(**data.model_dump())
    session.add(category)
    commit_or_conflict(session, CONFLICT)
    return category


@router.patch("/{category_id}", response_model=CategoryRead, dependencies=[Depends(require_admin)])
def update_category(category_id: ResourceId, data: CategoryUpdate, session: SessionDep):
    category = get_or_404(session, Category, category_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    commit_or_conflict(session, CONFLICT)
    return category


@router.delete("/{category_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_category(category_id: ResourceId, session: SessionDep) -> Response:
    """Delete the category and leave its sources uncategorized. Articles are preserved."""
    session.delete(get_or_404(session, Category, category_id))
    session.commit()
    return Response(status_code=204)
