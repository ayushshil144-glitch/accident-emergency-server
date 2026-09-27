from twilio.rest import Client
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
import os
import math

app = FastAPI(title="Accident Emergency Server")


# ============================================================
# DATABASE CONNECTION
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

def get_connection():

    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable not found")

    return psycopg2.connect(DATABASE_URL)


# ============================================================
# DATA MODELS
# ============================================================

class HospitalData(BaseModel):
    name: str
    latitude: float
    longitude: float
    phone: str


class AccidentData(BaseModel):
    vehicle_id: str
    impact: str
    latitude: float
    longitude: float
    heart_rate: int
    spo2: int
    driver_response: bool


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    # Hospital table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            phone TEXT
        )
    """)

    # Emergency alert table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emergency_alerts (
            id SERIAL PRIMARY KEY,
            vehicle_id TEXT NOT NULL,
            impact TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            heart_rate INTEGER,
            spo2 INTEGER,
            hospital_name TEXT,
            hospital_phone TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    cursor.close()
    conn.close()


# Create tables when server starts
create_tables()


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def calculate_distance(lat1, lon1, lat2, lon2):

    R = 6371

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)

    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        *
        math.cos(lat2)
        *
        math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return R * c


# ============================================================
# FIND NEAREST HOSPITAL
# ============================================================

def find_nearest_hospital(latitude, longitude):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            latitude,
            longitude,
            phone
        FROM hospitals
    """)

    hospitals = cursor.fetchall()

    cursor.close()
    conn.close()

    nearest = None
    minimum_distance = float("inf")

    for hospital in hospitals:

        distance = calculate_distance(
            latitude,
            longitude,
            hospital[2],
            hospital[3]
        )

        if distance < minimum_distance:

            minimum_distance = distance

            nearest = {
                "id": hospital[0],
                "name": hospital[1],
                "latitude": hospital[2],
                "longitude": hospital[3],
                "phone": hospital[4],
                "distance_km": round(distance, 2)
            }

    return nearest


# ============================================================
# CREATE EMERGENCY ALERT
# ============================================================

def create_emergency_alert(data, hospital):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO emergency_alerts (
            vehicle_id,
            impact,
            latitude,
            longitude,
            heart_rate,
            spo2,
            hospital_name,
            hospital_phone,
            status
        )

        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)

        RETURNING id

    """, (
        data.vehicle_id,
        data.impact,
        data.latitude,
        data.longitude,
        data.heart_rate,
        data.spo2,
        hospital["name"],
        hospital["phone"],
        "PENDING"
    ))

    alert_id = cursor.fetchone()[0]

    conn.commit()

    cursor.close()
    conn.close()

    return alert_id


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "message": "Accident Emergency Server is running",
        "database": "PostgreSQL"
    }


# ============================================================
# ADD HOSPITAL
# ============================================================

@app.post("/api/hospitals")
def add_hospital(hospital: HospitalData):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO hospitals (
            name,
            latitude,
            longitude,
            phone
        )

        VALUES (%s, %s, %s, %s)

        RETURNING id

    """, (
        hospital.name,
        hospital.latitude,
        hospital.longitude,
        hospital.phone
    ))

    hospital_id = cursor.fetchone()[0]

    conn.commit()

    cursor.close()
    conn.close()

    return {
        "success": True,
        "message": "Hospital added successfully",
        "hospital_id": hospital_id
    }


# ============================================================
# VIEW ALL HOSPITALS
# ============================================================

@app.get("/api/hospitals")
def get_hospitals():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            latitude,
            longitude,
            phone
        FROM hospitals

        ORDER BY id
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    hospitals = []

    for row in rows:

        hospitals.append({
            "id": row[0],
            "name": row[1],
            "latitude": row[2],
            "longitude": row[3],
            "phone": row[4]
        })

    return hospitals


# ============================================================
# UPDATE HOSPITAL
# ============================================================

