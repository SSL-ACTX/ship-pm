namespace Rewriting

universe u

/-! # 1. Abstract Reduction Systems: Closures and Definitions -/

/-- Reflexive-transitive closure of a binary reduction relation R (a ↠ b). -/
inductive Star {α : Type u} (R : α → α → Prop) : α → α → Prop where
  | refl (a : α) : Star R a a
  | step {a b c : α} : R a b → Star R b c → Star R a c

/-- Symmetric-reflexive-transitive closure (conversion / equivalence closure a ↔* b). -/
inductive Conversion {α : Type u} (R : α → α → Prop) : α → α → Prop where
  | refl (a : α) : Conversion R a a
  | fwd {a b c : α} : R a b → Conversion R b c → Conversion R a c
  | bwd {a b c : α} : R b a → Conversion R b c → Conversion R a c

/-- Single step inclusion into multi-step reduction. -/
theorem Star.single {α : Type u} {R : α → α → Prop} {a b : α} (h : R a b) : Star R a b :=
  Star.step h (Star.refl b)

/-- Transitivity of multi-step reduction: a ↠ b and b ↠ c implies a ↠ c. -/
theorem Star.trans {α : Type u} {R : α → α → Prop} {a b c : α}
    (h1 : Star R a b) (h2 : Star R b c) : Star R a c := by
  induction h1 with
  | refl _ => exact h2
  | step rab _ ih => exact Star.step rab (ih h2)

/-- Transitivity of conversion closure. -/
theorem Conversion.trans {α : Type u} {R : α → α → Prop} {a b c : α}
    (h1 : Conversion R a b) (h2 : Conversion R b c) : Conversion R a c := by
  induction h1 with
  | refl _ => exact h2
  | fwd rab _ ih => exact Conversion.fwd rab (ih h2)
  | bwd rba _ ih => exact Conversion.bwd rba (ih h2)

/-- Symmetry of conversion closure. -/
theorem Conversion.symm {α : Type u} {R : α → α → Prop} {a b : α}
    (h : Conversion R a b) : Conversion R b a := by
  induction h with
  | refl x => exact Conversion.refl x
  | fwd rab _ ih =>
    have h_ba : Conversion R _ _ := Conversion.bwd rab (Conversion.refl _)
    exact Conversion.trans ih h_ba
  | bwd rba _ ih =>
    have h_ba : Conversion R _ _ := Conversion.fwd rba (Conversion.refl _)
    exact Conversion.trans ih h_ba

/-- Any reduction path is a conversion path. -/
theorem Star.to_conversion {α : Type u} {R : α → α → Prop} {a b : α}
    (h : Star R a b) : Conversion R a b := by
  induction h with
  | refl x => exact Conversion.refl x
  | step rab _ ih => exact Conversion.fwd rab ih

/-! # 2. Confluence, Normal Forms, and Termination -/

/-- Confluence (the Church-Rosser diamond property for multi-step reduction). -/
def Confluent {α : Type u} (R : α → α → Prop) : Prop :=
  ∀ a b c, Star R a b → Star R a c → ∃ d, Star R b d ∧ Star R c d

/-- Semi-confluence: a single step and a multi-step reduction can always be joined. -/
def SemiConfluent {α : Type u} (R : α → α → Prop) : Prop :=
  ∀ a b c, R a b → Star R a c → ∃ d, Star R b d ∧ Star R c d

/-- Local confluence (weak Church-Rosser): two single steps can always be joined. -/
def LocalConfluent {α : Type u} (R : α → α → Prop) : Prop :=
  ∀ a b c, R a b → R a c → ∃ d, Star R b d ∧ Star R c d

/-- The Church-Rosser property: any conversion path joins at a common reduct. -/
def ChurchRosser {α : Type u} (R : α → α → Prop) : Prop :=
  ∀ a b, Conversion R a b → ∃ d, Star R a d ∧ Star R b d

/-- A term is in normal form if it admits no further reduction steps. -/
def NormalForm {α : Type u} (R : α → α → Prop) (a : α) : Prop :=
  ∀ b, ¬ R a b

/-- Termination (Strong Normalization): reduction admits no infinite descending chains. -/
def Terminating {α : Type u} (R : α → α → Prop) : Prop :=
  WellFounded (fun x y => R y x)

