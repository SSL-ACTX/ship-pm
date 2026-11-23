open Nano

type 'a btree =
  | Empty
  | Node of 'a * 'a btree * 'a btree

let rec insert x = function
  | Empty -> Node (x, Empty, Empty)
  | Node (v, left, right) ->
      if x < v then
        Node (v, insert x left, right)
      else if x > v then
        Node (v, left, insert x right)
      else
        Node (v, left, right)

let rec sum_tree = function
  | Empty -> 0
  | Node (v, left, right) -> v + sum_tree left + sum_tree right

let test () =
  let t = Empty in
  let t = insert 50 t in
  let t = insert 25 t in
  let t = insert 75 t in
  let t = insert 10 t in
  sum_tree t
