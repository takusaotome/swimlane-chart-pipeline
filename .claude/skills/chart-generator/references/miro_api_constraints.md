# Miro API Constraints

## Rate Limits

| Item | Specification |
|---|---|
| Rate limit | 100,000 credits/min |
| Level 1 call cost | 50 credits/call |
| Effective limit | ~2,000 calls/min |
| Bulk create max | 20 items/batch |

## Retry Strategy

| Item | Specification |
|---|---|
| Retry strategy | Exponential backoff (1s, 2s, 4s) |
| Max retries | 3 per request |
| 429 response | Respect Retry-After header; fallback to backoff |
| Bulk failure | Transactional (all or nothing per batch) |

## Shape Constraints

| Item | Specification |
|---|---|
| Minimum dimension | 8px (width and height) |
| Shape types | rectangle, circle, rhombus, round_rectangle, etc. |
| Text in shapes | Supports `<br>` for line breaks |
| Connector snap | "auto" snap to closest edge point |

## Frame Operations

- Frame creation: POST /v2/boards/{board_id}/frames
- Frame items listing: GET /v2/boards/{board_id}/frames/{frame_id}/items
- Items in frames are positioned relative to the board, not the frame
- Frame acts as a container/grouping mechanism

## Connector Constraints

- Connectors are NOT part of bulk operations
- Must be created one at a time via POST /v2/boards/{board_id}/connectors
- Requires startItem.id and endItem.id to reference existing items
- Supported shapes: straight, elbowed, curved
- Captions positioned by percentage along the path

## Deletion Order

When cleaning up, delete in this order to avoid orphan references:
1. Connectors (reference shapes)
2. Shapes and text items
3. Frame (container)

## Batch Creation Notes

- Bulk endpoint: POST /v2/boards/{board_id}/items/bulk
- Body: JSON array of up to 20 items
- Response: `{"type": "bulk_operation", "data": [...]}`
- Items are created in order; response array preserves order
- Use this order correspondence for key-to-ID mapping
