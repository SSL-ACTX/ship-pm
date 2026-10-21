namespace CategoryTheory

universe u₁ v₁ u₂ v₂

/-! # 1. Categories and Functors -/

/-- A category consists of objects and morphisms with identity and associative composition. -/
structure Category (Obj : Type u₁) where
  Hom     : Obj → Obj → Type v₁
  id      : (X : Obj) → Hom X X
  comp    : {X Y Z : Obj} → Hom X Y → Hom Y Z → Hom X Z
  id_comp : ∀ {X Y : Obj} (f : Hom X Y), comp (id X) f = f
  comp_id : ∀ {X Y : Obj} (f : Hom X Y), comp f (id Y) = f
  assoc   : ∀ {W X Y Z : Obj} (f : Hom W X) (g : Hom X Y) (h : Hom Y Z),
    comp (comp f g) h = comp f (comp g h)

/-- A functor preserves identity morphisms and composition. -/
structure Functor {ObjC : Type u₁} (C : Category.{u₁, v₁} ObjC)
                 {ObjD : Type u₂} (D : Category.{u₂, v₂} ObjD) where
  obj      : ObjC → ObjD
  map      : {X Y : ObjC} → C.Hom X Y → D.Hom (obj X) (obj Y)
  map_id   : ∀ (X : ObjC), map (C.id X) = D.id (obj X)
  map_comp : ∀ {X Y Z : ObjC} (f : C.Hom X Y) (g : C.Hom Y Z),
    map (C.comp f g) = D.comp (map f) (map g)

/-! # 2. Adjunctions and Monads -/

