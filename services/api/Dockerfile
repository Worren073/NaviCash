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

# Puerto expuesto por el runserver de desarrollo.
EXPOSE 8000

# Comando por defecto (se puede sobrescribir desde docker-compose o Render).
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]