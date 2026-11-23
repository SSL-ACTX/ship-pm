open Nano

type 'a eff = ..
type 'a eff += Ask : int eff

external perform : 'a eff -> 'a = "%perform"

let test_perform () =
  perform Ask
