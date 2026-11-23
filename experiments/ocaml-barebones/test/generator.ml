open Nano
open Nano_effects

type _ t += Yield : int -> unit t

let rec range_generator low high =
  if low <= high then begin
    perform (Yield low);
    range_generator (low + 1) high
  end

let test () =
  let total = ref 0 in
  let handler : unit Deep.effect_handler =
    { effc = (fun (type a) (eff : a t) ->
        match eff with
        | Yield n -> Some (fun (k : (a, unit) Deep.continuation) ->
            total := !total + n;
            Deep.continue k ())
        | _ -> None)
    }
  in
  Deep.try_with (fun () -> range_generator 1 10) () handler;
  !total