/-- Uniqueness of an existential witness (pure Lean core replacement for Mathlib's ∃!). -/
def ExistsUnique {α : Sort u} (p : α → Prop) : Prop :=
  ∃ x, p x ∧ ∀ y, p y → y = x

/-! # 3. The Strip Lemma and the Church-Rosser Theorem -/

/-- Confluence trivially implies semi-confluence. -/
theorem confluent_implies_semiConfluent {α : Type u} {R : α → α → Prop}
    (h : Confluent R) : SemiConfluent R := by
  intro a b c rab rac
  exact h a b c (Star.single rab) rac

/-- The Strip Lemma: Semi-confluence implies global confluence. -/
theorem semiConfluent_implies_confluent {α : Type u} {R : α → α → Prop}
    (h : SemiConfluent R) : Confluent R := by
  intro a b c hab
  induction hab generalizing c with
  | refl _ =>
    intro rac
    exact ⟨c, rac, Star.refl c⟩
  | step raa' ha'b ih =>
    intro rac
    rcases h _ _ _ raa' rac with ⟨u, ha'u, rcu⟩
    rcases ih u ha'u with ⟨d, rbd, rud⟩
    exact ⟨d, rbd, Star.trans rcu rud⟩

/-- Confluence and semi-confluence are equivalent. -/
theorem confluent_iff_semiConfluent {α : Type u} (R : α → α → Prop) :
    Confluent R ↔ SemiConfluent R :=
  ⟨confluent_implies_semiConfluent, semiConfluent_implies_confluent⟩

/-- The Church-Rosser Theorem (Forward): Confluence implies the Church-Rosser property. -/
theorem confluent_implies_churchRosser {α : Type u} {R : α → α → Prop}
    (conf : Confluent R) : ChurchRosser R := by
  intro a b hab
  induction hab with
  | refl x =>
    exact ⟨x, Star.refl x, Star.refl x⟩
  | fwd rab _ ih =>
    rcases ih with ⟨d, hbd, hcd⟩
    exact ⟨d, Star.step rab hbd, hcd⟩
  | bwd rba _ ih =>
    rcases ih with ⟨u, hbu, hcu⟩
    have hba : Star R _ _ := Star.single rba
    rcases conf _ _ _ hba hbu with ⟨d, had, hud⟩
    exact ⟨d, had, Star.trans hcu hud⟩

/-- The Church-Rosser Theorem (Reverse): The Church-Rosser property implies confluence. -/
theorem churchRosser_implies_confluent {α : Type u} {R : α → α → Prop}
    (cr : ChurchRosser R) : Confluent R := by
  intro a b c hab hac
  have h_ba : Conversion R b a := Conversion.symm (Star.to_conversion hab)
  have h_ac : Conversion R a c := Star.to_conversion hac
  have h_bc : Conversion R b c := Conversion.trans h_ba h_ac
  exact cr b c h_bc

/-- Full equivalence of Confluence and the Church-Rosser property. -/
theorem confluent_iff_churchRosser {α : Type u} (R : α → α → Prop) :
    Confluent R ↔ ChurchRosser R :=
  ⟨confluent_implies_churchRosser, churchRosser_implies_confluent⟩

/-! # 4. Uniqueness of Normal Forms -/

/-- A normal form cannot reduce to any distinct term. -/
theorem normal_form_star {α : Type u} {R : α → α → Prop} {a b : α}
    (nf : NormalForm R a) (h : Star R a b) : a = b := by
  cases h with
  | refl _ => rfl
  | step rab _ => exact False.elim (nf _ rab)

/-- In a confluent system, normal forms are unique. -/
theorem unique_normal_forms {α : Type u} {R : α → α → Prop} (conf : Confluent R) {a b : α}
    (conv : Conversion R a b) (nfa : NormalForm R a) (nfb : NormalForm R b) : a = b := by
  have cr := confluent_implies_churchRosser conf a b conv
  rcases cr with ⟨d, had, hbd⟩
  have ha : a = d := normal_form_star nfa had
  have hb : b = d := normal_form_star nfb hbd
  rw [ha, hb]

/-! # 5. Newman's Lemma -/

/-- Newman's Lemma (1942): For terminating systems, local confluence implies global confluence. -/
theorem newman_lemma {α : Type u} {R : α → α → Prop}
    (term : Terminating R) (lc : LocalConfluent R) : Confluent R := by
  intro a
  apply term.induction a
  intro x ih b c hxb hxc
  cases hxb with
  | refl _ =>
    exact ⟨c, hxc, Star.refl c⟩
  | step rx_x₁ hx₁b =>
    cases hxc with
    | refl _ =>
      exact ⟨b, Star.refl b, Star.step rx_x₁ hx₁b⟩
    | step rx_x₂ hx₂c =>
      rcases lc x _ _ rx_x₁ rx_x₂ with ⟨u, hx₁u, hx₂u⟩
      have conf_x₁ := ih _ rx_x₁
      rcases conf_x₁ b u hx₁b hx₁u with ⟨v, hbv, huv⟩
      have hx₂v : Star R _ v := Star.trans hx₂u huv
      have conf_x₂ := ih _ rx_x₂
      rcases conf_x₂ c v hx₂c hx₂v with ⟨d, hcd, hvd⟩
      have hbd : Star R b d := Star.trans hbv hvd
      exact ⟨d, hbd, hcd⟩

/-! # 6. Normalization and Canonical Forms -/

/-- Every element in a terminating reduction system has at least one normal form. -/
theorem terminating_has_normal_form {α : Type u} {R : α → α → Prop}
    (term : Terminating R) (a : α) : ∃ b, Star R a b ∧ NormalForm R b := by
  apply term.induction a
  intro x ih
  by_cases h : ∃ y, R x y
  · rcases h with ⟨y, rxy⟩
    rcases ih y rxy with ⟨nf_y, h_star, h_nf⟩
    exact ⟨nf_y, Star.step rxy h_star, h_nf⟩
  · have h_nf : NormalForm R x := by
      intro y rxy
      exact h ⟨y, rxy⟩
    exact ⟨x, Star.refl x, h_nf⟩

/-- In a terminating and locally confluent system, every term has a unique canonical normal form. -/
theorem unique_canonical_form {α : Type u} {R : α → α → Prop}
    (term : Terminating R) (lc : LocalConfluent R) (a : α) :
    ExistsUnique (fun b => Star R a b ∧ NormalForm R b) := by
  rcases terminating_has_normal_form term a with ⟨b, hab, nfb⟩
  refine ⟨b, ⟨hab, nfb⟩, ?_⟩
  intro c ⟨hac, nfc⟩
  have conf := newman_lemma term lc
  have conv_bc : Conversion R b c :=
    Conversion.trans (Conversion.symm (Star.to_conversion hab)) (Star.to_conversion hac)
  exact (unique_normal_forms conf conv_bc nfb nfc).symm

/-- Well-founded measure induction establishes termination. -/
theorem terminating_of_measure {α : Type u} {R : α → α → Prop} (m : α → Nat)
    (h : ∀ x y, R x y → m y < m x) : Terminating R := by
  have h_acc : ∀ n (x : α), m x ≤ n → Acc (fun a b => R b a) x := by
    intro n
    induction n with
    | zero =>
      intro x hx
      constructor
      intro y (rxy : R x y)
      have := h x y rxy
      omega
    | succ n ih =>
      intro x hx
      constructor
      intro y (rxy : R x y)
      have := h x y rxy
      apply ih y
      omega
  exact ⟨fun a => h_acc (m a) a (Nat.le_refl (m a))⟩

/-! # 7. Concrete Application: A Concurrent Grid-Reduction System -/

/-- Non-deterministic reduction rules on coordinate pairs:
    Left: (a + 1, b) ⟶ (a, b)
    Right: (a, b + 1) ⟶ (a, b) -/
inductive GridStep : Nat × Nat → Nat × Nat → Prop where
  | step_left  (a b : Nat) : GridStep (a + 1, b) (a, b)
  | step_right (a b : Nat) : GridStep (a, b + 1) (a, b)

/-- The coordinate-sum measure function strictly decreases along reductions. -/
def gridMeasure (p : Nat × Nat) : Nat := p.1 + p.2

theorem gridStep_decreases : ∀ (p q : Nat × Nat), GridStep p q → gridMeasure q < gridMeasure p := by
  intro p q h
  cases h with
  | step_left a b =>
    dsimp [gridMeasure]
    omega
  | step_right a b =>
    dsimp [gridMeasure]
    omega

/-- Termination of GridStep verified via well-founded measure. -/
theorem gridStep_terminating : Terminating GridStep :=
  terminating_of_measure gridMeasure (fun x y h => gridStep_decreases x y h)

/-- Local confluence: Any non-deterministic choice joins at a common grid point. -/
theorem gridStep_localConfluent : LocalConfluent GridStep := by
  intro p q₁ q₂ h1 h2
  cases h1 with
  | step_left a b =>
    cases h2 with
    | step_left a' b' =>
      exact ⟨(a, b), Star.refl (a, b), Star.refl (a, b)⟩
    | step_right a' b' =>
      exact ⟨(a, b'), Star.single (GridStep.step_right a b'), Star.single (GridStep.step_left a b')⟩
  | step_right a b =>
    cases h2 with
    | step_left a' b' =>
      exact ⟨(a', b), Star.single (GridStep.step_left a' b), Star.single (GridStep.step_right a' b)⟩
    | step_right a' b' =>
      exact ⟨(a, b), Star.refl (a, b), Star.refl (a, b)⟩

/-- By Newman's Lemma, GridStep is globally confluent! -/
theorem gridStep_confluent : Confluent GridStep :=
  newman_lemma gridStep_terminating gridStep_localConfluent

/-- GridStep satisfies the Church-Rosser property. -/
theorem gridStep_churchRosser : ChurchRosser GridStep :=
  confluent_implies_churchRosser gridStep_confluent

/-- The origin (0, 0) is a normal form. -/
theorem gridStep_origin_normalForm : NormalForm GridStep (0, 0) := by
  intro q h
  cases h

/-- Every coordinate pair reduces to a unique canonical normal form. -/
theorem gridStep_canonical (p : Nat × Nat) :
    ExistsUnique (fun q => Star GridStep p q ∧ NormalForm GridStep q) :=
  unique_canonical_form gridStep_terminating gridStep_localConfluent p

end Rewriting

open Rewriting

-- Compile-time verification
#eval IO.println "Verification successful: ARS, Newman's Lemma, and Church-Rosser fully type-checked."
#check @newman_lemma
#check @confluent_iff_churchRosser
#check @unique_canonical_form
#check @gridStep_confluent
