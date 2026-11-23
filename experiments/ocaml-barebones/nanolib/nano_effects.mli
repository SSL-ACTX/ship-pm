open Nano

type 'a t = 'a eff = ..
external perform : 'a t -> 'a = "%perform"

type ('a, 'b) stack [@@immediate]
type last_fiber [@@immediate]

external resume : ('a, 'b) stack -> ('c -> 'a) -> 'c -> last_fiber -> 'b = "%resume"
external runstack : ('a, 'b) stack -> ('c -> 'a) -> 'c -> 'b = "%runstack"

module Deep : sig
  type nonrec ('a, 'b) continuation = ('a, 'b) continuation

  type ('a, 'b) handler =
    { retc : 'a -> 'b;
      exnc : exn -> 'b;
      effc : 'c. 'c t -> (('c, 'b) continuation -> 'b) option }

  type 'a effect_handler =
    { effc : 'b. 'b t -> (('b, 'a) continuation -> 'a) option }

  val continue : ('a, 'b) continuation -> 'a -> 'b
  val match_with : ('c -> 'a) -> 'c -> ('a, 'b) handler -> 'b
  val try_with : ('b -> 'a) -> 'b -> 'a effect_handler -> 'a
end
