from sqlalchemy.orm import Session
from app.models import engine


def get_db():
    with Session(engine) as session:
        yield session
