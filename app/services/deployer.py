"""
Motor de despliegue.
Pipeline: git clone/pull → escribir .env → pip install → comandos → restart systemd
"""
import asyncio
import logging
import os
import re
import subprocess
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import App, Deployment, EnvVar, engine
from app.crypto import decrypt

logger = logging.getLogger(__name__)

APPS_DIR = os.environ.get("DEPLOYER_APPS_DIR", "/opt/apps")


def _run(cmd: str, cwd: str, env: dict, log_file) -> tuple[int, str]:
    """Ejecuta un comando, escribe output al log_file y lo retorna."""
    log_file.write(f"$ {_sanitize_log_text(cmd)}\n")
    log_file.flush()
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_file.write(_sanitize_log_text(result.stdout or ""))
    log_file.write(f"→ exit code: {result.returncode}\n\n")
    log_file.flush()
    return result.returncode, result.stdout


async def deploy_app(app_id: int, commit_sha: str | None = None):
    """Lanza el pipeline de despliegue en un thread separado para no bloquear el event loop."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _deploy_sync, app_id, commit_sha)


def _deploy_sync(app_id: int, commit_sha: str | None):
    with Session(engine) as db:
        app = db.query(App).filter(App.id == app_id).first()
        if not app:
            logger.error(f"App {app_id} not found")
            return

        deployment = Deployment(
            app_id=app_id,
            commit_sha=commit_sha or "unknown",
            status="running",
        )
        db.add(deployment)
        db.commit()
        db.refresh(deployment)

        app_dir = os.path.join(APPS_DIR, app.name)
        repo_dir = os.path.join(app_dir, "repo")
        venv_dir = os.path.join(app_dir, "venv")
        logs_dir = os.path.join(app_dir, "logs")
        env_file = os.path.join(app_dir, ".env")
        log_path = os.path.join(logs_dir, f"deploy-{deployment.id}.log")

        os.makedirs(logs_dir, exist_ok=True)
        stage = "init"
        last_command = ""

        try:
            with open(log_path, "w") as lf:
                lf.write(f"=== Deploy {deployment.id} — {datetime.now(timezone.utc).isoformat()} ===\n\n")

                # 1. Clonar o actualizar el repo
                stage = "git"
                token = decrypt(app.github_token) if app.github_token else None
                repo_url = _inject_token(app.repo_url, token)

                if not os.path.exists(os.path.join(repo_dir, ".git")):
                    lf.write("--- Clonando repositorio ---\n")
                    last_command = f"git clone {repo_url} {repo_dir}"
                    rc, _ = _run(f"git clone {repo_url} {repo_dir}", app_dir, os.environ.copy(), lf)
                else:
                    lf.write("--- Actualizando repositorio ---\n")
                    last_command = f"git fetch origin {app.branch} && git reset --hard origin/{app.branch}"
                    rc, _ = _run(f"git fetch origin {app.branch} && git reset --hard origin/{app.branch}", repo_dir, os.environ.copy(), lf)

                if rc != 0:
                    raise RuntimeError("git falló")

                # 2. Obtener commit actual
                stage = "metadata"
                result = subprocess.run("git rev-parse HEAD", shell=True, cwd=repo_dir, capture_output=True, text=True)
                actual_sha = result.stdout.strip()
                msg_result = subprocess.run("git log -1 --pretty=%s", shell=True, cwd=repo_dir, capture_output=True, text=True)
                deployment.commit_sha = actual_sha
                deployment.commit_message = msg_result.stdout.strip()
                db.commit()

                # 3. Crear/actualizar virtualenv
                stage = "venv"
                lf.write("--- Preparando virtualenv ---\n")
                if not os.path.exists(venv_dir):
                    last_command = f"python3 -m venv {venv_dir}"
                    _run(f"python3 -m venv {venv_dir}", app_dir, os.environ.copy(), lf)

                pip = os.path.join(venv_dir, "bin", "pip")
                python = os.path.join(venv_dir, "bin", "python")

                # 4. Escribir .env
                stage = "env"
                _write_env_file(db, app_id, env_file)
                lf.write(f"--- Variables de entorno escritas en {env_file} ---\n\n")

                # Entorno con .env cargado
                run_env = _load_env(env_file)
                run_env["VIRTUAL_ENV"] = venv_dir
                run_env["PATH"] = f"{venv_dir}/bin:{os.environ.get('PATH', '')}"

                # 5. pip install
                stage = "dependencies"
                lf.write("--- Instalando dependencias ---\n")
                last_command = f"{pip} install -r requirements.txt"
                rc, _ = _run(f"{pip} install -r requirements.txt", repo_dir, run_env, lf)
                if rc != 0:
                    raise RuntimeError("pip install falló")

                # 6. Comandos custom
                stage = "commands"
                lf.write("--- Comandos de despliegue ---\n")
                for cmd in app.deploy_commands:
                    full_cmd = cmd.command.replace("python", python)
                    last_command = full_cmd
                    rc, _ = _run(full_cmd, repo_dir, run_env, lf)
                    if rc != 0:
                        raise RuntimeError(f"Comando falló: {cmd.command}")

                # 7. Reiniciar servicio systemd
                stage = "systemd"
                service = f"django-{app.name}"
                lf.write(f"--- Reiniciando {service} ---\n")
                last_command = f"sudo -n systemctl restart {service}"
                rc, _ = _run(f"sudo -n systemctl restart {service}", app_dir, os.environ.copy(), lf)
                if rc != 0:
                    raise RuntimeError(f"No se pudo reiniciar {service}")

                lf.write("\n✅ Deploy completado con éxito\n")
                deployment.status = "success"
                app.deployed_commit = actual_sha

        except Exception as e:
            logger.exception(f"Deploy {deployment.id} falló: {e}")
            deployment.status = "failed"
            deployment.log = (
                f"Etapa: {stage}\n"
                f"Comando: {_sanitize_log_text(last_command) if last_command else '-'}\n"
                f"Error: {e}"
            )

        finally:
            if os.path.exists(log_path):
                tail = _tail_file(log_path)
                if deployment.status == "failed":
                    deployment.log = f"{deployment.log}\n\n--- Últimas líneas ---\n{tail}"
                elif not deployment.log:
                    deployment.log = tail
            deployment.finished_at = datetime.now(timezone.utc)
            db.commit()


def _inject_token(url: str, token: str | None) -> str:
    if not token:
        return url
    if url.startswith("https://"):
        return url.replace("https://", f"https://{token}@")
    return url


def _write_env_file(db: Session, app_id: int, path: str):
    vars_ = db.query(EnvVar).filter(EnvVar.app_id == app_id).all()
    with open(path, "w") as f:
        for v in vars_:
            f.write(f"{v.key}={decrypt(v.value_encrypted)}\n")
    os.chmod(path, 0o600)


def _load_env(path: str) -> dict:
    env = os.environ.copy()
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _sanitize_log_text(text: str) -> str:
    # Evita exponer tokens cuando se usan URLs https://token@host.
    return re.sub(r"https://[^/@\s]+@", "https://***@", text)


def _tail_file(path: str, max_chars: int = 12000) -> str:
    with open(path, "r") as f:
        data = f.read()
    if len(data) <= max_chars:
        return data
    return data[-max_chars:]

