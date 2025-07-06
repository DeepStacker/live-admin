import httpx
import time
from datetime import datetime
from models import Service, PingLog
from db import get_session
from fastapi import WebSocket
from typing import List
import json


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Mark broken connections for removal
                disconnected.append(connection)

        # Remove broken connections
        for connection in disconnected:
            if connection in self.active_connections:
                self.active_connections.remove(connection)


async def do_ping(service: Service):
    timestamp = datetime.utcnow()
    start_time = time.time()

    log = PingLog(
        service_id=service.id, timestamp=timestamp, status="unknown", message=""
    )

    if not service.enabled:
        log.status = "disabled"
        log.message = "Service is disabled"
        with get_session() as session:
            session.add(log)
            session.commit()
            session.refresh(log)  # Ensure log is properly loaded
        return log

    try:
        timeout_seconds = service.timeout / 1000
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(service.url, headers=service.headers)

            response_time = time.time() - start_time

            log.status = "success"
            log.message = f"✅ HTTP {response.status_code}"
            log.response_time = response_time
            log.response_code = response.status_code
            log.response_body = str(response.text)[:500]  # Store first 500 chars

            service.last_ping = (
                f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} ✅ ({response.status_code})"
            )
            service.last_status = "success"
            service.retry_attempts = 0

    except httpx.TimeoutException:
        response_time = time.time() - start_time
        log.status = "timeout"
        log.message = f"❌ Timeout ({service.timeout}ms)"
        log.response_time = response_time

        service.last_ping = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} ❌ Timeout"
        service.last_status = "timeout"
        service.retry_attempts += 1

    except httpx.ConnectError as e:
        response_time = time.time() - start_time
        log.status = "connection_error"
        log.message = f"❌ Connection Error: {str(e)[:100]}"
        log.response_time = response_time

        service.last_ping = (
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} ❌ Connection Error"
        )
        service.last_status = "connection_error"
        service.retry_attempts += 1

    except Exception as e:
        response_time = time.time() - start_time
        log.status = "error"
        log.message = f"❌ Error: {str(e)[:100]}"
        log.response_time = response_time

        service.last_ping = (
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} ❌ {str(e)[:50]}"
        )
        service.last_status = "error"
        service.retry_attempts += 1

    # Update service timestamp
    service.updated_at = datetime.utcnow()

    # Use a fresh session to avoid detached instance issues
    with get_session() as session:
        session.add(log)
        session.merge(service)  # Use merge to handle detached instance
        session.commit()
        session.refresh(log)  # Ensure log is properly loaded

    return log
