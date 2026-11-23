open Nano
open Nano_effects

type _ t += Ask : int t

let computation () =
  let v = perform Ask in
  v + 10

let run () =
  let handler : int Deep.effect_handler =
    { effc = (fun (type a) (eff : a t) ->
        match eff with
        | Ask -> Some (fun (k : (a, int) Deep.continuation) ->
            Deep.continue k 42)
        | _ -> None)
    }
  in
  Deep.try_with (fun () -> computation ()) () handler
