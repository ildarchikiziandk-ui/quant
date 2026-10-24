"""Открытка ко Дню отца: nvra.ru/dayyot — папе Ренату от Ильдара и команды Nuvora."""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from deps import render

from .common import router


@router.get("/dayyot")
@router.get("/dayyot/")
def dayyot(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "packs/v3/dayyot.html")
