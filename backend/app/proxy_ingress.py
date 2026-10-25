"""Dedicated Serve ingress. Start without Uvicorn proxy headers or lifespan.

The main backend owns migrations, bootstrap and periodic workers. This listener
shares its routes and authorization, never runs a second bootstrap/worker loop.
"""
import os

from app.core.trusted_proxy import TrustedProxyIngress
from app.main import app as application

app = TrustedProxyIngress(
    application,
    peer=os.environ["ATLAS_TRUSTED_PROXY_IP"],
    hostname=os.environ["ATLAS_TRUSTED_PROXY_HOST"],
)
