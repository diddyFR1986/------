"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
import shutil

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

if os.environ.get('VERCEL'):
    src = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db.sqlite3')
    dst = '/tmp/db.sqlite3'
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy(src, dst)

application = get_wsgi_application()
app = application
