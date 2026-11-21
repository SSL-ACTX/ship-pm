module StandaloneFib where

open import Agda.Primitive

-- Inductive natural numbers
data ℕ : Set where
  zero : ℕ
  suc  : ℕ → ℕ

_+_ : ℕ → ℕ → ℕ
zero  + n = n
suc m + n = suc (m + n)

infix 20 _+_

-- Propositional equality
data _≡_ {a} {A : Set a} (x : A) : A → Set a where
  refl : x ≡ x

{-# BUILTIN EQUALITY _≡_ #-}
infix 4 _≡_

-- Associativity theorem
+-assoc : (x y z : ℕ) → ((x + y) + z) ≡ (x + (y + z))
+-assoc zero    y z = refl
+-assoc (suc x) y z rewrite +-assoc x y z = refl

-- Fibonacci definition
fib : ℕ → ℕ
fib zero          = zero
fib (suc zero)    = suc zero
fib (suc (suc n)) = fib (suc n) + fib n

-- Base cases verified by compile-time reduction
fib-5-is-5 : fib (suc (suc (suc (suc (suc zero))))) ≡ suc (suc (suc (suc (suc zero))))
fib-5-is-5 = refl

fib-6-is-8 : fib (suc (suc (suc (suc (suc (suc zero)))))) ≡ suc (suc (suc (suc (suc (suc (suc (suc zero)))))))
fib-6-is-8 = refl
