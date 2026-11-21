# Verus examples

This example implements lower-bound search and binary search over a sorted
vector. It verifies the loop bounds and both sides of the search partition,
then uses that contract to prove the `Option` result is either a matching index
or a correct absence result. The `main` function checks duplicates, an absent
key, and an insertion point.

It needs the `verus` command and the matching Rust toolchain that the Verus
release requests.

Run all examples with automatic cleanup:

```sh
./run.sh
```

The script copies the source into a temporary directory, verifies it, and
removes that directory on exit. To verify it directly, run
`verus lower_bound.rs` from this directory.
