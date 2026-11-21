# Hax: verified Rust extraction

This crate implements a lower-bound binary search and a search API that returns
either the matching index or the insertion position. The loop maintains a
strictly shrinking `lo..hi` interval; Hax translates its arithmetic and slice
accesses to F* proof obligations for panic freedom.

Run the example:

```sh
./run.sh
```

The runner first executes the Rust tests, then extracts only the two public
search functions and their dependencies to Lean. It uses a temporary copy and
removes all generated Cargo and extraction files on exit.