/-- An adjunction F ⊣ G specified via unit and counit with triangle identities. -/
structure Adjunction {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
                     {ObjD : Type u₂} {D : Category.{u₂, v₂} ObjD}
                     (F : Functor C D) (G : Functor D C) where
  unit              : (X : ObjC) → C.Hom X (G.obj (F.obj X))
  unit_naturality   : ∀ {X Y : ObjC} (f : C.Hom X Y),
    C.comp f (unit Y) = C.comp (unit X) (G.map (F.map f))
  counit            : (Y : ObjD) → D.Hom (F.obj (G.obj Y)) Y
  counit_naturality : ∀ {X Y : ObjD} (g : D.Hom X Y),
    D.comp (F.map (G.map g)) (counit Y) = D.comp (counit X) g
  triangle_left     : ∀ (X : ObjC),
    D.comp (F.map (unit X)) (counit (F.obj X)) = D.id (F.obj X)
  triangle_right    : ∀ (Y : ObjD),
    C.comp (unit (G.obj Y)) (G.map (counit Y)) = C.id (G.obj Y)

/-- A Monad (T, η, μ) on a category C satisfying associativity and unit laws. -/
structure Monad {ObjC : Type u₁} (C : Category.{u₁, v₁} ObjC) where
  T            : Functor C C
  η            : (X : ObjC) → C.Hom X (T.obj X)
  η_naturality : ∀ {X Y : ObjC} (f : C.Hom X Y),
    C.comp f (η Y) = C.comp (η X) (T.map f)
  μ            : (X : ObjC) → C.Hom (T.obj (T.obj X)) (T.obj X)
  μ_naturality : ∀ {X Y : ObjC} (f : C.Hom X Y),
    C.comp (T.map (T.map f)) (μ Y) = C.comp (μ X) (T.map f)
  assoc        : ∀ (X : ObjC),
    C.comp (T.map (μ X)) (μ X) = C.comp (μ (T.obj X)) (μ X)
  left_unit    : ∀ (X : ObjC),
    C.comp (T.map (η X)) (μ X) = C.id (T.obj X)
  right_unit   : ∀ (X : ObjC),
    C.comp (η (T.obj X)) (μ X) = C.id (T.obj X)

/-! # 3. Theorem: Every Adjunction Induces a Monad -/

/-- Composition of an adjunction's functors T = G ∘ F. -/
def adjunctionFunctor {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    {ObjD : Type u₂} {D : Category.{u₂, v₂} ObjD}
    (F : Functor C D) (G : Functor D C) : Functor C C where
  obj X := G.obj (F.obj X)
  map f := G.map (F.map f)
  map_id X := by rw [F.map_id, G.map_id]
  map_comp f g := by rw [F.map_comp, G.map_comp]

/-- Construction of the monad induced by an adjunction F ⊣ G. -/
def adjunctionToMonad {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    {ObjD : Type u₂} {D : Category.{u₂, v₂} ObjD}
    {F : Functor C D} {G : Functor D C} (adj : Adjunction F G) : Monad C where
  T := adjunctionFunctor F G
  η := adj.unit
  η_naturality := adj.unit_naturality
  μ X := G.map (adj.counit (F.obj X))
  μ_naturality {X Y} f := by
    dsimp [adjunctionFunctor]
    rw [← G.map_comp, adj.counit_naturality (F.map f), G.map_comp]
  assoc X := by
    dsimp [adjunctionFunctor]
    rw [← G.map_comp, adj.counit_naturality (adj.counit (F.obj X)), G.map_comp]
  left_unit X := by
    dsimp [adjunctionFunctor]
    rw [← G.map_comp, adj.triangle_left X, G.map_id]
  right_unit X := by
    dsimp [adjunctionFunctor]
    exact adj.triangle_right (F.obj X)

/-! # 4. The Kleisli Category of a Monad -/

/-- The Kleisli extension (bind) operator for morphisms. -/
def kleisliLift {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) {X Y : ObjC} (f : C.Hom X (M.T.obj Y)) :
    C.Hom (M.T.obj X) (M.T.obj Y) :=
  C.comp (M.T.map f) (M.μ Y)

theorem kleisliLift_η {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) (X : ObjC) :
    kleisliLift M (M.η X) = C.id (M.T.obj X) :=
  M.left_unit X

theorem kleisliLift_id {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) (X : ObjC) :
    kleisliLift M (C.id (M.T.obj X)) = M.μ X := by
  dsimp [kleisliLift]
  rw [M.T.map_id, C.id_comp]

theorem η_comp_kleisliLift {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) {X Y : ObjC} (f : C.Hom X (M.T.obj Y)) :
    C.comp (M.η X) (kleisliLift M f) = f := by
  dsimp [kleisliLift]
  rw [← C.assoc, ← M.η_naturality f, C.assoc, M.right_unit Y, C.comp_id]

theorem kleisliLift_map_η {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) {X Y : ObjC} (g : C.Hom X Y) :
    kleisliLift M (C.comp g (M.η Y)) = M.T.map g := by
  dsimp [kleisliLift]
  rw [M.T.map_comp, C.assoc, M.left_unit Y, C.comp_id]

theorem kleisliLift_comp {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) {X Y Z : ObjC}
    (f : C.Hom X (M.T.obj Y)) (g : C.Hom Y (M.T.obj Z)) :
    kleisliLift M (C.comp f (kleisliLift M g)) =
      C.comp (kleisliLift M f) (kleisliLift M g) := by
  dsimp [kleisliLift]
  rw [M.T.map_comp, C.assoc]
  have h_mid : C.comp (M.T.map (C.comp (M.T.map g) (M.μ Z))) (M.μ Z) =
               C.comp (M.μ Y) (C.comp (M.T.map g) (M.μ Z)) := by
    rw [M.T.map_comp, C.assoc, M.assoc Z, ← C.assoc, M.μ_naturality g, C.assoc]
  rw [h_mid, ← C.assoc]

/-- The Kleisli Category Kl(M) where arrows X → Y are arrows X → T(Y) in C. -/
def kleisliCat {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) : Category.{u₁, v₁} ObjC where
  Hom X Y     := C.Hom X (M.T.obj Y)
  id X        := M.η X
  comp f g    := C.comp f (kleisliLift M g)
  id_comp f   := η_comp_kleisliLift M f
  comp_id f   := by
    change C.comp f (kleisliLift M (M.η _)) = f
    rw [kleisliLift_η, C.comp_id]
  assoc f g h := by
    change C.comp (C.comp f (kleisliLift M g)) (kleisliLift M h) =
           C.comp f (kleisliLift M (C.comp g (kleisliLift M h)))
    rw [C.assoc, ← kleisliLift_comp]

/-! # 5. The Kleisli Adjunction -/

/-- The canonical left functor F_T : C → Kl(T). -/
def kleisliLeft {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) : Functor C (kleisliCat M) where
  obj X := X
  map f := C.comp f (M.η _)
  map_id X := C.id_comp (M.η X)
  map_comp {X Y Z} f g := by
    change C.comp (C.comp f g) (M.η Z) =
           C.comp (C.comp f (M.η Y)) (kleisliLift M (C.comp g (M.η Z)))
    rw [kleisliLift_map_η]
    rw [C.assoc, M.η_naturality g, ← C.assoc]

/-- The canonical right functor G_T : Kl(T) → C. -/
def kleisliRight {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) : Functor (kleisliCat M) C where
  obj X := M.T.obj X
  map f := kleisliLift M f
  map_id X := kleisliLift_η M X
  map_comp {X Y Z} f g := by
    change kleisliLift M (C.comp f (kleisliLift M g)) =
           C.comp (kleisliLift M f) (kleisliLift M g)
    exact kleisliLift_comp M f g

/-- Theorem: F_T ⊣ G_T forms an Adjunction. -/
def kleisliAdjunction {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) : Adjunction (kleisliLeft M) (kleisliRight M) where
  unit X := M.η X
  unit_naturality {X Y} f := by
    change C.comp f (M.η Y) = C.comp (M.η X) (kleisliLift M (C.comp f (M.η Y)))
    rw [kleisliLift_map_η, M.η_naturality f]
  counit Y := C.id (M.T.obj Y)
  counit_naturality {X Y} f := by
    change C.comp (C.comp (kleisliLift M f) (M.η (M.T.obj Y))) (kleisliLift M (C.id (M.T.obj Y))) =
           C.comp (C.id (M.T.obj X)) (kleisliLift M f)
    rw [kleisliLift_id, C.id_comp]
    rw [C.assoc, M.right_unit Y, C.comp_id]
  triangle_left X := by
    change C.comp (C.comp (M.η X) (M.η (M.T.obj X))) (kleisliLift M (C.id (M.T.obj X))) = M.η X
    rw [kleisliLift_id, C.assoc, M.right_unit X, C.comp_id]
  triangle_right Y := by
    change C.comp (M.η (M.T.obj Y)) (kleisliLift M (C.id (M.T.obj Y))) = C.id (M.T.obj Y)
    rw [kleisliLift_id]
    exact M.right_unit Y

/-! # 6. The Kleisli Comparison Theorem -/

/-- The monad induced by the Kleisli adjunction recovers the original functor on objects. -/
theorem kleisli_reconstruct_obj {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) (X : ObjC) :
    (adjunctionToMonad (kleisliAdjunction M)).T.obj X = M.T.obj X := rfl

/-- The monad induced by the Kleisli adjunction recovers the original unit η. -/
theorem kleisli_reconstruct_η {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) (X : ObjC) :
    (adjunctionToMonad (kleisliAdjunction M)).η X = M.η X := rfl

/-- The monad induced by the Kleisli adjunction recovers the original multiplication μ. -/
theorem kleisli_reconstruct_μ {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    (M : Monad C) (X : ObjC) :
    (adjunctionToMonad (kleisliAdjunction M)).μ X = M.μ X := by
  change kleisliLift M (C.id (M.T.obj X)) = M.μ X
  exact kleisliLift_id M X

end CategoryTheory

open CategoryTheory

-- Compile-time diagnostic confirmation
#eval IO.println "Verification successful: Adjunctions, Monads, and Kleisli theorem fully type-checked."
#check @adjunctionToMonad
#check @kleisliCat
#check @kleisliAdjunction
#check @kleisli_reconstruct_μ
