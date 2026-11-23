open Nano

let rec sum_list acc = function
  | [] -> acc
  | x :: xs -> sum_list (acc + x) xs

let test () =
  let r = ref 10 in
  r := !r * 2;
  let xs = 1 :: 2 :: 3 :: 4 :: [] in
  sum_list !r xs
