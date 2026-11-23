# Makefile for Barebones OCaml 5 Micro-Runtime & Standalone Compilation
# 100% Self-Contained Source — Zero libasmrun.a dependency!

CC ?= clang
AS ?= as
OCAMLC ?= $(CURDIR)/bin/ocamlc
OCAMLOPT ?= $(CURDIR)/bin/ocamlopt
OCAML_WHERE ?= $(CURDIR)/lib/ocaml

CFLAGS := -O2 -Wall -I$(OCAML_WHERE)
OCAMLFLAGS := -nopervasives -I $(CURDIR)/nanolib

# Modules
NANOLIB_CMI := nanolib/nano.cmi
NANOLIB_OBJ := nanolib/nano.o

EFFECTS_CMI := nanolib/nano_effects.cmi
EFFECTS_OBJ := nanolib/nano_effects.o

# Micro-Runtime Objects (Pure Source C & Assembly)
RUNTIME_OBJ := runtime/micro_runtime.o
TRAMPOLINE_OBJ := runtime/trampoline.o
EFFECTS_RUNTIME_OBJ := runtime/effects_runtime.o
EFFECTS_ARM64_OBJ := runtime/effects_arm64.o
APPLY_OBJ := runtime/apply.o
ALLOC_ARM64_OBJ := runtime/alloc_arm64.o

ALL_RUNTIME_OBJS := $(RUNTIME_OBJ) $(TRAMPOLINE_OBJ) $(EFFECTS_RUNTIME_OBJ) \
                    $(EFFECTS_ARM64_OBJ) $(APPLY_OBJ) $(ALLOC_ARM64_OBJ)

# Targets
CALC_BIN := test/calc_standalone
TREE_BIN := test/tree_standalone
EFFECT_BIN := test/effect_standalone

.PHONY: all clean run test-sizes help run-effect run-tree run-calc

all: $(NANOLIB_OBJ) $(EFFECTS_OBJ) $(ALL_RUNTIME_OBJS) $(CALC_BIN) $(TREE_BIN) $(EFFECT_BIN)

# Step 1: Base NanoStdlib
$(NANOLIB_CMI): nanolib/nano.mli
	@echo "==> Compiling NanoStdlib interface (.cmi)..."
	$(OCAMLC) $(OCAMLFLAGS) -c $<

$(NANOLIB_OBJ): nanolib/nano.ml $(NANOLIB_CMI)
	@echo "==> Compiling NanoStdlib native object (.o)..."
	$(OCAMLOPT) $(OCAMLFLAGS) -c -S $<

# Step 2: NanoEffects
$(EFFECTS_CMI): nanolib/nano_effects.mli $(NANOLIB_CMI)
	@echo "==> Compiling NanoEffects interface (.cmi)..."
	$(OCAMLC) $(OCAMLFLAGS) -c $<

$(EFFECTS_OBJ): nanolib/nano_effects.ml $(EFFECTS_CMI)
	@echo "==> Compiling NanoEffects native object (.o)..."
	$(OCAMLOPT) $(OCAMLFLAGS) -c -S $<

# Step 3: Pure Source Micro-Runtime
$(TRAMPOLINE_OBJ): runtime/trampoline.s
	@echo "==> Assembling ARM64 trampoline..."
	$(AS) $< -o $@

$(APPLY_OBJ): runtime/apply.s
	@echo "==> Assembling apply dispatch..."
	$(AS) $< -o $@

$(EFFECTS_ARM64_OBJ): runtime/effects_arm64.s
	@echo "==> Assembling effects stack-switcher..."
	$(AS) $< -o $@

$(ALLOC_ARM64_OBJ): runtime/alloc_arm64.s
	@echo "==> Assembling bump allocator..."
	$(AS) $< -o $@

$(RUNTIME_OBJ): runtime/micro_runtime.c
	@echo "==> Compiling C micro-runtime..."
	$(CC) $(CFLAGS) -c $< -o $@

$(EFFECTS_RUNTIME_OBJ): runtime/effects_runtime.c
	@echo "==> Compiling C fiber stack manager..."
	$(CC) $(CFLAGS) -c $< -o $@

# Step 4: Standalone Binaries
$(CALC_BIN): $(ALL_RUNTIME_OBJS) $(NANOLIB_OBJ) test/calc.ml
	@echo "==> Building Calc standalone binary..."
	./bare-ocamlopt test/calc.ml -o $@

$(TREE_BIN): $(ALL_RUNTIME_OBJS) $(NANOLIB_OBJ) test/tree.ml
	@echo "==> Building Tree standalone binary..."
	./bare-ocamlopt test/tree.ml -o $@

$(EFFECT_BIN): $(ALL_RUNTIME_OBJS) $(NANOLIB_OBJ) $(EFFECTS_OBJ) test/effect_demo.ml
	@echo "==> Building Effects standalone binary..."
	./bare-ocamlopt test/effect_demo.ml -o $@

run-calc: $(CALC_BIN)
	@echo "==> Running Calc Test:"
	@./$(CALC_BIN)

run-tree: $(TREE_BIN)
	@echo "==> Running Tree Test:"
	@./$(TREE_BIN)

run-effect: $(EFFECT_BIN)
	@echo "==> Running Effects Test:"
	@./$(EFFECT_BIN)

run: run-calc run-tree run-effect

test-sizes: $(CALC_BIN) $(TREE_BIN) $(EFFECT_BIN)
	@echo "==> Standalone Binary Sizes:"
	@ls -lh $(CALC_BIN) $(TREE_BIN) $(EFFECT_BIN)
	@size $(CALC_BIN) $(TREE_BIN) $(EFFECT_BIN)

clean:
	@echo "==> Cleaning generated artifacts..."
	rm -f nanolib/*.cmi nanolib/*.cmo nanolib/*.cmx nanolib/*.o nanolib/*.s
	rm -f runtime/*.o runtime/test_ptr runtime/test_offsets*
	rm -f test/*.cmi test/*.cmo test/*.cmx test/*.o test/*.s test/glue_effect.o test/effect_custom_asm test/effect_via_cli
	rm -f $(CALC_BIN) $(TREE_BIN) $(EFFECT_BIN)
