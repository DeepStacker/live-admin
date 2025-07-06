from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

sqlite_file_name = "database.db"

engine = create_engine(f"sqlite:///{sqlite_file_name}", echo=False)

# Enable foreign key constraints for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)
