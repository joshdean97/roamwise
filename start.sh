#!/usr/bin/env sh
set -eu

export APP_ENV="${APP_ENV:-production}"

echo "Applying database migrations..."
flask --app app db upgrade

echo "Checking city seed data..."
python seed_city_data.py

echo "Starting onboarding email worker..."
flask --app app onboarding-email-worker &

echo "Starting Roamwise..."
exec gunicorn -c gunicorn.conf.py app:app
