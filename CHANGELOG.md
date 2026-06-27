# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

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

[0.3.0]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.3.0
[0.2.0]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.2.0
[0.1.0]: https://github.com/HL-Apprentice/homestead-inventory/releases/tag/v0.1.0
