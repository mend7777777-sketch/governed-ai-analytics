# Operational Scripts

- `generate_mock_data.py`: load local mock warehouse data.
- `migrations/012_auth_hardening.sql`: add token-version invalidation, password lifecycle fields, and database-backed login rate limits to an existing database.
- `migrations/013_productization.sql`: add knowledge versions, metric definitions, query history, and metadata audit fields to an existing database.
- Training scripts will be moved here after the knowledge module is separated.

Scripts are not imported by the API process.
