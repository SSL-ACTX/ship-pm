From iris.heap_lang Require Import adequacy.
From iris.heap_lang.lib Require Import assert.
From multris.channel Require Import proofmode.

(** Inspired by https://en.wikipedia.org/wiki/Chang_and_Roberts_algorithm *)

Definition process : val :=
  rec: "go" "c" "idl" "id" "idr" "isp" :=
    if: recv "c" "idr"
    then let: "id'" := recv "c" "idr" in
         if: "id" < "id'"          (** Case 1 *)
         then send "c" "idl" #true;; send "c" "idl" "id'";;
              "go" "c" "idl" "id" "idr" #true
         else if: "id" = "id'"     (** Case 4 *)
         then send "c" "idl" #false;; send "c" "idl" "id";;
              "go" "c" "idl" "id" "idr" #false
         else if: "isp" (** Case 3 *)
         then "go" "c" "idl" "id" "idr" "isp" (** Case 2 *)
         else send "c" "idl" #true;; send "c" "idl" "id";;
              "go" "c" "idl" "id" "idr" #true
    else let: "id'" := recv "c" "idr" in
         if: "id" = "id'" then "id'"
         else send "c" "idl" #false;; send "c" "idl" "id'";; "id'".

Definition init : val :=
  λ: "c" "idl" "id" "idr",
    send "c" "idl" #true;; send "c" "idl" "id";;
    process "c" "idl" "id" "idr" #true.

Abbreviation iProto_choice a p1 p2 :=
  (<a @ (b : bool)> MSG #b; if b then p1 else p2)%proto.

Section ring_leader_election_protocols.
  Context `{!heapGS Σ, chanG Σ}.

  Definition my_recv_prot (il i ir : nat) (P : iProp Σ) (p : nat → iProto Σ)
             (rec : bool -d> iProto Σ) : bool -d> iProto Σ :=
    λ (isp:bool),
      iProto_choice (Recv,ir)
        (<(Recv,ir) @ (i':nat)> MSG #i';
         if bool_decide (i < i')
         then <(Send,il)> MSG #true ; <(Send,il)> MSG #i' ; rec true
         else if bool_decide (i = i')
         then <(Send,il)> MSG #false ; <(Send, il)> MSG #i ; rec false
         else if isp then rec isp
         else <(Send,il)> MSG #true ; <(Send,il)> MSG #i ; rec true)%proto
        (<(Recv,ir) @ (i':nat)> MSG #i'
           {{ if bool_decide (i = i') then P else True%I }};
         if (bool_decide (i = i')) then p i
         else <(Send,il)> MSG #false; <(Send,il)> MSG #i'; p i')%proto.

  Instance rle_prot_aux_contractive il i ir P p :
    Contractive (my_recv_prot il i ir P p).
  Proof. rewrite /my_recv_prot. solve_proto_contractive. Qed.
  Definition rle_prot il i ir P p := fixpoint (my_recv_prot il i ir P p).
  Instance rle_prot_unfold il i ir isp P p :
    ProtoUnfold (rle_prot il i ir P p isp)
                (my_recv_prot il i ir P p (rle_prot il i ir P p) isp).
  Proof. apply proto_unfold_eq, (fixpoint_unfold (my_recv_prot il i ir P p)). Qed.
  Lemma rle_prot_unfold' il i ir isp P p :
    (rle_prot il i ir P p isp) ≡
    (my_recv_prot il i ir P p (rle_prot il i ir P p) isp).
  Proof. apply (fixpoint_unfold (my_recv_prot il i ir P p)). Qed.

  Definition rle_preprot (il i ir : nat) P p : iProto Σ :=
    (<(Send, il)> MSG #true; <(Send, il)> MSG #i {{ P }} ;
    rle_prot il i ir P p true)%proto.

  Lemma process_spec il i ir P p c (isp:bool) :
    {{{ c ↣ (rle_prot il i ir P p isp) }}}
      process c #il #i #ir #isp
    {{{ i', RET #i'; c ↣ p i' ∗ if (bool_decide (i = i')) then P else True%I }}}.
  Proof.
    iIntros (Φ) "Hc HΦ".
    iLöb as "IH" forall (Φ isp).
    wp_lam. wp_recv (b) as "_".
    destruct b.
    - wp_recv (i') as "_".
      wp_pures. case_bool_decide as Hlt.
      { case_bool_decide; [|lia].
        wp_send with "[//]". wp_send with "[//]".
        wp_smart_apply ("IH" with "Hc HΦ"). }
      case_bool_decide as Hlt2.
      { case_bool_decide; [lia|]. wp_pures. case_bool_decide; [|simplify_eq;lia].
        wp_send with "[//]". wp_send with "[//]".
        wp_smart_apply ("IH" with "Hc HΦ"). }
      case_bool_decide; [lia|].
      wp_pures. case_bool_decide; [simplify_eq;lia|]. wp_pures.
      destruct isp; [by wp_smart_apply ("IH" with "Hc HΦ")|].
      wp_send with "[//]". wp_send with "[//]".
      wp_smart_apply ("IH" with "Hc HΦ").
    - wp_recv (id') as "HP". wp_pures.
      case_bool_decide as Hlt.
      { case_bool_decide; [|simplify_eq;lia].
        wp_pures. subst. iApply "HΦ". iFrame. by case_bool_decide. }
      case_bool_decide; [simplify_eq;lia|].
      wp_send with "[//]". wp_send with "[//]". wp_pures. iApply "HΦ".
      iFrame. by case_bool_decide; [simplify_eq;lia|].
  Qed.

  Lemma init_spec c il i ir p P :
    {{{ c ↣ rle_preprot il i ir P p ∗ P }}}
      init c #il #i #ir
    {{{ i', RET #i'; c ↣ p i' ∗ if (bool_decide (i = i')) then P else True%I }}}.
  Proof.
    iIntros (Φ) "[Hc HP] HΦ". wp_lam. wp_send with "[//]". wp_send with "[HP//]".
    wp_smart_apply (process_spec with "Hc HΦ").
  Qed.

End ring_leader_election_protocols.

Definition rle_ref_prog : val :=
  λ: <>,
     let: "l" := ref #42 in
     let: "cs" := new_chan #4 in
     let: "c0" := get_chan "cs" #0 in
     let: "c1" := get_chan "cs" #1 in
     let: "c2" := get_chan "cs" #2 in
     let: "c3" := get_chan "cs" #3 in
     Fork (let: "id_max" := process "c1" #0 #1 #2 #false in
           if: "id_max" = #1 then Free "l" else #());;
     Fork (let: "id_max" := process "c2" #1 #2 #3 #false in
           if: "id_max" = #2 then Free "l" else #());;
     Fork (let: "id_max" := process "c3" #2 #3 #0 #false in
           if: "id_max" = #3 then Free "l" else #());;
     let: "id_max" := init "c0" #3 #0 #1 in
     if: "id_max" = #0 then Free "l" else #().

Section rle_ref_prog_proof.
  Context `{!heapGS Σ, chanG Σ}.

  Definition rle_ref_prog_prot_pool P : list (iProto Σ) :=
     [rle_preprot 3 0 1 P (λ id_max, END)%proto;
      rle_prot 0 1 2 P (λ id_max, END)%proto false;
      rle_prot 1 2 3 P (λ id_max, END)%proto false;
      rle_prot 2 3 0 P (λ id_max, END)%proto false].

  Lemma rle_ref_prog_prot_pool_consistent P :
    ⊢ iProto_consistent (rle_ref_prog_prot_pool P).
  Proof.
    rewrite /rle_ref_prog_prot_pool /rle_preprot.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
    case_bool_decide; try lia.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
    case_bool_decide; try lia.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
    case_bool_decide; try lia.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
  Qed.

  Lemma rle_ref_prog_spec :
    {{{ True }}} rle_ref_prog #() {{{ RET #(); True }}}.
  Proof.
    iIntros (Φ) "_ HΦ". wp_lam.
    wp_alloc l as "Hl".
    wp_new_chan (rle_ref_prog_prot_pool (l ↦ #42))
      with rle_ref_prog_prot_pool_consistent
      as (c0 c1 c2 c3) "Hc0" "Hc1" "Hc2" "Hc3".
    wp_smart_apply (wp_fork with "[Hc1]").
    { iIntros "!>". wp_smart_apply (process_spec with "Hc1").
      iIntros (i') "[_ Hl]". wp_pures. case_bool_decide.
      - case_bool_decide; [|simplify_eq; lia]. by wp_free.
      - case_bool_decide; [simplify_eq; lia|]. by wp_pures. }
    wp_smart_apply (wp_fork with "[Hc2]").
    { iIntros "!>". wp_smart_apply (process_spec with "Hc2").
      iIntros (i') "[_ Hl]". wp_pures. case_bool_decide.
      - case_bool_decide; [|simplify_eq; lia]. by wp_free.
      - case_bool_decide; [simplify_eq; lia|]. by wp_pures. }
    wp_smart_apply (wp_fork with "[Hc3]").
    { iIntros "!>". wp_smart_apply (process_spec with "Hc3").
      iIntros (i') "[_ Hl]". wp_pures. case_bool_decide.
      - case_bool_decide; [|simplify_eq; lia]. by wp_free.
      - case_bool_decide; [simplify_eq; lia|]. by wp_pures. }
    wp_smart_apply (init_spec with "[$Hc0 $Hl]").
    iIntros (i') "[_ Hl]". wp_pures. case_bool_decide.
    - case_bool_decide; [|simplify_eq; lia]. wp_free. by iApply "HΦ".
    - case_bool_decide; [simplify_eq; lia|]. wp_pures. by iApply "HΦ". 
  Qed.

End rle_ref_prog_proof.

Lemma rle_ref_prog_adequate :
  adequate NotStuck (rle_ref_prog #()) ({|heap := ∅; used_proph_id := ∅|})
           (λ _ _, True).
Proof.
  apply (heap_adequacy #[heapΣ; chanΣ]).
  iIntros (Σ) "H". by iApply rle_ref_prog_spec.
Qed.

Definition relay : val :=
  λ: "c" "c'" "idl" "id" "idr" "id_max",
    if: "id" = "id_max" then
      send "c'" #0 "id_max";; send "c" "idl" #();; recv "c" "idr"
    else
      recv "c" "idr";; send "c'" #0 "id_max";; send "c" "idl" #().

Definition rle_del_prog : val :=
  λ: <>,
     let: "cs'" := new_chan #2 in
     let: "c0'" := get_chan "cs'" #0 in
     let: "c1'" := get_chan "cs'" #1 in
     Fork (let: "id_max" := recv "c0'" #1 in
           (rec: "f" <> :=
              let: "id'" := recv "c0'" #1 in
              assert: ("id'" = "id_max");; "f" #()) #());;
     let: "cs" := new_chan #4 in
     let: "c0" := get_chan "cs" #0 in
     let: "c1" := get_chan "cs" #1 in
     let: "c2" := get_chan "cs" #2 in
     let: "c3" := get_chan "cs" #3 in
     Fork (let: "id_max" := process "c1" #0 #1 #2 #false in
           relay "c1" "c1'" #0 #1 #2 "id_max");;
     Fork (let: "id_max" := process "c2" #1 #2 #3 #false in
           relay "c2" "c1'" #1 #2 #3 "id_max");;
     Fork (let: "id_max" := process "c3" #2 #3 #0 #false in
           relay "c3" "c1'" #2 #3 #0 "id_max");;
     let: "id_max" := init "c0" #3 #0 #1 in
     relay "c0" "c1'" #3 #0 #1 "id_max".

Section rle_del_prog_proof.
  Context `{!heapGS Σ, chanG Σ}.

  Definition relay_del_prot (P:iProp Σ) (il i ir i_max : nat) : iProto Σ :=
    if bool_decide (i = i_max) then
      (<(Send,il)> MSG #() {{ P }} ; <(Recv,ir)> MSG #() {{ P }}; END)%proto
    else
      (<(Recv,ir)> MSG #() {{ P }} ; <(Send,il)> MSG #() {{ P }}; END)%proto.

  Definition relay_send_aux (id : nat) (rec : iProto Σ) : iProto Σ :=
    (<(Send,0)> MSG #id ; rec)%proto.
  Instance relay_send_aux_contractive i : Contractive (relay_send_aux i).
  Proof. solve_proto_contractive. Qed.
  Definition relay_send_prot i := fixpoint (relay_send_aux i).
  Instance relay_send_prot_unfold i :
    ProtoUnfold (relay_send_prot i) (relay_send_aux i (relay_send_prot i)).
  Proof. apply proto_unfold_eq, (fixpoint_unfold (relay_send_aux i)). Qed.
  Lemma relay_send_prot_unfold' i :
    (relay_send_prot i) ≡
    (relay_send_aux i (relay_send_prot i)).
  Proof. apply (fixpoint_unfold (relay_send_aux i)). Qed.

  Definition relay_send_preprot : iProto Σ :=
    (<(Send,0) @ (i_max:nat)> MSG #i_max ; relay_send_prot i_max)%proto.

  Definition relay_recv_aux (id : nat) (rec : iProto Σ) : iProto Σ :=
    (<(Recv,1)> MSG #id ; rec)%proto.
  Instance relay_recv_aux_contractive i : Contractive (relay_recv_aux i).
  Proof. solve_proto_contractive. Qed.
  Definition relay_recv_prot i := fixpoint (relay_recv_aux i).
  Instance relay_recv_prot_unfold i :
    ProtoUnfold (relay_recv_prot i) (relay_recv_aux i (relay_recv_prot i)).
  Proof. apply proto_unfold_eq, (fixpoint_unfold (relay_recv_aux i)). Qed.
  Lemma relay_recv_prot_unfold' i :
    (relay_recv_prot i) ≡
    (relay_recv_aux i (relay_recv_prot i)).
  Proof. apply (fixpoint_unfold (relay_recv_aux i)). Qed.
  Definition relay_recv_preprot : iProto Σ :=
    (<(Recv,1) @ (i_max:nat)> MSG #i_max ; relay_recv_prot i_max)%proto.

  Definition rle_del_prog_prot_pool P Φ : list (iProto Σ) :=
     [rle_preprot 3 0 1 P (λ id_max, relay_del_prot (Φ id_max) 3 0 1 id_max);
      rle_prot 0 1 2 P (λ id_max, relay_del_prot (Φ id_max) 0 1 2 id_max) false;
      rle_prot 1 2 3 P (λ id_max, relay_del_prot (Φ id_max) 1 2 3 id_max) false;
      rle_prot 2 3 0 P (λ id_max, relay_del_prot (Φ id_max) 2 3 0 id_max) false].

  Lemma rle_del_prog_prot_pool_consistent P Φ :
    ⊢ iProto_consistent (rle_del_prog_prot_pool P Φ).
  Proof.
    rewrite /rle_del_prog_prot_pool /rle_preprot.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
    case_bool_decide; try lia.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
    case_bool_decide; try lia.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
    case_bool_decide; try lia.
    rewrite !rle_prot_unfold'.
    iProto_consistent_take_steps.
  Qed.

  Definition rle_del_prog_prot_pool' : list (iProto Σ) :=
     [relay_recv_preprot; relay_send_preprot].

  Lemma rle_del_prog_prot_pool_consistent' :
    ⊢ iProto_consistent (rle_del_prog_prot_pool').
  Proof.
    rewrite /rle_del_prog_prot_pool'.
    iProto_consistent_take_steps.
    iLöb as "IH".
    iEval (rewrite relay_recv_prot_unfold').
    iEval (rewrite relay_send_prot_unfold').
    iProto_consistent_take_steps.
    done.
  Qed.

  Lemma relay_spec c c' il i ir i_max :
    {{{ c ↣ relay_del_prot (c' ↣ relay_send_prot i_max) il i ir i_max ∗
        if (bool_decide (i = i_max)) then c' ↣ relay_send_preprot else True%I }}}
      relay c c' #il #i #ir #i_max
    {{{ RET #(); True }}}.
  Proof.
    iIntros (Φ) "[Hc Hc'] HΦ". wp_lam.
    rewrite /relay_del_prot.
    wp_pures. case_bool_decide.
    - simplify_eq. wp_pures.
      case_bool_decide; [|simplify_eq;lia].
      wp_send with "[//]". wp_send with "[Hc'//]". wp_recv as "Hc'".
      by iApply "HΦ".
    - case_bool_decide; [simplify_eq;lia|].
      iClear "Hc'". wp_recv as "Hc'".
      wp_send with "[//]". wp_send with "[Hc'//]". by iApply "HΦ".
  Qed.

  Lemma rle_del_prog_spec :
    {{{ True }}} rle_del_prog #() {{{ RET #(); True }}}.
  Proof.
    iIntros (Φ) "_ HΦ". wp_lam.
    wp_new_chan rle_del_prog_prot_pool' with rle_del_prog_prot_pool_consistent'
      as (c0' c1') "Hc0'" "Hc1'".
    wp_smart_apply (wp_fork with "[Hc0']").
    { iIntros "!>". wp_recv (i_max) as "_". wp_pures.
      iLöb as "IH". wp_recv as "_". wp_smart_apply wp_assert.
      wp_pures. iModIntro. iSplit; [iPureIntro; f_equiv; by case_bool_decide|].
      iIntros "!>". wp_pures. by iApply "IH". }
    wp_new_chan (rle_del_prog_prot_pool (c1' ↣ relay_send_preprot)
                           (λ i_max, c1' ↣ relay_send_prot i_max))
      with rle_del_prog_prot_pool_consistent
      as (c0 c1 c2 c3) "Hc0" "Hc1" "Hc2" "Hc3".
    wp_smart_apply (wp_fork with "[Hc1]").
    { iIntros "!>". wp_smart_apply (process_spec with "Hc1").
      iIntros (i') "Hc1". by wp_smart_apply (relay_spec with "[$Hc1]"). }
    wp_smart_apply (wp_fork with "[Hc2]").
    { iIntros "!>". wp_smart_apply (process_spec with "Hc2").
      iIntros (i') "Hc2". by wp_smart_apply (relay_spec with "[$Hc2]"). }
    wp_smart_apply (wp_fork with "[Hc3]").
    { iIntros "!>". wp_smart_apply (process_spec with "Hc3").
      iIntros (i') "Hc3". by wp_smart_apply (relay_spec with "[$Hc3]"). }
    wp_smart_apply (init_spec with "[$Hc0 $Hc1']").
    iIntros (i') "Hc0". by wp_smart_apply (relay_spec with "[$Hc0]").
  Qed.

End rle_del_prog_proof.

Lemma rle_del_prog_adequate :
  adequate NotStuck (rle_del_prog #()) ({|heap := ∅; used_proph_id := ∅|})
           (λ _ _, True).
Proof.
  apply (heap_adequacy #[heapΣ; chanΣ]).
  iIntros (Σ) "H". by iApply rle_del_prog_spec.
Qed.
