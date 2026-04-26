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
    with open(service_path, "w") as f:
        f.write(content)

    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", f"django-{app.name}"], check=False)
    logger.info(f"Servicio systemd creado: {service_path}")
    return True


def remove_service(app) -> bool:
    """Detiene, deshabilita y elimina el servicio."""
    service = f"django-{app.name}"
    subprocess.run(["systemctl", "stop", service], check=False)
    subprocess.run(["systemctl", "disable", service], check=False)

    service_path = os.path.join(SYSTEMD_DIR, f"{service}.service")
    if os.path.exists(service_path):
        os.remove(service_path)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    return True
