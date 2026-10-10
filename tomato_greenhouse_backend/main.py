import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    Greenhouse, Plant, EnvironmentReading, PlantGrowth,
    ManualGrowthMeasurement, UltrasonicTest,
)
from schemas import EnvironmentReadingCreate, PlantGrowthCreate, ManualGrowthCreate, UltrasonicTestCreate, LoginRequest

app = FastAPI(title="Tomato Greenhouse API", version="2.0.0")

# Set FRONTEND_ORIGINS to comma-separated deployed UI origins in production.
_frontend_origins = [x.strip() for x in os.getenv("FRONTEND_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
)

TOKEN_LIFETIME_SECONDS = 8 * 60 * 60


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign(payload: str) -> str:
    secret = os.getenv("AUTH_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="Set AUTH_SECRET (at least 32 characters) in your backend .env before using login.")
    return _b64(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())


def _make_token(username: str) -> str:
    payload = _b64(json.dumps({"sub": username, "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS}, separators=(",", ":")).encode("utf-8"))
    return payload + "." + _sign(payload)


def require_device_key(x_device_key: str | None = Header(default=None)) -> bool:
    """Protect public ESP32 ingest routes with a shared device key."""
    expected = os.getenv("DEVICE_API_KEY", "")
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="Device ingest is not configured: set DEVICE_API_KEY.")
    if not x_device_key or not hmac.compare_digest(x_device_key, expected):
        raise HTTPException(status_code=401, detail="Invalid device key.")
    return True


def require_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please sign in to access this resource.")
    token = authorization[7:].strip()
    try:
        payload, signature = token.split(".", 1)
        expected = _sign(payload)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if int(claims.get("exp", 0)) < int(time.time()):
            raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.")
        username = claims.get("sub")
        if not username:
            raise ValueError("missing subject")
        return {"username": username}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid sign-in token.")


def _apply_date_filters(query, column, start_date, end_date):
    if start_date is not None:
        query = query.filter(column >= start_date)
    if end_date is not None:
        query = query.filter(column <= end_date)
    return query


@app.get("/")
def root():
    return {"message": "Tomato Greenhouse API is running", "version": "2.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-check")
def db_check():
    try:
        with SessionLocal() as db:
            db.query(Greenhouse).limit(1).all()
        return {"database": "connected"}
    except Exception as exc:
        return {"database": "connection failed", "error": str(exc)}


@app.post("/auth/login")
def login(payload: LoginRequest):
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "")
    if not expected_password:
        raise HTTPException(status_code=503, detail="Set ADMIN_PASSWORD and AUTH_SECRET in your backend .env before signing in.")
    if not hmac.compare_digest(payload.username, expected_user) or not hmac.compare_digest(payload.password, expected_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    token = _make_token(payload.username)
    return {"access_token": token, "token_type": "bearer", "user": {"username": payload.username, "name": "Administrator"}}


# ---------- Environment readings: ESP32 ingest remains unauthenticated ----------
@app.post("/api/readings")
def create_reading(reading: EnvironmentReadingCreate, _device_ok: bool = Depends(require_device_key), db: Session = Depends(get_db)):
    if not db.get(Greenhouse, reading.greenhouse_id):
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if db.query(EnvironmentReading).filter(EnvironmentReading.event_id == reading.event_id).first():
        raise HTTPException(status_code=409, detail="Event ID already exists")
    new_reading = EnvironmentReading(**reading.model_dump())
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    return {"message": "Reading saved", "id": new_reading.id, "event_id": new_reading.event_id}


@app.get("/api/readings")
def get_readings(
    greenhouse_id: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(default=1000, ge=1, le=50000),
    _user: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = db.query(EnvironmentReading)
    if greenhouse_id is not None:
        query = query.filter(EnvironmentReading.greenhouse_id == greenhouse_id)
    query = _apply_date_filters(query, EnvironmentReading.recorded_at, start_date, end_date)
    rows = query.order_by(EnvironmentReading.recorded_at.desc()).limit(limit).all()
    return [_reading_dict(r) for r in rows]


def _reading_dict(r: EnvironmentReading) -> dict:
    return {
        "id": r.id, "event_id": r.event_id, "greenhouse_id": r.greenhouse_id,
        "recorded_at": r.recorded_at, "temperature_c": r.temperature_c,
        "humidity_percent": r.humidity_percent, "soil_moisture_percent": r.soil_moisture_percent,
        "light_level": r.light_level, "pump_status": r.pump_status,
        "fan_status": r.fan_status, "grow_light_status": r.grow_light_status,
    }


@app.get("/api/readings/latest")
def get_latest_reading(
    greenhouse_id: int | None = None,
    _user: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = db.query(EnvironmentReading)
    if greenhouse_id is not None:
        query = query.filter(EnvironmentReading.greenhouse_id == greenhouse_id)
    reading = query.order_by(EnvironmentReading.recorded_at.desc()).first()
    if not reading:
        raise HTTPException(status_code=404, detail="No readings found")
    return _reading_dict(reading)


@app.get("/device/status")
def device_status(_user: dict = Depends(require_user), db: Session = Depends(get_db)):
    reading = db.query(EnvironmentReading).order_by(EnvironmentReading.recorded_at.desc()).first()
    if not reading:
        return {"wifi_connected": False, "last_seen_at": None, "age_seconds": None}
    stamp = reading.recorded_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = max(0, int((datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()))
    return {"wifi_connected": age <= 600, "last_seen_at": reading.recorded_at, "age_seconds": age}


# ---------- Official ruler measurements: used by dashboard/chart/export ----------
@app.post("/api/growth/manual")
def create_manual_growth(data: ManualGrowthCreate, _user: dict = Depends(require_user), db: Session = Depends(get_db)):
    if not db.get(Plant, data.plant_id):
        raise HTTPException(status_code=404, detail="Plant not found")
    record = ManualGrowthMeasurement(
        event_id="RULER-" + uuid.uuid4().hex,
        plant_id=data.plant_id,
        recorded_at=data.recorded_at,
        height_cm=data.height_cm,
        notes=data.notes.strip() if data.notes and data.notes.strip() else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _manual_growth_dict(record)


def _manual_growth_dict(r: ManualGrowthMeasurement) -> dict:
    return {"id": r.id, "event_id": r.event_id, "plant_id": r.plant_id, "recorded_at": r.recorded_at,
            "height_cm": r.height_cm, "notes": r.notes, "method": "ruler"}


@app.get("/api/growth/manual")
def get_manual_growth(
    plant_id: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(default=1000, ge=1, le=50000),
    _user: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = db.query(ManualGrowthMeasurement)
    if plant_id is not None:
        query = query.filter(ManualGrowthMeasurement.plant_id == plant_id)
    query = _apply_date_filters(query, ManualGrowthMeasurement.recorded_at, start_date, end_date)
    rows = query.order_by(ManualGrowthMeasurement.recorded_at.desc()).limit(limit).all()
    return [_manual_growth_dict(r) for r in rows]


@app.get("/api/growth/manual/latest")
def get_latest_manual_growth(plant_id: int | None = None, _user: dict = Depends(require_user), db: Session = Depends(get_db)):
    query = db.query(ManualGrowthMeasurement)
    if plant_id is not None:
        query = query.filter(ManualGrowthMeasurement.plant_id == plant_id)
    row = query.order_by(ManualGrowthMeasurement.recorded_at.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="No ruler measurements have been recorded yet")
    return _manual_growth_dict(row)


# ---------- Experimental ultrasonic readings: kept separate from official growth ----------
@app.post("/api/ultrasonic-tests")
def create_ultrasonic_test(data: UltrasonicTestCreate, _device_ok: bool = Depends(require_device_key), db: Session = Depends(get_db)):
    if not db.get(Plant, data.plant_id):
        raise HTTPException(status_code=404, detail="Plant not found")
    if db.query(UltrasonicTest).filter(UltrasonicTest.event_id == data.event_id).first():
        raise HTTPException(status_code=409, detail="Event ID already exists")
    estimated = data.estimated_height_cm if data.estimated_height_cm is not None else data.height_cm
    if data.distance_cm is None and estimated is None:
        raise HTTPException(status_code=422, detail="Provide distance_cm or estimated_height_cm")
    row = UltrasonicTest(event_id=data.event_id, plant_id=data.plant_id, recorded_at=data.recorded_at,
                         distance_cm=data.distance_cm, estimated_height_cm=estimated)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _ultrasonic_dict(row)


def _ultrasonic_dict(r: UltrasonicTest) -> dict:
    return {"id": r.id, "event_id": r.event_id, "plant_id": r.plant_id, "recorded_at": r.recorded_at,
            "distance_cm": r.distance_cm, "estimated_height_cm": r.estimated_height_cm,
            "classification": "experimental - not official plant height"}


@app.get("/api/ultrasonic-tests")
def get_ultrasonic_tests(
    plant_id: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(default=1000, ge=1, le=50000),
    _user: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = db.query(UltrasonicTest)
    if plant_id is not None:
        query = query.filter(UltrasonicTest.plant_id == plant_id)
    query = _apply_date_filters(query, UltrasonicTest.recorded_at, start_date, end_date)
    rows = query.order_by(UltrasonicTest.recorded_at.desc()).limit(limit).all()
    return [_ultrasonic_dict(r) for r in rows]


# ---------- Legacy endpoints kept for older clients/data; not used for official chart ----------
@app.post("/api/growth")
def create_legacy_growth(growth: PlantGrowthCreate, _device_ok: bool = Depends(require_device_key), db: Session = Depends(get_db)):
    if not db.get(Plant, growth.plant_id):
        raise HTTPException(status_code=404, detail="Plant not found")
    if db.query(PlantGrowth).filter(PlantGrowth.event_id == growth.event_id).first():
        raise HTTPException(status_code=409, detail="Event ID already exists")
    record = PlantGrowth(**growth.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"message": "Legacy growth record saved", "id": record.id, "event_id": record.event_id}


@app.get("/api/growth")
def get_legacy_growth(
    plant_id: int | None = None,
    limit: int = Query(default=1000, ge=1, le=50000),
    _user: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = db.query(PlantGrowth)
    if plant_id is not None:
        query = query.filter(PlantGrowth.plant_id == plant_id)
    rows = query.order_by(PlantGrowth.recorded_at.desc()).limit(limit).all()
    return [{"id": r.id, "event_id": r.event_id, "plant_id": r.plant_id, "recorded_at": r.recorded_at,
             "height_cm": r.height_cm, "classification": "legacy - not official ruler measurement"} for r in rows]


@app.get("/api/growth/latest")
def get_legacy_latest_growth(plant_id: int | None = None, _user: dict = Depends(require_user), db: Session = Depends(get_db)):
    query = db.query(PlantGrowth)
    if plant_id is not None:
        query = query.filter(PlantGrowth.plant_id == plant_id)
    row = query.order_by(PlantGrowth.recorded_at.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="No legacy growth records found")
    return {"id": row.id, "event_id": row.event_id, "plant_id": row.plant_id, "recorded_at": row.recorded_at,
            "height_cm": row.height_cm, "classification": "legacy - not official ruler measurement"}
