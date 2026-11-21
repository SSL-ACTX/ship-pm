use vstd::prelude::*;

verus! {

spec fn min(x: int, y: int) -> int {
    if x <= y { x } else { y }
}

fn main() {
    assert(min(10, 20) == 10);
    assert(min(-10, -20) == -20);
    assert(forall|x: int, y: int| min(x, y) <= x && min(x, y) <= y);
    assert(forall|x: int, y: int| min(x, y) == x || min(x, y) == y);
    assert(forall|x: int, y: int| min(x, y) == min(y, x));
}

} // verus!
