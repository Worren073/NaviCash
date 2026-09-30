#!/bin/bash
# wait_for_db.sh — espera a que PostgreSQL esté listo antes de migrar/servir.
# Usa pg_isready (herramienta estándar) en lugar de intentar conexión con psycopg.
# - Producción (Render): usa DATABASE_URL (URL completa resuelta por el Blueprint).
# - Desarrollo: usa los campos POSTGRES_* por separado.
# Reintenta cada 3 segundos durante 45 segundos (15 intentos).

if [ -n "$DATABASE_URL" ]; then
  conn="$DATABASE_URL"
  echo "[wait_for_db] Esperando PostgreSQL vía DATABASE_URL..."
else
  conn=""
  echo "[wait_for_db] Esperando PostgreSQL en $POSTGRES_HOST:$POSTGRES_PORT..."
  echo "[wait_for_db] POSTGRES_USER=$POSTGRES_USER"
  echo "[wait_for_db] POSTGRES_DB=$POSTGRES_DB"
fi

max_attempts=15
attempt=1

while [ $attempt -le $max_attempts ]; do
  # pg_isready es más ligero que intentar una conexión completa.
  # Retorna 0 si la BD está lista, non-zero en caso contrario.
  if [ -n "$conn" ]; then
    ready=$(pg_isready "$conn" 2>&1)
  else
    ready=$(PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" 2>&1)
  fi

  if echo "$ready" | grep -q "accepting connections"; then
    echo "[wait_for_db] ✓ PostgreSQL está listo (intento $attempt/$max_attempts)"
    exit 0
  fi

  if [ $attempt -lt $max_attempts ]; then
    echo "[wait_for_db] Intento $attempt/$max_attempts falló. Reintentando en 3s..."
    sleep 3
  fi
  attempt=$((attempt + 1))
done

echo "[wait_for_db] ✗ PostgreSQL no respondió tras $max_attempts intentos (45 segundos). Abortando."
echo "[wait_for_db] Verifica:"
echo "[wait_for_db]   - DATABASE_URL / POSTGRES_HOST está correcto"
echo "[wait_for_db]   - Las credenciales son las correctas"
echo "[wait_for_db]   - La BD está en línea en Render"
exit 1
