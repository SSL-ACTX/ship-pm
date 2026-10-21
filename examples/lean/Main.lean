
inductive Expr where
  | num : Nat → Expr
  | add : Expr → Expr → Expr
  | mul : Expr → Expr → Expr
  deriving Repr, DecidableEq

open Expr

def eval : Expr → Nat
  | num n   => n
  | add a b => eval a + eval b
  | mul a b => eval a * eval b

-- Simplify recursively and fold constant operations.
def simplify : Expr → Expr
  | num n => num n
  | add a b =>
      let a' := simplify a
      let b' := simplify b
      match a', b' with
      | num x, num y => num (x + y)
      | _, _ => add a' b'
  | mul a b =>
      let a' := simplify a
      let b' := simplify b
      match a', b' with
      | num x, num y => num (x * y)
      | _, _ => mul a' b'

def exampleExpr : Expr :=
  mul (add (num 2) (num 3))
      (add (num 0) (num 4))

#eval eval exampleExpr
#eval simplify exampleExpr
#eval eval (simplify exampleExpr)

-- The simplifier preserves the expression's value.
theorem simplify_correct (e : Expr) :
    eval (simplify e) = eval e := by
  induction e with
  | num n =>
      rfl
  | add a b ihA ihB =>
      simp only [simplify]
      split <;> simp_all [eval]
  | mul a b ihA ihB =>
      simp only [simplify]
      split <;> simp_all [eval]
