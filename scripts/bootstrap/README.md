# Bootstrap SQL

For a new empty `ai_analytics` database, execute these files in numeric order:

1. `01_governance_metadata.sql`
2. `02_identity_and_auth.sql`
3. `03_data_access.sql`
4. `04_knowledge.sql`

These files are organized by purpose for new-environment setup. Do not run them
against the current database: it has already been migrated with the versioned
files in `scripts/migrations/`.

`scripts/migrations/` is immutable migration history. New schema changes must
be added there as a new numbered file, then incorporated into the appropriate
bootstrap file.
