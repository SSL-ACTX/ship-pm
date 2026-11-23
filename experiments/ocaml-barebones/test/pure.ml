type 'a tree = Leaf | Node of 'a * 'a tree * 'a tree
let pair a b = (a, b)
let id x = x
let choose cond a b = match cond with true -> a | false -> b
