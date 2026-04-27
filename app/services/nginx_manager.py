"""
Genera y gestiona las configuraciones de nginx para cada app desplegada.
Cada app obtiene un bloque location /path_prefix/ → gunicorn en su puerto.
"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

NGINX_CONF_DIR = os.environ.get("DEPLOYER_NGINX_DIR", "/etc/nginx/sites-enabled")
NGINX_MAIN_CONF = os.environ.get("DEPLOYER_NGINX_CONF", "/etc/nginx/sites-enabled/deployer")

_LOCATION_TEMPLATE = """\
    # --- app: {name} ---
    location /{path_prefix}/ {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header SCRIPT_NAME /{path_prefix};
        client_max_body_size 50M;
    }}
"""

_SERVER_TEMPLATE = """\
server {{
    listen 80 default_server;
    listen [::]:80 default_server;

    # SSE logs del panel (sin buffering)
    location /deployer/logs/deployment/ {{
        proxy_pass http://127.0.0.1:8100/logs/deployment/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        add_header X-Accel-Buffering no;
    }}

    # Panel deployer
    location /deployer/ {{
        proxy_pass http://127.0.0.1:8100/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

{locations}
}}
"""


def _get_all_apps():
    """Importa aquí para evitar circular imports."""
    from app.models import App, engine
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        return db.query(App).filter(App.active == True).all()


def regenerate_full_config():
    """Regenera el archivo nginx completo con todas las apps activas."""
    apps = _get_all_apps()
    locations = "".join(
        _LOCATION_TEMPLATE.format(name=a.name, path_prefix=a.path_prefix, port=a.port)
        for a in apps
    )
    config = _SERVER_TEMPLATE.format(locations=locations)

    os.makedirs(NGINX_CONF_DIR, exist_ok=True)
    with open(NGINX_MAIN_CONF, "w") as f:
        f.write(config)

    _reload_nginx()


def generate_and_reload(app):
    """Añade/actualiza la config y recarga nginx."""
    regenerate_full_config()


def remove(app):
    """Elimina la app de la config y recarga nginx."""
    regenerate_full_config()


def _reload_nginx():
    result = subprocess.run(["sudo", "-n", "nginx", "-t"], capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"nginx config test falló:\n{result.stderr}")
        return False

    reload = subprocess.run(["sudo", "-n", "systemctl", "reload", "nginx"], capture_output=True, text=True)
    if reload.returncode != 0:
        logger.error(f"nginx reload falló:\n{reload.stderr}")
        return False

    logger.info("nginx recargado correctamente")
    return True
