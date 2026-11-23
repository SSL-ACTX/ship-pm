open Nano

type 'a t = 'a eff = ..
external perform : 'a t -> 'a = "%perform"

type ('a, 'b) stack [@@immediate]
type last_fiber [@@immediate]

external resume : ('a, 'b) stack -> ('c -> 'a) -> 'c -> last_fiber -> 'b = "%resume"
external runstack : ('a, 'b) stack -> ('c -> 'a) -> 'c -> 'b = "%runstack"

module Deep = struct
  type nonrec ('a, 'b) continuation = ('a, 'b) continuation

  external take_cont_noexc : ('a, 'b) continuation -> ('a, 'b) stack =
    "caml_continuation_use_noexc" [@@noalloc]
  external alloc_stack :
    ('a -> 'b) ->
    (exn -> 'b) ->
    ('c t -> ('c, 'b) continuation -> last_fiber -> 'b) ->
    ('a, 'b) stack = "caml_alloc_stack"
  external cont_last_fiber : ('a, 'b) continuation -> last_fiber = "%field1"

  let continue k v =
    resume (take_cont_noexc k) (fun x -> x) v (cont_last_fiber k)

  type ('a, 'b) handler =
    { retc : 'a -> 'b;
      exnc : exn -> 'b;
      effc : 'c. 'c t -> (('c, 'b) continuation -> 'b) option }

  type 'a effect_handler =
    { effc : 'b. 'b t -> (('b, 'a) continuation -> 'a) option }

  external reperform :
    'a t -> ('a, 'b) continuation -> last_fiber -> 'b = "%reperform"

  let match_with comp arg (handler : ('a, 'b) handler) =
    let effc eff k last_fiber =
      match handler.effc eff with
      | Some f -> f k
      | None -> reperform eff k last_fiber
    in
    let s = alloc_stack handler.retc handler.exnc effc in
    runstack s comp arg

  let try_with comp arg (handler : 'a effect_handler) =
    let effc' eff k last_fiber =
      match handler.effc eff with
      | Some f -> f k
      | None -> reperform eff k last_fiber
    in
    let s = alloc_stack (fun x -> x) (fun e -> raise e) effc' in
    runstack s comp arg
end
