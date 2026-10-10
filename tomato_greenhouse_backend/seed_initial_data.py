"""Ensure the deployed DB contains the IDs the current device/frontend expect."""
from sqlalchemy import text
from database import SessionLocal
from models import Greenhouse, Plant

GREENHOUSE_ID = 6
PLANT_ID = 1

with SessionLocal() as db:
    greenhouse = db.get(Greenhouse, GREENHOUSE_ID)
    if greenhouse is None:
        db.add(Greenhouse(id=GREENHOUSE_ID, name="Tomato Greenhouse"))
        db.flush()
        print(f"Created greenhouse id={GREENHOUSE_ID}")
    else:
        print(f"Greenhouse id={GREENHOUSE_ID} already exists")

    plant = db.get(Plant, PLANT_ID)
    if plant is None:
        db.add(Plant(id=PLANT_ID, greenhouse_id=GREENHOUSE_ID, name="Tomato Plant"))
        db.flush()
        print(f"Created plant id={PLANT_ID}")
    else:
        print(f"Plant id={PLANT_ID} already exists")

    # Explicit IDs are used above; advance PostgreSQL sequences to avoid collisions.
    db.execute(text("SELECT setval(pg_get_serial_sequence('greenhouses', 'id'), (SELECT COALESCE(MAX(id), 1) FROM greenhouses), true)"))
    db.execute(text("SELECT setval(pg_get_serial_sequence('plants', 'id'), (SELECT COALESCE(MAX(id), 1) FROM plants), true)"))
    db.commit()
