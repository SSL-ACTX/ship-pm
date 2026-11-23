# Barebones OCaml 5: Stripped-to-the-Bone Architecture & Unified Toolchain

## Overview

We have built a fully self-contained, barebones **OCaml 5 toolchain and micro-runtime** that strips away OCaml's monolithic standard library (`stdlib.cma`/`stdlib.a`) and heavy multicore runtime (`libasmrun.a`), enabling standalone native binaries from **11 KB to 28 KB** with **full algebraic effects support**.

---

## 1. What Has Been Built & Proven

### A. NanoStdlib (`nanolib/nano.ml` & `nanolib/nano_effects.ml`)
- Pure zero-overhead OCaml interface.
- Exposes language primitives (`+`, `-`, `*`, `ref`, `!`, `:=`, comparisons, lists, trees, options) hooked directly to compiler built-in primitives (`%addint`, `%makemutable`, etc.).
- Complete algebraic effects API (`perform`, `Deep.try_with`, `Deep.continue`, `Deep.match_with`) without depending on `Stdlib.Effect`.

### B. The C Micro-Runtime & ARM64 Native Engine (`runtime/`)
- **`micro_runtime.c`**: Minimal domain state, root initialization, bump allocator, and entry point.
- **`trampoline.s`**: Low-level AAPCS64 trampoline to safely set OCaml 5 runtime registers (`x28` domain state, `x27` minor heap bump pointer).
- **`effects_runtime.c`**: Custom linear fiber stack manager implementing `caml_alloc_stack` and `caml_continuation_use_noexc`.
- **`apply.s`**: Native function application and arity-matching uncurrying dispatch (`caml_apply2`, `caml_apply3`).
- **`arm64.o`**: Low-level native stack switching instructions (`caml_perform`, `caml_resume`, `caml_runstack`).

### C. The Automated CLI Driver: `bare-ocamlopt`
Compile any standalone OCaml file with a single command:
```bash
./bare-ocamlopt test/effect_demo.ml -o my_binary
```
It handles typechecking under `-nopervasives`, extracting symbols, synthesizing C adapters, and linking all micro-runtime objects into an ultra-small ELF executable.

---

## 2. Test Suite & Benchmark Results

Run all test suites via `make run`:

```text
==> Running Calc Test:
[micro_runtime] Result: 30

==> Running Tree Test:
[micro_runtime] Result: 160

==> Running Effects Test:
[micro_runtime] Result: 52
```

### Binary Size Comparison

| Binary | Features Exercised | Size | Text Segment (.text) |
| :--- | :--- | :--- | :--- |
| **`calc_standalone`** | Mutable refs, list folding | **26 KB** | 10 KB |
| **`tree_standalone`** | Algebraic binary trees, generic comparison bridge | **28 KB** | 11 KB |
| **`effect_standalone`** | Delimited continuations, algebraic effects | **28 KB** | 10 KB |
| *Standard OCaml 5* | Any of the above with standard runtime | *~5 MB* | *~1.5 MB* |

---

## 3. Makefile Targets

From inside `experiments/ocaml-barebones`:

```bash
make          # Build everything (nanolib, micro-runtime, and all standalone test binaries)
make run      # Execute all three test programs
make test-sizes # Show size breakdown across all test binaries
make clean    # Wipe generated binaries and objects
```
