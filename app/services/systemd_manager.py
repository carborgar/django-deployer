"""
Genera archivos .service de systemd para cada app Django.
El servicio corre gunicorn con el socket en el puerto configurado.
"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

APPS_DIR = os.environ.get("DEPLOYER_APPS_DIR", "/opt/apps")
SYSTEMD_DIR = "/etc/systemd/system"

_SERVICE_TEMPLATE = """\
[Unit]
Description=Django app: {name}
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory={repo_dir}
EnvironmentFile={env_file}
ExecStart={venv_dir}/bin/gunicorn \\
    --workers 2 \\
    --bind 127.0.0.1:{port} \\
    --access-logfile {logs_dir}/app.log \\
    --error-logfile {logs_dir}/app.log \\
    {wsgi_module}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""


def create_service(app) -> bool:
    """Crea y habilita el servicio systemd para la app."""
    app_dir = os.path.join(APPS_DIR, app.name)
    repo_dir = os.path.join(app_dir, "repo")
    venv_dir = os.path.join(app_dir, "venv")
    logs_dir = os.path.join(app_dir, "logs")
    env_file = os.path.join(app_dir, ".env")

    os.makedirs(logs_dir, exist_ok=True)

    wsgi_module = f"{app.name}.wsgi:application"

    content = _SERVICE_TEMPLATE.format(
        name=app.name,
        repo_dir=repo_dir,
        env_file=env_file,
        venv_dir=venv_dir,
        port=app.port,
        logs_dir=logs_dir,
        wsgi_module=wsgi_module,
    )

    service_path = os.path.join(SYSTEMD_DIR, f"django-{app.name}.service")
    try:
        # Usamos `sudo tee` para escribir ficheros en /etc/systemd sin necesitar
        # permisos de escritura directos como www-data.
        tee = subprocess.run(
            ["sudo", "-n", "tee", service_path],
            input=content,
            check=False,
            capture_output=True,
            text=True,
        )
        if tee.returncode != 0:
            logger.error(f"No se pudo escribir {service_path} via tee: {tee.stderr.strip()}")
            return False
        # Asegurar permisos correctos
        subprocess.run(["sudo", "-n", "chmod", "0644", service_path], check=False)
    except OSError as e:
        logger.error(f"No se pudo preparar unidad {service_path}: {e}")
        return False

    daemon_reload = subprocess.run(["sudo", "-n", "systemctl", "daemon-reload"], check=False, capture_output=True, text=True)
    if daemon_reload.returncode != 0:
        logger.error(f"systemctl daemon-reload falló: {daemon_reload.stderr.strip()}")
        return False

    enable = subprocess.run(["sudo", "-n", "systemctl", "enable", f"django-{app.name}"], check=False, capture_output=True, text=True)
    if enable.returncode != 0:
        logger.error(f"systemctl enable django-{app.name} falló: {enable.stderr.strip()}")
        return False

    logger.info(f"Servicio systemd creado: {service_path}")
    return True


def remove_service(app) -> bool:
    """Detiene, deshabilita y elimina el servicio."""
    service = f"django-{app.name}"
    stop = subprocess.run(["sudo", "-n", "systemctl", "stop", service], check=False, capture_output=True, text=True)
    if stop.returncode != 0:
        logger.warning(f"systemctl stop {service} devolvió {stop.returncode}: {stop.stderr.strip()}")

    disable = subprocess.run(["sudo", "-n", "systemctl", "disable", service], check=False, capture_output=True, text=True)
    if disable.returncode != 0:
        logger.warning(f"systemctl disable {service} devolvió {disable.returncode}: {disable.stderr.strip()}")

    service_path = os.path.join(SYSTEMD_DIR, f"{service}.service")
    if os.path.exists(service_path):
        rm = subprocess.run(["sudo", "-n", "rm", "-f", service_path], check=False, capture_output=True, text=True)
        if rm.returncode != 0:
            logger.error(f"No se pudo eliminar {service_path}: {rm.stderr.strip()}")
            return False
    daemon_reload = subprocess.run(["sudo", "-n", "systemctl", "daemon-reload"], check=False, capture_output=True, text=True)
    if daemon_reload.returncode != 0:
        logger.error(f"systemctl daemon-reload falló al eliminar {service}: {daemon_reload.stderr.strip()}")
        return False

    return True
