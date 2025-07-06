from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON, DateTime
from typing import Optional, List
from datetime import datetime
import json


class Service(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    url: str
    interval: int = 300000  # milliseconds
    timeout: int = 5000  # milliseconds
    headers: dict = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True
    retry_attempts: int = 0
    retry_max: int = 3
    last_ping: Optional[str] = None
    last_status: Optional[str] = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow, sa_column=Column(DateTime)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, sa_column=Column(DateTime)
    )

    # Relationship to ping logs
    ping_logs: List["PingLog"] = Relationship(back_populates="service")


class PingLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    service_id: int = Field(foreign_key="service.id")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, sa_column=Column(DateTime)
    )
    status: str
    message: str
    response_time: Optional[float] = None  # in seconds
    response_code: Optional[int] = None
    response_body: Optional[str] = None

    # Relationship to service
    service: Optional[Service] = Relationship(back_populates="ping_logs")
