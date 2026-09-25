# Change a route through M4

RouteRegistry stores an allocation high-water mark. POST /routes/{routeId}/versions allocates the next version;
the definition's routeId/version must match. GET the route first to obtain maxVersion.
Edit only DRAFT using PUT /routes/{routeId}/versions/{version} with definition and its stateVersion.
Publish with POST to the same version's /publish endpoint and {"stateVersion": currentVersionState}.
Published versions reject both HTTP editing and direct database UPDATE/DELETE.

Publishing v2 updates the route default while existing executions retain their route_version composite FK.
FoundationIT and AdmissionIT verify immutable bindings; the M3 engine reads the bound version, never the current default.
GET /routes/{routeId}/versions/1 remains available after disable and soft delete for old execution/recovery.
PATCH route metadata uses name/enabled/stateVersion. DELETE route uses query stateVersion and retains data.
DELETE an unpublished version withdraws its draft, retaining audit and never reusing its version number.

All HTTP mutations require the configured admin bearer token. Read the latest returned stateVersion before
the next mutation; stale values return 409 STATE_CONFLICT. Never edit published snapshots through a migration.
See docs/api/openapi.yaml for the actual request and response schemas. M4 adapters are candidates; public recovery remains M5.

Published versions also bind controlled adapter semantics (V6). Editing a deployment catalog does not
change an older version's meaning: queued/active/retry work blocks with IN_DOUBT if its current adapter
binding differs. Keep old bindings available until work settles, or use future audited M5 resolution;
never rewrite a published row. Publish v2 under the deliberately updated catalog to adopt new behavior.
Unknown or cross-kind refs, including rollback and notification, fail publication and retain DRAFT.

M5 recovery reads the execution-bound published version and adapter bindings, even if the route is disabled or a newer default is published. Never change an existing queued recovery to the new version; publish and submit a new execution for new semantics.
