# Dockerfile para el backend Django de NaviCash.
# ---------------------------------------------------------------------------
# Desarrollo: imagen ligera basada en python:3.13-slim. Las dependencias se
# instalan dentro del contenedor (nunca en la máquina anfitriona).
# En producción Render usará una variante con gunicorn (ver STACK.md).
# ---------------------------------------------------------------------------
FROM python:3.13-slim

# No escribir bytecode y que la salida sea "unbuffered" (logs en vivo).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Directorio de trabajo dentro del contenedor.
WORKDIR /app

# Systemdeps mínimas (psycopg binario embebido no necesita libpq si usamos psycopg[binary]).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Instalamos Python-deps con pip directamente (sin virtualenv dentro del contenedor).
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiamos el código del proyecto.
COPY . .

# Puerto de la API.
EXPOSE 8000

# Comando por defecto controlado por DEBUG (AUDIT M7):
#   - DEBUG=1  -> runserver con autoreload (desarrollo local).
#   - DEBUG=0  -> gunicorn multi-worker listo para producción (3 workers,
#                 timeout 60 s para el LLM del asistente sin matar workers).
# docker-compose de desarrollo sobre-escribe el comando (ver infra/), esta
# lógica aplica a la imagen base / despliegues prod tipo Render.
CMD ["sh", "-c", "if [ \"$DEBUG\" = \"1\" ]; then python manage.py runserver 0.0.0.0:8000; else gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3 --timeout 60; fi"]