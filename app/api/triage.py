from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.schemas import TriageRequest, TriageResponse
from app.db.session import get_db
from app.core.pipeline import run_triage_pipeline

router = APIRouter(tags=["Triage"])


@router.post("/triage", response_model=TriageResponse)
def triage_endpoint(request: TriageRequest, debug: bool = False, db: Session = Depends(get_db)):
    return run_triage_pipeline(request, db=db, debug=debug)
