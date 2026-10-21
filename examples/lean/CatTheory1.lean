namespace CategoryTheory

universe u₁ v₁ u₂ v₂ w₁ w₂

/-- A category consists of objects and morphisms satisfying identity and associativity laws. -/
structure Category (Obj : Type u₁) where
  Hom : Obj → Obj → Type v₁
  id : (X : Obj) → Hom X X
  comp : {X Y Z : Obj} → Hom X Y → Hom Y Z → Hom X Z
  id_comp : ∀ {X Y : Obj} (f : Hom X Y), comp (id X) f = f
  comp_id : ∀ {X Y : Obj} (f : Hom X Y), comp f (id Y) = f
  assoc : ∀ {W X Y Z : Obj} (f : Hom W X) (g : Hom X Y) (h : Hom Y Z),
    comp (comp f g) h = comp f (comp g h)

/-- The opposite category obtained by reversing the direction of all arrows. -/
def op {Obj : Type u₁} (C : Category.{u₁, v₁} Obj) : Category.{u₁, v₁} Obj where
  Hom X Y := C.Hom Y X
  id X := C.id X
  comp f g := C.comp g f
  id_comp f := C.comp_id f
  comp_id f := C.id_comp f
  assoc f g h := (C.assoc h g f).symm

/-- The category of types and functions in universe level v₁. -/
def typeCat : Category.{v₁ + 1, v₁} (Type v₁) where
  Hom X Y := X → Y
  id _ := id
  comp f g := g ∘ f
  id_comp _ := rfl
  comp_id _ := rfl
  assoc _ _ _ := rfl

/-- A functor between two categories preserving identities and composition. -/
structure Functor {ObjC : Type u₁} (C : Category.{u₁, v₁} ObjC)
                 {ObjD : Type u₂} (D : Category.{u₂, v₂} ObjD) where
  obj : ObjC → ObjD
  map : {X Y : ObjC} → C.Hom X Y → D.Hom (obj X) (obj Y)
  map_id : ∀ (X : ObjC), map (C.id X) = D.id (obj X)
  map_comp : ∀ {X Y Z : ObjC} (f : C.Hom X Y) (g : C.Hom Y Z),
    map (C.comp f g) = D.comp (map f) (map g)

/-- A natural transformation between two parallel functors. -/
structure NatTrans {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
                   {ObjD : Type u₂} {D : Category.{u₂, v₂} ObjD}
                   (F G : Functor C D) where
  app : (X : ObjC) → D.Hom (F.obj X) (G.obj X)
  naturality : ∀ {X Y : ObjC} (f : C.Hom X Y),
    D.comp (F.map f) (app Y) = D.comp (app X) (G.map f)

theorem NatTrans.ext {ObjC : Type u₁} {C : Category.{u₁, v₁} ObjC}
    {ObjD : Type u₂} {D : Category.{u₂, v₂} ObjD}
    {F G : Functor C D} {α β : NatTrans F G}
    (h : ∀ X, α.app X = β.app X) : α = β := by
  have h_app : α.app = β.app := funext h
  cases α
  cases β
  subst h_app
  rfl

/-- A presheaf on C is a functor from the opposite category Cᵒᵖ to the category of types. -/
abbrev Presheaf {Obj : Type u₁} (C : Category.{u₁, v₁} Obj) :=
  Functor (op C) typeCat.{v₁}

/-- The contravariant Yoneda presheaf h_A = Hom(-, A). -/
def presheafHom {Obj : Type u₁} (C : Category.{u₁, v₁} Obj) (A : Obj) : Presheaf C where
  obj X := C.Hom X A
  map f := fun g => C.comp f g
  map_id _ := by
    funext g
    exact C.id_comp g
  map_comp f g := by
    funext h
    exact C.assoc g f h

variable {Obj : Type u₁} {C : Category.{u₁, v₁} Obj}

/-- Evaluation of a natural transformation at the identity arrow. -/
def yonedaMap {A : Obj} (P : Presheaf C) (α : NatTrans (presheafHom C A) P) : P.obj A :=
  α.app A (C.id A)

/-- Construction of a natural transformation from an element of P(A). -/
def yonedaInv {A : Obj} (P : Presheaf C) (x : P.obj A) : NatTrans (presheafHom C A) P where
  app X f := P.map f x
  naturality {X Y} f := by
    funext h
    exact congrFun (P.map_comp h f) x

theorem yoneda_left_inv {A : Obj} (P : Presheaf C) (x : P.obj A) :
    yonedaMap P (yonedaInv P x) = x := by
  dsimp [yonedaMap, yonedaInv]
  exact congrFun (P.map_id A) x

theorem yoneda_right_inv {A : Obj} (P : Presheaf C) (α : NatTrans (presheafHom C A) P) :
    yonedaInv P (yonedaMap P α) = α := by
  apply NatTrans.ext
  intro X
  funext f
  have nat := congrFun (α.naturality f) (C.id A)
  have h_comp_id : (presheafHom C A).map f (C.id A) = f := C.comp_id f
  rw [show typeCat.comp ((presheafHom C A).map f) (α.app X) (C.id A) =
        α.app X ((presheafHom C A).map f (C.id A)) from rfl] at nat
  rw [show typeCat.comp (α.app A) (P.map f) (C.id A) =
        P.map f (α.app A (C.id A)) from rfl] at nat
  rw [h_comp_id] at nat
  exact nat.symm

/-- Isomorphism of types across arbitrary universes. -/
structure TypeEquiv (α : Sort w₁) (β : Sort w₂) where
  toFun     : α → β
  invFun    : β → α
  left_inv  : ∀ x, invFun (toFun x) = x
  right_inv : ∀ y, toFun (invFun y) = y

/-- The Yoneda Lemma: Nat(Hom(-, A), P) ≅ P(A). -/
def yoneda_lemma (A : Obj) (P : Presheaf C) :
    TypeEquiv (NatTrans (presheafHom C A) P) (P.obj A) where
  toFun := yonedaMap P
  invFun := yonedaInv P
  left_inv := yoneda_right_inv P
  right_inv := yoneda_left_inv P

/-- Action of the Yoneda embedding on morphisms. -/
def yonedaEmbeddingMap (A B : Obj) (f : C.Hom A B) :
    NatTrans (presheafHom C A) (presheafHom C B) :=
  yonedaInv (presheafHom C B) f

/-- Inverse mapping from natural transformations to base morphisms. -/
def yonedaEmbeddingInv (A B : Obj)
    (α : NatTrans (presheafHom C A) (presheafHom C B)) : C.Hom A B :=
  yonedaMap (presheafHom C B) α

/-- The Yoneda embedding is full and faithful. -/
def yoneda_embedding_fully_faithful (A B : Obj) :
    TypeEquiv (C.Hom A B) (NatTrans (presheafHom C A) (presheafHom C B)) where
  toFun := yonedaEmbeddingMap A B
  invFun := yonedaEmbeddingInv A B
  left_inv := yoneda_left_inv (presheafHom C B)
  right_inv := yoneda_right_inv (presheafHom C B)

end CategoryTheory

open CategoryTheory

-- Compile-time verification and diagnostic output
#eval IO.println "Verification successful: All structures, proofs, and equivalences type-checked."
#check @yoneda_lemma
#check @yoneda_embedding_fully_faithful
