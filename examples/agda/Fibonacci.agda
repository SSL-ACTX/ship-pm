module Fibonacci where

open import Data.Nat
open import Data.Nat.Properties
open import Relation.Binary.PropositionalEquality

-- Recursive definition of Fibonacci numbers
fib : ℕ → ℕ
fib 0 = 0
fib 1 = 1
fib (suc (suc n)) = fib (suc n) + fib n

-- Base cases verified by normalization
_ : fib 0 ≡ 0
_ = refl

_ : fib 1 ≡ 1
_ = refl

_ : fib 6 ≡ 8
_ = refl
