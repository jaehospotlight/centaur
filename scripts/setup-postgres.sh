#!/bin/bash
set -euo pipefail

# Install Postgres 16 + pgvector on Ubuntu 24.04
echo "=== Installing PostgreSQL 16 ==="
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-16-pgvector

# Start and enable
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql <<EOF
CREATE USER tempo WITH PASSWORD '${POSTGRES_PASSWORD:-tempo_prod}';
CREATE DATABASE ai_v2 OWNER tempo;
\c ai_v2
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
GRANT ALL PRIVILEGES ON DATABASE ai_v2 TO tempo;
GRANT ALL ON SCHEMA public TO tempo;
EOF

# Configure pg_hba.conf for local + network access
PG_HBA=$(sudo -u postgres psql -t -c "SHOW hba_file" | tr -d ' ')
sudo cp "$PG_HBA" "${PG_HBA}.bak"
# Allow local connections
echo "host    ai_v2    tempo    127.0.0.1/32    scram-sha-256" | sudo tee -a "$PG_HBA"
echo "host    ai_v2    tempo    ::1/128         scram-sha-256" | sudo tee -a "$PG_HBA"
# Allow connections from docker containers
echo "host    ai_v2    tempo    172.17.0.0/16   scram-sha-256" | sudo tee -a "$PG_HBA"

# Configure postgresql.conf for performance
PG_CONF=$(sudo -u postgres psql -t -c "SHOW config_file" | tr -d ' ')
sudo tee -a "$PG_CONF" > /dev/null <<PGCONF

# ai_v2 tuning
shared_buffers = '512MB'
effective_cache_size = '2GB'
work_mem = '64MB'
maintenance_work_mem = '256MB'
max_connections = 100
listen_addresses = 'localhost'
PGCONF

sudo systemctl restart postgresql

echo "=== PostgreSQL setup complete ==="
echo "Connection: postgresql://tempo:${POSTGRES_PASSWORD:-tempo_prod}@localhost:5432/ai_v2"
