from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class EnvironmentReadingCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    greenhouse_id: int
    recorded_at: datetime
    temperature_c: float | None = None
    humidity_percent: float | None = None
    soil_moisture_percent: float | None = None
    light_level: int | None = None
    pump_status: bool = False
    fan_status: bool = False
    grow_light_status: bool = False


class PlantGrowthCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    plant_id: int
    recorded_at: datetime
    height_cm: float = Field(gt=0, le=300)


class ManualGrowthCreate(BaseModel):
    plant_id: int
    recorded_at: datetime
    height_cm: float = Field(gt=0, le=300)
    notes: str | None = Field(default=None, max_length=500)


class UltrasonicTestCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    plant_id: int
    recorded_at: datetime
    distance_cm: float | None = Field(default=None, ge=0, le=1000)
    estimated_height_cm: float | None = Field(default=None, ge=0, le=300)
    # Backward-compatible with the current firmware's former height_cm payload.
    height_cm: float | None = Field(default=None, ge=0, le=300)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
