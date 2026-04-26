import os
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["root_path"] = os.environ.get("DEPLOYER_ROOT_PATH", "")
