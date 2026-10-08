import subprocess
from pathlib import Path


class NginxManager:

    BASE = Path("/etc/nginx/sites-available")
    ENABLED = Path("/etc/nginx/sites-enabled")


    @classmethod
    def run(cls, cmd):
        return subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True
        )


    @classmethod
    def create_site(
        cls,
        domain:str,
        port:int
    ):

        filename = cls.BASE / f"{domain}.conf"

        config = f"""
server {{
    listen 80;
    listen [::]:80;

    server_name {domain};

    location / {{
        proxy_pass http://127.0.0.1:{port};

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""

        filename.write_text(config)


        link = cls.ENABLED / f"{domain}.conf"

        if not link.exists():
            link.symlink_to(filename)


        test = cls.run(
            "nginx -t"
        )

        if test.returncode != 0:
            return False, test.stderr


        cls.run(
            "systemctl reload nginx"
        )

        return True, "nginx_ready"
