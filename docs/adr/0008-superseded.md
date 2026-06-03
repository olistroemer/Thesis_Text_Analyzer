# ADR-0008: (superseded)

**Status:** Superseded by [ADR-0006](0006-schema.md)
**Date:** 2026-06-03

## Context

A previous proposal split the schema into two: a "professor's local DB" with no source awareness, and a separate "researcher's merged DB" with a `sources` table and a `source_id` prepended to every primary key.

## What replaced it

The decision was reversed: ADR-0006 (revision 3) adopts a single unified schema with an optional `source_id` dimension. The local DB has exactly one `source` row with `kind='local'`; researcher imports add rows with `kind='imported'`. Same code paths, same migrations, same schema file — the source dimension is implicit in the local case and explicit in the merged case.

The hole in the numbering is preserved deliberately for historical traceability.

## Why it was reversed

User feedback: "I'm not that fond of the idea of two different tools/schema right now. Let's stay with the more complex version for now." Maintaining two schemas would have meant migrations in lockstep and a sister-tool packaging story, adding complexity that wasn't yet justified.

If we ever do split the tools later, the schema would not need to change — only the entry point.
