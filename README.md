# Django Deployer

Panel de control para desplegar automáticamente apps Django desde GitHub en un servidor Linux.

## Características
- 🔄 **Polling automático** de GitHub cada 60s — detecta nuevos commits y despliega
- 🚀 **Deploy manual** desde el panel
- 🔑 **Variables de entorno** cifradas (Fernet) con edición individual y en bloque
- ⚙️ **Comandos personalizados** (migrate, collectstatic, etc.) con orden configurable
- 📋 **Logs en tiempo real** del deploy (SSE) y logs de la app (gunicorn)
- 🕐 **Historial** de deployments con estado y duración
- 🌐 **nginx automático** — cada app se sirve en `/path-prefix/`
- 🛠 **systemd** — cada app Django corre como servicio gestionado

## Requisitos del servidor
- Ubuntu/Debian
- Python 3.11+
- nginx
- systemd

## Instalación en el servidor

```bash
git clone https://github.com/TU_USUARIO/django-deployer /tmp/django-deployer
cd /tmp/django-deployer
sudo bash scripts/setup.sh
```

El panel queda accesible en `http://IP_SERVIDOR/deployer/`

## Desarrollo local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Para desarrollo local (sin nginx/systemd):
mkdir -p /etc/deployer /opt/apps
python3 -c "from cryptography.fernet import Fernet; open('/etc/deployer/secret.key','w').write(Fernet.generate_key().decode())"

python run.py
# → http://127.0.0.1:8100
```

## Estructura

```
app/
  main.py              # FastAPI app + lifespan (scheduler)
  models.py            # SQLAlchemy: App, Deployment, EnvVar, DeployCommand
  crypto.py            # Cifrado Fernet para tokens y env vars
  routers/
    apps.py            # CRUD apps + dashboard
    deployments.py     # Detalle de deployment
    envvars.py         # CRUD variables de entorno
    commands.py        # CRUD comandos de despliegue
    logs.py            # SSE streaming + tail logs
  services/
    deployer.py        # Pipeline de despliegue
    poller.py          # Polling GitHub API
    nginx_manager.py   # Generación config nginx
    systemd_manager.py # Generación servicios systemd
  templates/           # Jinja2 + Tailwind + HTMX
scripts/
  setup.sh             # Instalación en servidor
```

## Variables de entorno del panel

| Variable | Defecto | Descripción |
|---|---|---|
| `DEPLOYER_KEY_PATH` | `/etc/deployer/secret.key` | Ruta clave Fernet |
| `DEPLOYER_APPS_DIR` | `/opt/apps` | Directorio apps Django |
| `DEPLOYER_NGINX_DIR` | `/etc/nginx/sites-enabled` | Directorio configs nginx |
| `DEPLOYER_NGINX_CONF` | `/etc/nginx/sites-enabled/deployer` | Archivo nginx principal |

## Cómo funciona el deploy

1. Poller detecta nuevo commit (o deploy manual)
2. `git clone` / `git pull` del repo
3. Se escribe el archivo `.env` con las variables cifradas
4. Se crea/actualiza el virtualenv
5. `pip install -r requirements.txt`
6. Se ejecutan los comandos personalizados (migrate, collectstatic...)
7. Se reinicia el servicio `django-{nombre}.service` con systemd
8. Se actualiza el commit desplegado en la BD
