#!/bin/bash
# wait_for_db.sh — espera a que PostgreSQL esté listo antes de migrar/servir.
# Reintenta cada 2 segundos durante 30 segundos (15 intentos).

set -e

echo "Esperando a que PostgreSQL esté listo en $POSTGRES_HOST:$POSTGRES_PORT..."

max_attempts=15
attempt=1

while [ $attempt -le $max_attempts ]; do
  if python -c "import psycopg; psycopg.connect('postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB', timeout=5)" 2>/dev/null; then
    echo "✓ PostgreSQL está listo (intento $attempt)."
    exit 0
  fi
  echo "  Reintentando ($attempt/$max_attempts)..."
  sleep 2
  attempt=$((attempt + 1))
done

echo "✗ PostgreSQL no respondió tras $max_attempts intentos. Abortando."
exit 1
