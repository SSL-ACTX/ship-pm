let add a b = a + b
let pair a b = (a, b)
type 'a tree = Leaf | Node of 'a * 'a tree * 'a tree
let rec depth = function
  | Leaf -> 0
  | Node (_, l, r) -> 1 + (let dl = depth l in let dr = depth r in if dl > dr then dl else dr)
