use vstd::prelude::*;

verus! {

fn checked_add(a: u64, b: u64) -> (sum: u64)
    requires
        (a as int) + (b as int) <= u64::MAX as int,
    ensures
        sum as int == (a as int) + (b as int),
{
    a + b
}

fn main() {
    let result = checked_add(20, 22);
    assert(result == 42);
}

} // verus!
