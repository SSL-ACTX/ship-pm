# Verus examples

These examples use Verus to verify Rust functions and specifications. They need
the `verus` command and the matching Rust toolchain that the Verus release
requests.

Run all examples with automatic cleanup:

```sh
./run.sh
```

The script copies the sources into a temporary directory, verifies each file,
and removes that directory on exit. To verify one example directly, run
`verus min.rs` or `verus checked_add.rs` from this directory.
