#!/usr/bin/env bash
# =============================================================================
# setup.sh — Configura el servidor para Django Deployer
# Ejecutar como root: sudo bash setup.sh
# =============================================================================
set -euo pipefail

DEPLOYER_DIR="/opt/deployer"
APPS_DIR="/opt/apps"
KEY_DIR="/etc/deployer"
DEPLOYER_PORT=8100

echo "============================================"
echo "  Django Deployer — Setup del servidor"
echo "============================================"

# --- Dependencias del sistema ---
echo "[1/7] Instalando dependencias del sistema..."
apt-get update -qq
apt-get install -y -qq nginx python3 python3-pip python3-venv git curl rsync

# --- Directorios ---
echo "[2/7] Creando estructura de directorios..."
mkdir -p "$DEPLOYER_DIR" "$APPS_DIR" "$KEY_DIR"
chmod 750 "$KEY_DIR"
chown root:www-data "$KEY_DIR"

# --- Virtualenv del deployer ---
echo "[3/7] Configurando virtualenv del deployer..."
if [ ! -d "$DEPLOYER_DIR/venv" ]; then
    python3 -m venv "$DEPLOYER_DIR/venv"
fi
"$DEPLOYER_DIR/venv/bin/pip" install --quiet --upgrade pip
"$DEPLOYER_DIR/venv/bin/pip" install --quiet -r "$(dirname "$0")/../requirements.txt"

# --- Clave de cifrado ---
echo "[4/7] Generando clave de cifrado para variables de entorno..."
KEY_FILE="$KEY_DIR/secret.key"
if [ ! -f "$KEY_FILE" ]; then
    "$DEPLOYER_DIR/venv/bin/python" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > "$KEY_FILE"
    chmod 640 "$KEY_FILE"
    chown root:www-data "$KEY_FILE"
    echo "    ✓ Clave generada en $KEY_FILE"
else
    chown root:www-data "$KEY_FILE"
    chmod 640 "$KEY_FILE"
    echo "    ✓ Ya existe clave en $KEY_FILE — no se sobreescribe"
fi

# Copiar el código del deployer
rsync -a --exclude='__pycache__' "$(dirname "$0")/../" "$DEPLOYER_DIR/src/"
chown -R www-data:www-data "$DEPLOYER_DIR/src"
echo "    ✓ Código copiado a $DEPLOYER_DIR/src/"

# --- Base de datos ---
echo "[5/7] Inicializando base de datos..."
DEPLOYER_KEY_PATH="$KEY_FILE" \
DEPLOYER_APPS_DIR="$APPS_DIR" \
DEPLOYER_DB_PATH="$DEPLOYER_DIR/deployer.db" \
DEPLOYER_NGINX_DIR=/etc/nginx/sites-enabled \
DEPLOYER_NGINX_CONF=/etc/nginx/sites-enabled/deployer \
    "$DEPLOYER_DIR/venv/bin/python" -c "
import sys; sys.path.insert(0, '$DEPLOYER_DIR/src')
from app.models import init_db; init_db()
print('    ✓ Base de datos lista')
"
chown www-data:www-data "$DEPLOYER_DIR/deployer.db"
chmod 640 "$DEPLOYER_DIR/deployer.db"
chown -R www-data:www-data "$APPS_DIR"
chmod 755 "$APPS_DIR"

# --- Servicio systemd del deployer ---
echo "[6/7] Creando servicio systemd del deployer..."
cat > /etc/systemd/system/django-deployer.service << EOF
[Unit]
Description=Django Deployer Panel
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$DEPLOYER_DIR/src
Environment=DEPLOYER_KEY_PATH=$KEY_FILE
Environment=DEPLOYER_APPS_DIR=$APPS_DIR
Environment=DEPLOYER_DB_PATH=$DEPLOYER_DIR/deployer.db
Environment=DEPLOYER_NGINX_DIR=/etc/nginx/sites-enabled
Environment=DEPLOYER_NGINX_CONF=/etc/nginx/sites-enabled/deployer
Environment=DEPLOYER_ROOT_PATH=/deployer
ExecStart=$DEPLOYER_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $DEPLOYER_PORT --workers 1 --root-path /deployer
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable django-deployer
systemctl restart django-deployer
echo "    ✓ Servicio django-deployer habilitado y arrancado"

# Permisos sudo para que el panel gestione systemd/nginx sin prompt
cat > /etc/sudoers.d/django-deployer << 'EOF'
Defaults:www-data !requiretty
www-data ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
www-data ALL=(root) NOPASSWD: /bin/systemctl reload nginx
www-data ALL=(root) NOPASSWD: /bin/systemctl restart django-*
www-data ALL=(root) NOPASSWD: /bin/systemctl enable django-*
www-data ALL=(root) NOPASSWD: /bin/systemctl disable django-*
www-data ALL=(root) NOPASSWD: /bin/systemctl stop django-*
www-data ALL=(root) NOPASSWD: /usr/sbin/nginx -t
www-data ALL=(root) NOPASSWD: /usr/bin/install -m 0644 * /etc/systemd/system/django-*.service
www-data ALL=(root) NOPASSWD: /bin/rm -f /etc/systemd/system/django-*.service
EOF
chmod 440 /etc/sudoers.d/django-deployer
visudo -cf /etc/sudoers.d/django-deployer > /dev/null
echo "    ✓ sudoers de django-deployer configurado"

# --- Nginx base ---
echo "[7/7] Configurando nginx base..."
# Eliminar default de nginx si existe
rm -f /etc/nginx/sites-enabled/default

# Crear config base (será gestionada por el deployer a partir de aquí)
if [ ! -f /etc/nginx/sites-enabled/deployer ]; then
    cat > /etc/nginx/sites-enabled/deployer << 'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    # SSE logs del panel (sin buffering)
    location /deployer/logs/deployment/ {
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
    }

    # Panel deployer
    location /deployer/ {
        proxy_pass http://127.0.0.1:8100/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
fi

nginx -t && systemctl reload nginx
echo "    ✓ nginx configurado"

echo ""
echo "============================================"
echo "  ✅ Setup completado"
echo ""
echo "  Panel disponible en: http://$(curl -s ifconfig.me)/deployer/"
echo "  Servicio:            systemctl status django-deployer"
echo "  Logs del panel:      journalctl -u django-deployer -f"
echo "============================================"
