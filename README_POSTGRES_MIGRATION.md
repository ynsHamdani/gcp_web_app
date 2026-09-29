# PostgreSQL storage migration

The Dash workflow is now connected to PostgreSQL through the existing storage
interfaces. JSON remains only as a one-time migration source.

## 1. Install dependencies

```bash
pip install -r requirements_postgresql.txt
```

## 2. Configure the local database

Copy:

```text
config.example.yaml -> config.yaml
```

Edit the PostgreSQL credentials in `config.yaml` and set:

```yaml
development:
  user_id: 1
```

to an existing row in `users` until the authentication page exists.

`config.yaml` is git-ignored.

## 3. Create the database schema

Run the previously provided SQL schema in PostgreSQL before starting Dash.

## 4. Migrate existing JSON data once

```bash
python scripts/migrate_json_to_postgres.py
```

The script maps the old SHA-256-based layer identifiers to the new numeric
PostgreSQL `layer_id` values. Legacy GCP records whose reference/historical
layer cannot be resolved are reported rather than inserted incorrectly.

## 5. Run the application

```bash
python app1.py
```

The application now reads/writes:

- GCPs -> PostgreSQL `gcps`
- layer metadata -> PostgreSQL `layers`
- development identity -> PostgreSQL `users`

The temporary raster COG cache remains filesystem-based because TiTiler needs
a live HTTP-accessible raster.
