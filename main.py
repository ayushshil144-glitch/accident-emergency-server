from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from twilio.rest import Client

import psycopg2
import os
import math
import secrets


# ============================================================
# APP
# Disable default Swagger/OpenAPI URLs.
# We create protected versions ourselves below.
# ============================================================

app = FastAPI(
    title="Accident Emergency Server",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

DEVICE_API_KEY = os.getenv("DEVICE_API_KEY")


# ============================================================
# SECURITY
# ============================================================

security = HTTPBasic()


def verify_admin(
    credentials: HTTPBasicCredentials = Depends(security)
):

    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="Admin authentication is not configured"
        )

    username_correct = secrets.compare_digest(
        credentials.username,
        ADMIN_USERNAME
    )

    password_correct = secrets.compare_digest(
        credentials.password,
        ADMIN_PASSWORD
    )

    if not (username_correct and password_correct):

        raise HTTPException(
            status_code=401,
            detail="Invalid admin username or password",
            headers={
                "WWW-Authenticate": "Basic"
            }
        )

    return True


def verify_device_api_key(
    x_api_key: str = Header(None, alias="X-API-Key")
):

    if not DEVICE_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Device API key is not configured"
        )

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Device API key required"
        )

    if not secrets.compare_digest(
        x_api_key,
        DEVICE_API_KEY
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid device API key"
        )

    return True


# ============================================================
# PROTECTED SWAGGER DOCS
# ============================================================

@app.get("/docs", include_in_schema=False)
def protected_docs(
    request: Request,
    authenticated: bool = Depends(verify_admin)
):

    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Accident Emergency Server - Admin"
    )


@app.get("/openapi.json", include_in_schema=False)
def protected_openapi(
    authenticated: bool = Depends(verify_admin)
):

    return JSONResponse(
        get_openapi(
            title=app.title,
            version="1.0.0",
            routes=app.routes
        )
    )


# ============================================================
# DATABASE
# ============================================================

def get_connection():

    if not DATABASE_URL:
        raise Exception(
            "DATABASE_URL environment variable not found"
        )

    return psycopg2.connect(DATABASE_URL)


# ============================================================
# TWILIO SMS
# ============================================================

def send_emergency_sms(phone):

    try:

        if not TWILIO_ACCOUNT_SID:
            raise Exception(
                "TWILIO_ACCOUNT_SID not configured"
            )

        if not TWILIO_AUTH_TOKEN:
            raise Exception(
                "TWILIO_AUTH_TOKEN not configured"
            )

        if not TWILIO_FROM_NUMBER:
            raise Exception(
                "TWILIO_FROM_NUMBER not configured"
            )

        client = Client(
            TWILIO_ACCOUNT_SID,
            TWILIO_AUTH_TOKEN
        )

        # Twilio trial predefined template
        message = client.messages.create(
            body="sms_internal_alerts",
            from_=TWILIO_FROM_NUMBER,
            to=phone
        )

        print("SMS sent successfully")
        print("Twilio SID:", message.sid)

        return {
            "success": True,
            "provider": "Twilio",
            "message_sid": message.sid
        }

    except Exception as e:

        print(
            "SMS sending failed:",
            str(e)
        )

        return {
            "success": False,
            "provider": "Twilio",
            "error": str(e)
        }


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
# CREATE TABLES
# ============================================================

def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (

            id SERIAL PRIMARY KEY,

            name TEXT NOT NULL,

            latitude DOUBLE PRECISION NOT NULL,

            longitude DOUBLE PRECISION NOT NULL,

            phone TEXT
        )
    """)

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


create_tables()


# ============================================================
# DISTANCE
# ============================================================

def calculate_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

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

def find_nearest_hospital(
    latitude,
    longitude
):

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
                "distance_km": round(
                    distance,
                    2
                )
            }

    return nearest


# ============================================================
# CREATE ALERT
# ============================================================

def create_emergency_alert(
    data,
    hospital
):

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

        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )

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
# PUBLIC HOME
# ============================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "message": "Accident Emergency Server"
    }


# ============================================================
# ADMIN - ADD HOSPITAL
# ============================================================

@app.post(
    "/api/hospitals",
    dependencies=[Depends(verify_admin)]
)
def add_hospital(
    hospital: HospitalData
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO hospitals (
            name,
            latitude,
            longitude,
            phone
        )

        VALUES (
            %s,
            %s,
            %s,
            %s
        )

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
        "message":
            "Hospital added successfully",
        "hospital_id": hospital_id
    }


# ============================================================
# ADMIN - VIEW HOSPITALS
# ============================================================

@app.get(
    "/api/hospitals",
    dependencies=[Depends(verify_admin)]
)
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
# ADMIN - UPDATE HOSPITAL
# ============================================================

@app.put(
    "/api/hospitals/{hospital_id}",
    dependencies=[Depends(verify_admin)]
)
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
        "message":
            "Hospital updated successfully"
    }


# ============================================================
# ADMIN - DELETE HOSPITAL
# ============================================================

@app.delete(
    "/api/hospitals/{hospital_id}",
    dependencies=[Depends(verify_admin)]
)
def delete_hospital(
    hospital_id: int
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM hospitals

        WHERE id = %s

        RETURNING id
    """, (
        hospital_id,
    ))

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
        "message":
            "Hospital deleted successfully"
    }


# ============================================================
# DEVICE - RECEIVE ACCIDENT
# ============================================================

@app.post(
    "/api/accident",
    dependencies=[
        Depends(verify_device_api_key)
    ]
)
def receive_accident(
    data: AccidentData
):

    print("\n============================")
    print("ACCIDENT RECEIVED")
    print("============================")

    print(
        "Vehicle:",
        data.vehicle_id
    )

    print(
        "Impact:",
        data.impact
    )

    print(
        "Location:",
        data.latitude,
        data.longitude
    )


    # Find nearest hospital

    hospital = find_nearest_hospital(
        data.latitude,
        data.longitude
    )


    if hospital is None:

        return {
            "success": False,
            "message":
                "No hospitals available"
        }


    print(
        "Nearest Hospital:",
        hospital["name"]
    )


    # Store emergency alert

    alert_id = create_emergency_alert(
        data,
        hospital
    )


    # Send SMS

    sms_result = send_emergency_sms(
        hospital["phone"]
    )


    return {
        "success": True,
        "message":
            "Emergency alert created",
        "alert_id": alert_id,
        "vehicle_id":
            data.vehicle_id,
        "nearest_hospital":
            hospital,
        "alert_status":
            "PENDING",
        "sms":
            sms_result
    }


# ============================================================
# ADMIN - VIEW ALERTS
# ============================================================

@app.get(
    "/api/alerts",
    dependencies=[Depends(verify_admin)]
)
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
