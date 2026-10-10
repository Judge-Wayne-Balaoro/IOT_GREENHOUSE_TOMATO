from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Greenhouse(Base):
    __tablename__ = "greenhouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    plants = relationship("Plant", back_populates="greenhouse")
    readings = relationship("EnvironmentReading", back_populates="greenhouse")


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    greenhouse_id: Mapped[int] = mapped_column(ForeignKey("greenhouses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    greenhouse = relationship("Greenhouse", back_populates="plants")
    # Legacy growth records are retained for backward compatibility only.
    growth_records = relationship("PlantGrowth", back_populates="plant")
    manual_growth_records = relationship("ManualGrowthMeasurement", back_populates="plant")
    ultrasonic_tests = relationship("UltrasonicTest", back_populates="plant")


class EnvironmentReading(Base):
    __tablename__ = "environment_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    greenhouse_id: Mapped[int] = mapped_column(ForeignKey("greenhouses.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_moisture_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    light_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pump_status: Mapped[bool] = mapped_column(Boolean, default=False)
    fan_status: Mapped[bool] = mapped_column(Boolean, default=False)
    grow_light_status: Mapped[bool] = mapped_column(Boolean, default=False)

    greenhouse = relationship("Greenhouse", back_populates="readings")


class PlantGrowth(Base):
    """Legacy ESP32 height records created before ultrasonic data was separated."""
    __tablename__ = "plant_growth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    plant = relationship("Plant", back_populates="growth_records")


class ManualGrowthMeasurement(Base):
    """Official plant-height measurements entered from a ruler."""
    __tablename__ = "manual_growth_measurements"
    __table_args__ = (Index("ix_manual_growth_plant_recorded", "plant_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    plant = relationship("Plant", back_populates="manual_growth_records")


class UltrasonicTest(Base):
    """Experimental ultrasonic distance/height measurements, not official growth data."""
    __tablename__ = "ultrasonic_tests"
    __table_args__ = (Index("ix_ultrasonic_plant_recorded", "plant_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distance_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    plant = relationship("Plant", back_populates="ultrasonic_tests")
