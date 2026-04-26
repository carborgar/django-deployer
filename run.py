#!/usr/bin/env python3
"""
Punto de entrada principal del deployer.
Uso: python run.py   (para desarrollo local)
"""
import os
import uvicorn

if __name__ == "__main__":
    os.environ.setdefault("DEPLOYER_KEY_PATH", "/etc/deployer/secret.key")
    os.environ.setdefault("DEPLOYER_APPS_DIR", "/opt/apps")
    os.environ.setdefault("DEPLOYER_NGINX_DIR", "/etc/nginx/sites-enabled")
    os.environ.setdefault("DEPLOYER_NGINX_CONF", "/etc/nginx/sites-enabled/deployer")
    os.environ.setdefault("DEPLOYER_DB_PATH", "/opt/deployer/deployer.db")

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8100,
        reload=False,
        workers=1,
    )
