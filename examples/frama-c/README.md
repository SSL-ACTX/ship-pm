# Frama-C Verification Platform Example

This example demonstrates parsing, contract checking, and AST validation of C code specified with the **ANSI/ISO C Specification Language (ACSL)** using **Frama-C**.

## Prerequisites

Install Frama-C via Ship's secondary Ubuntu pool:
```sh
ship i frama-c-base --deb
```

## Running the Example

```sh
bash examples/frama-c/run.sh
```

The script parses `linear_search.c` with its ACSL behaviors, loop invariants, and variant termination annotations, then pretty-prints the normalized AST.