@app.put("/api/hospitals/{hospital_id}")
def update_hospital(
    hospital_id: int,
    hospital: HospitalData
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE hospitals

        SET
            name = %s,
            latitude = %s,
            longitude = %s,
            phone = %s

        WHERE id = %s

        RETURNING id

    """, (
        hospital.name,
        hospital.latitude,
        hospital.longitude,
        hospital.phone,
        hospital_id
    ))

    updated = cursor.fetchone()

    conn.commit()

    cursor.close()
    conn.close()

    if updated is None:

        raise HTTPException(
            status_code=404,
            detail="Hospital not found"
        )

    return {
        "success": True,
        "message": "Hospital updated successfully"
    }


# ============================================================
# DELETE HOSPITAL
# ============================================================

@app.delete("/api/hospitals/{hospital_id}")
def delete_hospital(hospital_id: int):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM hospitals
        WHERE id = %s
        RETURNING id
    """, (hospital_id,))

    deleted = cursor.fetchone()

    conn.commit()

    cursor.close()
    conn.close()

    if deleted is None:

        raise HTTPException(
            status_code=404,
            detail="Hospital not found"
        )

    return {
        "success": True,
        "message": "Hospital deleted successfully"
    }


# ============================================================
# RECEIVE ACCIDENT
# ============================================================

@app.post("/api/accident")
def receive_accident(data: AccidentData):

    print("\n=======================================")
    print("          ACCIDENT RECEIVED")
    print("=======================================")

    print("Vehicle:", data.vehicle_id)
    print("Impact:", data.impact)

    print(
        "Location:",
        data.latitude,
        ",",
        data.longitude
    )

    print("Heart Rate:", data.heart_rate)
    print("SpO2:", data.spo2)
    print("Driver Response:", data.driver_response)

    # Find nearest hospital
    hospital = find_nearest_hospital(
        data.latitude,
        data.longitude
    )

    if hospital is None:

        return {
            "success": False,
            "message": "No hospitals available"
        }

    print("\n---------- NEAREST HOSPITAL ----------")

    print("Hospital:", hospital["name"])
    print("Distance:", hospital["distance_km"], "km")
    print("Phone:", hospital["phone"])

    # Create emergency alert
    alert_id = create_emergency_alert(
        data,
        hospital
    )

    print("\n=======================================")
    print("          EMERGENCY ALERT")
    print("=======================================")

    print("Alert ID:", alert_id)
    print("Vehicle:", data.vehicle_id)
    print("Accident Type:", data.impact)

    print(
        "Location:",
        data.latitude,
        ",",
        data.longitude
    )

    print("Heart Rate:", data.heart_rate, "BPM")
    print("SpO2:", data.spo2, "%")

    print("\nSEND TO:")
    print("Hospital:", hospital["name"])
    print("Phone:", hospital["phone"])

    print("\nStatus: PENDING")
    print("=======================================\n")

    return {
        "success": True,
        "message": "Emergency alert created",
        "alert_id": alert_id,
        "vehicle_id": data.vehicle_id,
        "nearest_hospital": hospital,
        "alert_status": "PENDING"
    }


# ============================================================
# VIEW EMERGENCY ALERTS
# ============================================================

@app.get("/api/alerts")
def get_alerts():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            vehicle_id,
            impact,
            latitude,
            longitude,
            heart_rate,
            spo2,
            hospital_name,
            hospital_phone,
            status,
            created_at

        FROM emergency_alerts

        ORDER BY id DESC
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    alerts = []

    for row in rows:

        alerts.append({
            "alert_id": row[0],
            "vehicle_id": row[1],
            "impact": row[2],
            "latitude": row[3],
            "longitude": row[4],
            "heart_rate": row[5],
            "spo2": row[6],
            "hospital_name": row[7],
            "hospital_phone": row[8],
            "status": row[9],
            "created_at": row[10]
        })

    return alerts
