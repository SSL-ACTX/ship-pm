external (+) : int -> int -> int = "%addint"
external ( * ) : int -> int -> int = "%mulint"

type point = { x : int; y : int }

let make_point x y = { x; y }
let sum_point p = p.x + p.y
let make_closure factor = fun x -> x * factor
