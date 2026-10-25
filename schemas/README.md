# Schemas

`resume.schema.json` — JSON Schema (draft-07 subset) for the canonical resume data. The engine validates against it with its own
small validator (`resume_design/schema_check.py`: `type`, `enum`, `required`, `properties`, `items`, `oneOf`, local `$ref`,
`minimum`/`maximum`), so no `jsonschema` package is needed. Other validators (e.g. `jsonschema`) can use the file directly.

Field semantics, placeholder format and the Markdown dialect: `../core/data-model.md`.
Unknown extra properties are allowed (forward compatibility) but ignored by the renderers.
Schema errors are reported as finding `schema` (blocking error) with the field path.
