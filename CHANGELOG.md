# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.4.2] - 2026-07-02

### Security & stability
A multi-round, four-model security + stability review (Claude + Grok + Gemini +
a local Qwen learner) surfaced and fixed:
- **Path traversal (Windows):** image deletion now validates filenames against a
  strict allowlist (matching how they're served) instead of an ad-hoc blocklist,
  closing an arbitrary-file-delete vector on Windows hosts.
- **Authorization:** the four services (`consume`, `consume_barcode`,
  `set_quantity`, `low_stock_to_todo`) now honor the **`require_admin`** option;
  the **`allow_structure_modification`** option is now enforced server-side (not
  just in the UI); and the dangerous operations — **deletes, image upload,
  backup import, and the outbound barcode lookup** — always require an admin,
  regardless of the toggle. Everyday actions (adding items, adjusting/consuming
  quantities) and automations/scripts (system context) are unaffected.
- **Crash-safety:** a malformed/empty request body returns a clean `400` instead
  of an unhandled `500`; importing a backup with a bad quantity is tolerated; and
  the low-stock-to-todo service reports a clean error instead of throwing if the
  target to-do list is unavailable.

No schema change; upgrading from v0.4.1 is seamless.

## [0.4.1] - 2026-07-02

### Fixed
A recursive three-model correctness review (Claude + Grok + Gemini, run to
convergence) found and fixed a batch of frontend + robustness bugs:
- **QR deep links** now work for names with accents, emoji, or any non-ASCII
  character (previously `btoa` threw and the QR silently failed); legacy codes
  still decode. Hostile/malformed deep links can no longer blank the panel.
- Failed saves/deletes in dialogs now show an error and recover instead of
  wedging on a disabled button; the QR download and scan-to-consume report the
  right message on failure.
- Image upload no longer crashes on failure (a React hook was called from a
  non-component); the camera scanner no longer risks a stale callback.
- `consume_barcode` service is now atomic (resolve + decrement under one lock).
- A full "replace" import now deletes the old, now-unreferenced image files.
- Removed a dead deep-link endpoint; assorted correctness and consistency fixes.

## [0.4.0] - 2026-06-26

### Added
- **Home Assistant services** for automations:
  - `homestead_inventory.consume` — decrement an item by id.
  - `homestead_inventory.consume_barcode` — decrement the item with a barcode.
  - `homestead_inventory.set_quantity` — set an item's quantity exactly.
  - `homestead_inventory.low_stock_to_todo` — append every low-stock item to a
    to-do list.
- **Backup & restore** — export the whole inventory (rooms → items, including
  empty containers) to a JSON file, and import it back. Import can **merge**
  (no duplicates) or **replace** (wipe first). New endpoints
  `GET /api/homestead_inventory/export` and `POST /api/homestead_inventory/import`,
  plus a "Backup" dialog in the panel.
- A **dark-theme icon** variant for the Home Assistant brands repository.

## [0.3.0] - 2026-06-26

### Added
- **Scan to consume** — scan a barcode from the Rooms screen to decrement the
  matching item by one (fires the `homestead_inventory_item_consumed` event).
- **Consumption history & analytics** — every quantity change is recorded.
  View an item's timeline plus computed rates (daily/weekly use, estimated days
  left, total used) over a selectable window. New endpoints:
  `GET /api/homestead_inventory/items/{id}/history` and
  `GET /api/homestead_inventory/items/{id}/consumption_rates`.

### Changed
- The camera scanner is now **lazy-loaded**, so the panel's initial bundle is
  small for users who never open the scanner.

### Database
- Schema **v3**: adds a `consumption_history` table. Migrated in place from v2;
  existing data is preserved.

## [0.2.0] - 2026-06-25

### Added
- **Barcode support** — store a barcode per item.
- **Scan to find** — scan a barcode to jump to the matching item.
- **In-app camera scanner** (ZXing) when adding/editing an item. Camera access
  requires a secure context (HTTPS or the Companion app); manual entry always
  works.
- **Optional product-name lookup** via Open Food Facts (off by default; the only
  outbound call the integration makes).

### Database
- Schema **v2**: adds an indexed `barcode` column to items (in-place migration).

## [0.1.0] - 2026-06-25

### Added
- Initial release: a home inventory manager with a dedicated sidebar panel
  (Rooms → Cupboards → Shelves → Organizers → Items), per-item photos, quantity
  tracking with minimum thresholds, low-stock events, printable QR location
  labels, and three sensors (total / low-stock / tracked items).
- Hardened async-SQLite backend (foreign-key enforcement, WAL, busy_timeout,
  schema versioning), signed/expiring image URLs, optional admin-only access.
- 100% local by default; English-only UI.

[0.4.2]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.4.2
[0.4.1]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.4.1
[0.4.0]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.4.0
[0.3.0]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.3.0
[0.2.0]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.2.0
[0.1.0]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.1.0
