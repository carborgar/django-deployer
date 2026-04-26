# Guía de despliegue — Django Deployer en Google Cloud

Guía paso a paso para instalar el panel de despliegue en tu servidor GCP y añadir tu primera app Django.

---

## Requisitos previos

- Instancia GCP (e2-micro o superior) con **Ubuntu 22.04** o Debian 12
- Acceso SSH al servidor
- Tu proyecto Django en un repositorio de GitHub (público o privado)
- El repositorio `django-deployer` subido a GitHub

---

## Parte 1 — Preparar el servidor GCP

### 1.1 Conectarte al servidor

```bash
# Desde Google Cloud Console → Compute Engine → SSH
# O con tu clave local:
ssh -i ~/.ssh/tu_clave usuario@IP_DEL_SERVIDOR
```

### 1.2 Abrir el puerto 80 en el firewall de GCP

En **Google Cloud Console**:

1. Ve a **VPC Network → Firewall**
2. Clic en **Create Firewall Rule**
3. Rellena:
   - Nombre: `allow-http`
   - Targets: `All instances in the network`
   - Source IP ranges: `0.0.0.0/0`
   - Protocols and ports: **TCP → 80**
4. Clic en **Create**

> Si quieres acceder al panel directamente por el puerto 8100 sin nginx (solo para pruebas), añade también el puerto 8100.

---

## Parte 2 — Instalar el Django Deployer

### 2.1 Descargar el deployer en el servidor

```bash
# Conectado al servidor como tu usuario (no root todavía)
git clone https://github.com/TU_USUARIO/django-deployer.git /tmp/django-deployer
```

Si el repo es privado, necesitas un token:

```bash
git clone https://TU_TOKEN@github.com/TU_USUARIO/django-deployer.git /tmp/django-deployer
```

### 2.2 Ejecutar el script de instalación

```bash
sudo bash /tmp/django-deployer/scripts/setup.sh
```

Este script hace automáticamente:
- ✅ Instala nginx, python3, git, pip
- ✅ Crea `/opt/deployer/` y `/opt/apps/`
- ✅ Genera la clave de cifrado en `/etc/deployer/secret.key`
- ✅ Instala las dependencias Python del panel
- ✅ Inicializa la base de datos SQLite
- ✅ Crea y activa el servicio `django-deployer` en systemd
- ✅ Configura nginx para servir el panel en `/deployer/`

Al terminar verás algo como:

```
============================================
  ✅ Setup completado

  Panel disponible en: http://34.X.X.X/deployer/
  Servicio:            systemctl status django-deployer
  Logs del panel:      journalctl -u django-deployer -f
============================================
```

### 2.3 Verificar que el panel está corriendo

```bash
systemctl status django-deployer
# Debe mostrar: active (running)

# Ver logs en tiempo real:
journalctl -u django-deployer -f
```

Abre en el navegador: **`http://IP_DEL_SERVIDOR/deployer/`**

Deberías ver el dashboard vacío del Django Deployer. 🎉

---

## Parte 3 — Añadir tu primera app Django

### 3.1 Preparar permisos en el servidor

El deployer corre como `www-data`. Necesita poder escribir en `/opt/apps/`:

```bash
sudo chown -R www-data:www-data /opt/apps
sudo chmod -R 755 /opt/apps
```

Si tu app necesita `sudo systemctl restart`, añade esto:

```bash
sudo visudo
# Añadir al final del archivo:
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart django-*, /bin/systemctl start django-*, /bin/systemctl stop django-*
```

### 3.2 Registrar la app en el panel

1. Abre **`http://IP/deployer/`**
2. Clic en **"+ Nueva app"**
3. Rellena el formulario:

| Campo | Ejemplo | Descripción |
|-------|---------|-------------|
| **Nombre** | `mi-app` | Identificador único (minúsculas y guiones) |
| **URL del repositorio** | `https://github.com/usuario/mi-app` | URL completa del repo |
| **Branch** | `main` | Branch que quieres desplegar |
| **Path prefix** | `mi-app` | La app estará en `http://IP/mi-app/` |
| **Puerto** | `8001` | Puerto interno de gunicorn (8001, 8002...) |
| **GitHub Token** | `ghp_xxx...` | Solo si el repo es privado |

4. Clic en **"Registrar app"**

> El panel genera automáticamente la config de nginx y el servicio systemd.

### 3.3 Configurar las variables de entorno

1. En la vista de la app, clic en **"🔑 Variables de entorno"**
2. Tienes dos opciones:

**Opción A — Pegar el .env completo** (recomendado):
```
SECRET_KEY=tu_secret_key_de_django
DEBUG=False
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=IP_DEL_SERVIDOR,localhost
DJANGO_SETTINGS_MODULE=mi_app.settings
```

