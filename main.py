from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
import math


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(title="Accident Emergency Server")

DATABASE = "hospitals.db"


# ============================================================
# ACCIDENT DATA FORMAT
# ============================================================

class AccidentData(BaseModel):
    vehicle_id: str
    impact: str
    latitude: float
    longitude: float
    heart_rate: int
    spo2: int
    driver_response: bool


# ============================================================
# CREATE DATABASE
# ============================================================

def create_database():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Hospital Table
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            phone TEXT
        )
    """)

    # --------------------------------------------------------
    # Emergency Alert Table
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emergency_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            impact TEXT,
            latitude REAL,
            longitude REAL,
            heart_rate INTEGER,
            spo2 INTEGER,
            hospital_name TEXT,
            hospital_phone TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --------------------------------------------------------
    # Add test hospitals if database is empty
    # --------------------------------------------------------

    cursor.execute("SELECT COUNT(*) FROM hospitals")

    count = cursor.fetchone()[0]

    if count == 0:

        hospitals = [

            (
                "Hospital A",
                22.750000,
                88.375000,
                "TEST001"
            ),

            (
                "Hospital B",
                22.745000,
                88.380000,
                "TEST002"
            ),

            (
                "Hospital C",
                22.760000,
                88.390000,
                "TEST003"
            )
        ]

        cursor.executemany("""
            INSERT INTO hospitals (
                name,
                latitude,
                longitude,
                phone
            )
            VALUES (?, ?, ?, ?)
        """, hospitals)

    conn.commit()

    conn.close()


# ============================================================
# DISTANCE CALCULATION
# HAVERSINE FORMULA
# ============================================================

def calculate_distance(lat1, lon1, lat2, lon2):

    # Radius of Earth in kilometers
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

    distance = R * c

    return distance


# ============================================================
# FIND NEAREST HOSPITAL
# ============================================================

def find_nearest_hospital(latitude, longitude):

    conn = sqlite3.connect(DATABASE)

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

    conn.close()

    nearest = None

    minimum_distance = float("inf")

    for hospital in hospitals:

        hospital_id = hospital[0]
        name = hospital[1]
        hospital_lat = hospital[2]
        hospital_lon = hospital[3]
        phone = hospital[4]

        distance = calculate_distance(
            latitude,
            longitude,
            hospital_lat,
            hospital_lon
        )

        if distance < minimum_distance:

            minimum_distance = distance

            nearest = {
                "id": hospital_id,
                "name": name,
                "latitude": hospital_lat,
                "longitude": hospital_lon,
                "phone": phone,
                "distance_km": round(distance, 2)
            }

    return nearest


# ============================================================
# CREATE EMERGENCY ALERT
# ============================================================

def create_emergency_alert(data, hospital):

    conn = sqlite3.connect(DATABASE)

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

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

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

    alert_id = cursor.lastrowid

    conn.commit()

    conn.close()

    return alert_id


# ============================================================
# CREATE DATABASE WHEN SERVER STARTS
# ============================================================

create_database()


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "message": "Accident Emergency Server is running"
    }


# ============================================================
# VIEW ALL HOSPITALS
# ============================================================

@app.get("/api/hospitals")
def get_hospitals():

    conn = sqlite3.connect(DATABASE)

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

    conn.close()

    return hospitals


# ============================================================
# RECEIVE ACCIDENT FROM VEHICLE
# ============================================================

@app.post("/api/accident")
def receive_accident(data: AccidentData):

    print("\n")
    print("=======================================")
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


    # --------------------------------------------------------
    # Find nearest hospital
    # --------------------------------------------------------

    hospital = find_nearest_hospital(
        data.latitude,
        data.longitude
    )


    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    if hospital is None:

        print("No hospital found in database.")

        return {
            "success": False,
            "message": "No hospital available"
        }


    print("\n")
    print("---------------------------------------")
    print("          NEAREST HOSPITAL")
    print("---------------------------------------")

    print("Hospital:", hospital["name"])

    print(
        "Distance:",
        hospital["distance_km"],
        "km"
    )

    print("Phone:", hospital["phone"])


    # --------------------------------------------------------
    # Create Emergency Alert
    # --------------------------------------------------------

    alert_id = create_emergency_alert(
        data,
        hospital
    )


    # --------------------------------------------------------
    # Display Emergency Alert
    # --------------------------------------------------------

    print("\n")
    print("=======================================")
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

    print(
        "Heart Rate:",
        data.heart_rate,
        "BPM"
    )

    print(
        "SpO2:",
        data.spo2,
        "%"
    )

    print(
        "Driver Response:",
        data.driver_response
    )

    print("\nSEND TO:")

    print(
        "Hospital:",
        hospital["name"]
    )

    print(
        "Phone:",
        hospital["phone"]
    )

    print("\nStatus: PENDING")

    print("=======================================")
    print("\n")


    # --------------------------------------------------------
    # Send response back to ESP
    # --------------------------------------------------------

    return {

        "success": True,

        "message":
            "Emergency alert created successfully",

        "alert_id":
            alert_id,

        "vehicle_id":
            data.vehicle_id,

        "nearest_hospital":
            hospital,

        "alert_status":
            "PENDING"
    }


# ============================================================
# VIEW ALL EMERGENCY ALERTS
# ============================================================

@app.get("/api/alerts")
def get_alerts():

    conn = sqlite3.connect(DATABASE)

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