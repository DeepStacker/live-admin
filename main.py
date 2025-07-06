from fastapi import (
    FastAPI,
    Request,
    Form,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import (
    AsyncIOScheduler,
)  # Changed to AsyncIOScheduler
from db import init_db, get_session
from models import Service, PingLog
from utils import do_ping, ConnectionManager
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI(title="Uptime Monitor", description="Advanced uptime monitoring service")

init_db()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# WebSocket connection manager for live updates
manager = ConnectionManager()

# CORS for frontend access
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

scheduler = AsyncIOScheduler()  # Changed to AsyncIOScheduler


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with get_session() as session:
        services = session.query(Service).all()
        return templates.TemplateResponse(
            "index.html", {"request": request, "services": services}
        )


@app.post("/add")
def add_service(
    name: str = Form(...),
    url: str = Form(...),
    interval: int = Form(300000),
    timeout: int = Form(5000),
    headers: str = Form("{}"),
):
    try:
        headers_dict = json.loads(headers) if headers.strip() else {}
    except json.JSONDecodeError:
        headers_dict = {}

    service = Service(
        name=name,
        url=url,
        interval=max(interval, 5000),  # Minimum 5 seconds
        timeout=max(timeout, 1000),  # Minimum 1 second
        headers=headers_dict,
    )

    with get_session() as session:
        session.add(service)
        session.commit()
        session.refresh(service)
        service_id = service.id  # Store the ID

    # Schedule the new service using the ID
    schedule_service_by_id(service_id)

    return RedirectResponse("/", status_code=303)


@app.post("/update/{service_id}")
def update_service(
    service_id: int,
    name: str = Form(...),
    url: str = Form(...),
    interval: int = Form(...),
    timeout: int = Form(...),
    headers: str = Form("{}"),
):
    with get_session() as session:
        service = session.get(Service, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        try:
            headers_dict = json.loads(headers) if headers.strip() else {}
        except json.JSONDecodeError:
            headers_dict = {}

        service.name = name
        service.url = url
        service.interval = max(interval, 5000)
        service.timeout = max(timeout, 1000)
        service.headers = headers_dict
        service.updated_at = datetime.utcnow()

        session.commit()

    # Reschedule the service
    schedule_service_by_id(service_id)

    return RedirectResponse("/", status_code=303)


@app.post("/toggle/{service_id}")
def toggle_service(service_id: int):
    with get_session() as session:
        service = session.get(Service, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        service.enabled = not service.enabled
        service.updated_at = datetime.utcnow()
        session.commit()

        if service.enabled:
            schedule_service_by_id(service_id)
        else:
            # Remove from scheduler
            job_id = f"ping_{service_id}"
            try:
                scheduler.remove_job(job_id)
            except:
                pass

    return RedirectResponse("/", status_code=303)


@app.post("/delete/{service_id}")
def delete_service(service_id: int):
    with get_session() as session:
        service = session.get(Service, service_id)
        if service:
            # Remove from scheduler
            job_id = f"ping_{service_id}"
            try:
                scheduler.remove_job(job_id)
            except:
                pass

            # Delete related logs first
            logs = session.query(PingLog).filter(PingLog.service_id == service_id).all()
            for log in logs:
                session.delete(log)

            session.delete(service)
            session.commit()

    return RedirectResponse("/", status_code=303)


@app.post("/ping/{service_id}")
async def manual_ping(service_id: int):
    with get_session() as session:
        service = session.get(Service, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        log = await do_ping(service)

        # Access attributes while still in session context
        log_data = {
            "status": log.status,
            "message": log.message,
            "response_time": log.response_time,
            "timestamp": log.timestamp.isoformat(),
        }

        return JSONResponse(content=log_data)


@app.get("/logs/{service_id}", response_class=HTMLResponse)
def view_logs(service_id: int, request: Request, limit: int = 100):
    with get_session() as session:
        service = session.get(Service, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        logs = (
            session.query(PingLog)
            .filter(PingLog.service_id == service_id)
            .order_by(PingLog.timestamp.desc())
            .limit(limit)
            .all()
        )

        return templates.TemplateResponse(
            "logs.html",
            {
                "request": request,
                "logs": logs,
                "service": service,
                "service_id": service_id,
            },
        )


@app.get("/api/services")
def get_services():
    with get_session() as session:
        services = session.query(Service).all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "enabled": s.enabled,
                "last_status": s.last_status,
                "last_ping": s.last_ping,
                "interval": s.interval,
                "timeout": s.timeout,
            }
            for s in services
        ]


@app.get("/api/logs/{service_id}")
def get_logs_api(service_id: int, limit: int = 50):
    with get_session() as session:
        logs = (
            session.query(PingLog)
            .filter(PingLog.service_id == service_id)
            .order_by(PingLog.timestamp.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "status": log.status,
                "message": log.message,
                "response_time": log.response_time,
                "response_code": log.response_code,
            }
            for log in logs
        ]


@app.get("/stats/{service_id}")
def get_service_stats(service_id: int):
    with get_session() as session:
        service = session.get(Service, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Get logs from last 24 hours
        since = datetime.utcnow() - timedelta(hours=24)
        logs = (
            session.query(PingLog)
            .filter(PingLog.service_id == service_id)
            .filter(PingLog.timestamp >= since)
            .all()
        )

        total_pings = len(logs)
        successful_pings = len([log for log in logs if log.status == "success"])
        uptime_percentage = (
            (successful_pings / total_pings * 100) if total_pings > 0 else 0
        )

        response_times = [
            log.response_time for log in logs if log.response_time is not None
        ]
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )

        return {
            "uptime_percentage": round(uptime_percentage, 2),
            "total_pings": total_pings,
            "successful_pings": successful_pings,
            "avg_response_time": round(avg_response_time, 3),
            "last_24h": True,
        }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def schedule_service_by_id(service_id: int):
    """Schedule a service by its ID to avoid session issues"""
    with get_session() as session:
        service = session.get(Service, service_id)
        if not service or not service.enabled:
            return

        job_id = f"ping_{service_id}"
        interval_seconds = max(service.interval // 1000, 5)

        # Remove existing job if it exists
        try:
            scheduler.remove_job(job_id)
        except:
            pass

        # Add new job
        scheduler.add_job(
            ping_and_broadcast,
            "interval",
            seconds=interval_seconds,
            id=job_id,
            args=[service_id],
            replace_existing=True,
        )


async def ping_and_broadcast(service_id: int):
    """Ping service and broadcast result"""
    try:
        with get_session() as session:
            service = session.get(Service, service_id)
            if not service or not service.enabled:
                return

            log = await do_ping(service)

            # Access attributes while still in session
            broadcast_data = {
                "type": "ping_result",
                "service_id": service_id,
                "status": log.status,
                "message": log.message,
                "timestamp": log.timestamp.isoformat(),
                "response_time": log.response_time,
            }

        # Broadcast to all connected WebSocket clients
        await manager.broadcast(json.dumps(broadcast_data))

    except Exception as e:
        print(f"Error in ping_and_broadcast for service {service_id}: {e}")


@app.on_event("startup")
async def on_startup():
    with get_session() as session:
        services = session.query(Service).filter(Service.enabled == True).all()
        service_ids = [svc.id for svc in services]

    # Schedule all enabled services
    for service_id in service_ids:
        schedule_service_by_id(service_id)

    if not scheduler.running:
        scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    if scheduler.running:
        scheduler.shutdown()