**Opción B — Añadir una a una** con el formulario de la parte inferior.

> Los valores se cifran con AES-128 (Fernet) antes de guardarse.

### 3.4 Revisar los comandos de despliegue

1. Clic en **"⚙️ Comandos"**
2. Por defecto ya están configurados:
   - `pip install -r requirements.txt`
   - `python manage.py migrate --noinput`
   - `python manage.py collectstatic --noinput`
3. Ajusta el orden con ↑↓, elimina los que no necesites, o añade los tuyos

### 3.5 Hacer el primer deploy

1. Vuelve a la vista de la app
2. Clic en **"🚀 Deploy manual"**
3. Verás el estado cambiando a **"running"** (amarillo parpadeante)
4. Clic en el deployment en el historial para ver el **log en tiempo real**

El pipeline ejecuta:
```
git clone https://github.com/usuario/mi-app /opt/apps/mi-app/repo
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
systemctl restart django-mi-app
```

Si todo va bien, el estado pasa a **"success"** (verde) ✅

### 3.6 Verificar que la app está sirviendo

```bash
# Ver el servicio de tu app
systemctl status django-mi-app

# Ver logs de gunicorn en tiempo real
tail -f /opt/apps/mi-app/logs/app.log
```

Abre en el navegador: **`http://IP_DEL_SERVIDOR/mi-app/`**

> ⚠️ **Importante**: Django necesita saber que está bajo un subpath. En tu `settings.py`:
> ```python
> FORCE_SCRIPT_NAME = '/mi-app'
> USE_X_FORWARDED_HOST = True
> ```
> O usa la variable de entorno `SCRIPT_NAME` (nginx ya la envía automáticamente con el header `SCRIPT_NAME`).

---

## Parte 4 — Despliegues automáticos

Una vez registrada la app, el polling está activo por defecto. Cada 60 segundos el deployer:

1. Consulta la GitHub API para obtener el último commit del branch configurado
2. Si el SHA del commit es distinto al desplegado → lanza un deploy automático
3. El panel actualiza el estado en tiempo real

Puedes ver la fecha del último check en la tarjeta de cada app en el dashboard.

Para **pausar** el polling de una app (sin borrarla):
1. Clic en **"✏️ Editar"**
2. Desmarca **"App activa (polling habilitado)"**
3. Guardar

---

## Parte 5 — Añadir más apps

Repite la Parte 3 por cada app Django, usando puertos distintos:

| App | Port prefix | Puerto |
|-----|-------------|--------|
| mi-app | `/mi-app/` | 8001 |
| otra-app | `/otra-app/` | 8002 |
| api | `/api/` | 8003 |

El nginx se actualiza automáticamente cada vez que registras o editas una app.

---

## Parte 6 — Comandos útiles en el servidor

```bash
# Estado del panel deployer
systemctl status django-deployer

# Logs del panel en tiempo real
journalctl -u django-deployer -f

# Reiniciar el panel (tras actualización)
systemctl restart django-deployer

# Estado de una app concreta
systemctl status django-mi-app

# Logs de una app
tail -f /opt/apps/mi-app/logs/app.log

# Log del último deploy
ls /opt/apps/mi-app/logs/        # ver qué deploys hay
cat /opt/apps/mi-app/logs/deploy-1.log

# Verificar config nginx
nginx -t
systemctl status nginx
```

---

## Parte 7 — Actualizar el propio deployer

Cuando haya cambios en el código del deployer:

```bash
# En el servidor
cd /tmp/django-deployer
git pull origin main
sudo rsync -a --exclude='__pycache__' ./ /opt/deployer/src/
sudo /opt/deployer/venv/bin/pip install -q -r requirements.txt
sudo systemctl restart django-deployer
```

---

## Resolución de problemas frecuentes

### La app devuelve 502 Bad Gateway
```bash
# Gunicorn no está corriendo
systemctl status django-mi-app
systemctl start django-mi-app
# Ver el error:
journalctl -u django-mi-app -n 50
```

### El deploy falla en "migrate"
- Comprueba que `DATABASE_URL` esté bien configurado en las variables de entorno
- Mira el log completo del deployment en el panel

### Archivos estáticos no se sirven (CSS/JS de Django)
Añade en nginx (el deployer ya configura `SCRIPT_NAME`):
```bash
# En /etc/nginx/sites-enabled/deployer, dentro del location de tu app:
location /mi-app/static/ {
    alias /opt/apps/mi-app/repo/staticfiles/;
}
```
O configura `whitenoise` en tu Django app (más sencillo, sin tocar nginx).

### Ver la clave de cifrado (para backup)
```bash
sudo cat /etc/deployer/secret.key
# Guárdala en un lugar seguro. Sin ella, no se pueden descifrar las env vars.
```
