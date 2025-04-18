from typing import Any, Dict, List, Optional, Type, TypeVar, Union, Generic
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

from app.utils.pagination import paginate, PaginatedResponse

ModelType = TypeVar("ModelType", bound=DeclarativeBase)
SchemaType = TypeVar("SchemaType", bound=BaseModel)


def build_sort(sort: str, order: str) -> Dict[str, Any]:
    """
    Build sort dictionary for query.
    """
    return {sort: order}


async def list_init_options(request: Request) -> Dict[str, Any]:
    """
    Initialize options for listing items.
    """
    query_params = dict(request.query_params)
    order = query_params.get("order", "asc")
    sort = query_params.get("sort", "created_at")
    sort_by = build_sort(sort, order)
    page = int(query_params.get("page", "1"))
    limit = int(query_params.get("limit", "10"))
    
    return {
        "order": order,
        "sort": sort_by,
        "page": page,
        "limit": limit,
    }


async def check_query_string(query_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process query parameters for filtering.
    """
    queries = {}
    filter_value = query_params.get("filter")
    fields = query_params.get("fields")
    
    # Copy other query params except filter, fields, and page
    for key, value in query_params.items():
        if key not in ["filter", "fields", "page", "limit", "order", "sort"]:
            queries[key] = value
    
    try:
        if filter_value and fields:
            field_list = fields.split(",")
            filter_conditions = []
            
            for field in field_list:
                filter_conditions.append({field: {"ilike": f"%{filter_value}%"}})
            
            # Return combined filter conditions with other queries
            return {"filter_conditions": filter_conditions, **queries}
        else:
            return queries
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error with filter: {str(e)}")


async def get_all_items(db: AsyncSession, model: Type[ModelType]) -> List[ModelType]:
    """
    Get all items from a model.
    """
    query = select(model).order_by(model.id)
    result = await db.execute(query)
    return result.scalars().all()


async def get_items(
    db: AsyncSession, 
    model: Type[ModelType],
    request: Request,
    query_params: Dict[str, Any]
) -> PaginatedResponse:
    """
    Get items with pagination and filtering.
    """
    options = await list_init_options(request)
    page = options["page"]
    limit = options["limit"]
    
    # Build base query
    query = select(model)
    
    # Apply filters
    filter_conditions = query_params.pop("filter_conditions", None)
    if filter_conditions:
        filter_clauses = []
        for condition in filter_conditions:
            for field, value in condition.items():
                column = getattr(model, field)
                if "ilike" in value:
                    filter_clauses.append(column.ilike(value["ilike"]))
        
        if filter_clauses:
            query = query.where(or_(*filter_clauses))
    
    # Apply other filters
    for field, value in query_params.items():
        if hasattr(model, field):
            query = query.where(getattr(model, field) == value)
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.execute(count_query)
    total_count = total.scalar() or 0
    
    # Apply pagination
    query = query.offset((page - 1) * limit).limit(limit)
    
    # Apply sorting
    sort_field = options["sort"]
    for field, direction in sort_field.items():
        column = getattr(model, field)
        if direction.lower() == "desc":
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())
    
    # Execute query
    result = await db.execute(query)
    items = result.scalars().all()
    
    # Return paginated response
    return paginate(items=items, total=total_count, page=page, size=limit)


async def get_item(db: AsyncSession, model: Type[ModelType], id: int) -> Optional[ModelType]:
    """
    Get a single item by ID.
    """
    query = select(model).where(model.id == id)
    result = await db.execute(query)
    item = result.scalars().first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return item


async def filter_items(db: AsyncSession, model: Type[ModelType], filters: Dict[str, Any]) -> List[ModelType]:
    """
    Filter items by fields.
    """
    query = select(model)
    
    for field, value in filters.items():
        if hasattr(model, field):
            query = query.where(getattr(model, field) == value)
    
    result = await db.execute(query)
    return result.scalars().all()


async def create_item(db: AsyncSession, model: Type[ModelType], data: Dict[str, Any]) -> ModelType:
    """
    Create a new item.
    """
    try:
        db_item = model(**data)
        db.add(db_item)
        await db.commit()
        await db.refresh(db_item)
        return db_item
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Error creating item: {str(e)}")


async def update_item(db: AsyncSession, model: Type[ModelType], id: int, data: Dict[str, Any]) -> ModelType:
    """
    Update an existing item.
    """
    item = await get_item(db, model, id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    for field, value in data.items():
        if hasattr(item, field):
            setattr(item, field, value)
    
    try:
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Error updating item: {str(e)}")


async def delete_item(db: AsyncSession, model: Type[ModelType], id: int) -> ModelType:
    """
    Delete an item.
    """
    item = await get_item(db, model, id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    try:
        await db.delete(item)
        await db.commit()
        return item
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Error deleting item: {str(e)}") 