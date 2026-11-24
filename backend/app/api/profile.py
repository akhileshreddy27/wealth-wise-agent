from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import services
from app.db import Profile, get_db
from app.engine.risk import QUESTIONNAIRE, compute_risk

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileIn(BaseModel):
    name: str = Field("", max_length=80)
    age: int = Field(ge=18, le=90)
    monthly_income: float = Field(ge=0)
    monthly_expenses: float = Field(ge=0)
    current_savings: float = Field(ge=0)
    horizon_years: int = Field(ge=1, le=40)
    dependents: int = Field(0, ge=0, le=10)
    answers: dict[str, int]


@router.get("/questionnaire")
def questionnaire():
    return QUESTIONNAIRE


@router.get("")
def read_profile(db: Session = Depends(get_db)):
    p = services.get_profile(db)
    return services.profile_dict(p) if p else None


@router.put("")
def save_profile(body: ProfileIn, db: Session = Depends(get_db)):
    try:
        score, category = compute_risk(body.answers, body.age, body.horizon_years, body.dependents,
                                       body.monthly_expenses, body.current_savings)
    except ValueError as e:
        raise HTTPException(422, str(e))
    p = services.get_profile(db) or Profile(id=1)
    for key, value in body.model_dump().items():
        setattr(p, key, value)
    p.risk_score, p.risk_category, p.updated_at = score, category, datetime.now(timezone.utc)
    db.add(p)
    db.commit()
    return services.profile_dict(p)
