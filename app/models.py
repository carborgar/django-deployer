import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timezone

_DB_PATH = os.environ.get("DEPLOYER_DB_PATH", "/opt/deployer/deployer.db")
engine = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class App(Base):
    __tablename__ = "apps"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    repo_url = Column(String(500), nullable=False)
    branch = Column(String(100), default="main")
    path_prefix = Column(String(100), nullable=False)   # e.g. "myapp" → served at /myapp/
    port = Column(Integer, nullable=False)
    github_token = Column(Text, nullable=True)          # cifrado con Fernet
    active = Column(Boolean, default=True)
    deployed_commit = Column(String(40), nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    deployments = relationship("Deployment", back_populates="app", cascade="all, delete-orphan")
    env_vars = relationship("EnvVar", back_populates="app", cascade="all, delete-orphan")
    deploy_commands = relationship("DeployCommand", back_populates="app", cascade="all, delete-orphan", order_by="DeployCommand.order")


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey("apps.id"), nullable=False)
    commit_sha = Column(String(40), nullable=False)
    commit_message = Column(Text, nullable=True)
    status = Column(String(20), default="pending")      # pending | running | success | failed
    log = Column(Text, default="")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)

    app = relationship("App", back_populates="deployments")

    @property
    def duration_seconds(self):
        if self.finished_at and self.started_at:
            return int((self.finished_at - self.started_at).total_seconds())
        return None


class EnvVar(Base):
    __tablename__ = "env_vars"

    id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey("apps.id"), nullable=False)
    key = Column(String(200), nullable=False)
    value_encrypted = Column(Text, nullable=False)

    app = relationship("App", back_populates="env_vars")


class DeployCommand(Base):
    __tablename__ = "deploy_commands"

    id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey("apps.id"), nullable=False)
    order = Column(Integer, default=0)
    command = Column(String(500), nullable=False)       # e.g. "python manage.py migrate"

    app = relationship("App", back_populates="deploy_commands")


def init_db():
    Base.metadata.create_all(engine)
