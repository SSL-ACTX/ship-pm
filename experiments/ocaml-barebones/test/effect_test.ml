open Nano

type _ Effect.t += Ask : int Effect.t

let run_effect () =
  try
    let v = Effect.perform Ask in
    v + 5
  with Effect.Eff (Ask, k) ->
    Effect.continue k 37
