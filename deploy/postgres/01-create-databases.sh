#!/bin/sh
set -eu

# Invoked by the official PostgreSQL entrypoint only for an empty data volume.
# psql variables quote values as SQL literals; passwords are not shell SQL code.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=crm_password="$CRM_DB_PASSWORD" \
  --set=keycloak_password="$KEYCLOAK_DB_PASSWORD" <<'SQL'
CREATE ROLE rtk_crm LOGIN PASSWORD :'crm_password';
CREATE DATABASE rtk_crm OWNER rtk_crm;
CREATE ROLE keycloak LOGIN PASSWORD :'keycloak_password';
CREATE DATABASE keycloak OWNER keycloak;
SQL
