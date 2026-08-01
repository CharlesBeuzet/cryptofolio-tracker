# Position conviction tags

User-defined tags that label a **position** (asset × exchange), not individual orders.
Use them to separate theses such as “VC play” vs “backspot” when the same asset is held on different venues — or to group unrelated assets under one conviction.

## Data model

| Table / column | Role |
|----------------|------|
| `tags` | Catalog: `name` (unique), optional `description` — listed alphabetically by name |
| `positions.tag_id` | Nullable FK — at most one tag per position |

Balance sync (`update_position_from_balance`) only updates quantity / status and **preserves** `tag_id`.

## GraphQL

**Queries**

- `tags` — list catalog
- `portfolio` / `positions` / `position` — each position may include `tag { id name description }`

**Mutations**

- `createTag(name, description?)`
- `updateTag(id, …)`
- `deleteTag(id)` — clears assignments then removes the tag
- `setPositionTag(positionId, tagId)` — pass `tagId: null` to clear

## UI

- **Settings (§5)** — create tags and assign them to open positions by venue
- **Theses (§4)** — venue groups remain; a second section groups by tag
- **Overview / Position detail** — show the assigned tag chip when present

## Schema migration

`init_db()` calls `migrate_tags_schema()`, which creates `tags` if missing, `ALTER TABLE`s `positions.tag_id` on existing SQLite databases, and drops legacy `tags.color` / `tags.sort_order` when present — without wiping data.

---

← [Docs hub](README.md) · [Settings](settings.md) · [Features](features.md)
