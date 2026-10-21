module PulseVerification
#lang-pulse

open Pulse.Lib.Pervasives
open PulseCore.FractionalPermission
open Pulse.Lib.Fractional
open FStar.Tactics.V2

let solve_perm_goal () : Tac unit =
  smt ()

let lemma_quarter_perm (p: perm) : Lemma (p /. 4.0R +. p /. 4.0R == p /. 2.0R) by (solve_perm_goal ()) = ()

fn share_ref (#a: Type0) (r: ref a) (#v: a)
  requires pts_to r #1.0R v
  ensures pts_to r #0.5R v ** pts_to r #0.5R v
{
  share r;
}

fn gather_ref (#a: Type0) (r: ref a) (#v1 #v2: a)
  requires pts_to r #0.5R v1 ** pts_to r #0.5R v2
  ensures pts_to r #1.0R v1 ** pure (v1 == v2)
{
  gather r;
}

fn read_shared (#a: Type0) (r: ref a) (#p: perm) (#v: a)
  requires pts_to r #p v
  returns x: a
  ensures pts_to r #p v ** pure (x == v)
{
  !r
}

fn split_quarter (#a: Type0) (r: ref a) (#v: a)
  requires pts_to r #0.5R v
  ensures pts_to r #0.25R v ** pts_to r #0.25R v
{
  share r;
}

fn swap_refs (r1 r2: ref int)
  requires pts_to r1 'v1 ** pts_to r2 'v2
  ensures pts_to r1 'v2 ** pts_to r2 'v1
{
  let x = !r1;
  let y = !r2;
  r1 := y;
  r2 := x;
}

fn rotate_three (r1 r2 r3: ref int)
  requires pts_to r1 'v1 ** pts_to r2 'v2 ** pts_to r3 'v3
  ensures pts_to r1 'v2 ** pts_to r2 'v3 ** pts_to r3 'v1
{
  let x = !r1;
  let y = !r2;
  let z = !r3;
  r1 := y;
  r2 := z;
  r3 := x;
}

fn add_to (r: ref int) (delta: int)
  requires pts_to r 'v
  ensures pts_to r ('v + delta)
{
  let cur = !r;
  r := cur + delta;
}

fn transfer (from_bal to_bal: ref int) (amount: int)
  requires pts_to from_bal 'vf ** pts_to to_bal 'vt ** pure (amount <= 'vf)
  ensures pts_to from_bal ('vf - amount) ** pts_to to_bal ('vt + amount)
{
  let bf = !from_bal;
  let bt = !to_bal;
  from_bal := bf - amount;
  to_bal := bt + amount;
}
