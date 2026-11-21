use vstd::prelude::*;

verus! {

spec fn sorted(values: Seq<u64>) -> bool {
    forall|i: int, j: int|
        0 <= i <= j < values.len() ==> values[i] <= values[j]
}

proof fn sorted_le(values: Seq<u64>, i: int, j: int)
    requires
        sorted(values),
        0 <= i <= j < values.len(),
    ensures
        values[i] <= values[j],
{
    reveal(sorted);
}

/// Return the first index whose value is at least `key`.
/// If no such index exists, return `values.len()`.
fn lower_bound(values: &Vec<u64>, key: u64) -> (index: usize)
    requires
        sorted(values@),
    ensures
        index <= values.len(),
        forall|i: int| 0 <= i < index as int ==> values@[i] < key,
        forall|i: int| index as int <= i < values@.len() ==> key <= values@[i],
{
    let mut lo: usize = 0;
    let mut hi: usize = values.len();
    let ghost model = values@;
    assert(sorted(model));

    while lo < hi
        invariant
            0 <= lo <= hi <= values.len(),
            values@ == model,
            sorted(model),
            forall|i: int| 0 <= i < lo as int ==> values@[i] < key,
            forall|i: int| hi as int <= i < values@.len() ==> key <= values@[i],
        decreases hi - lo,
    {
        let mid = lo + (hi - lo) / 2;

        if values[mid] < key {
            assert forall|i: int| 0 <= i <= mid as int implies
                values@[i] <= values@[mid as int] by {
                sorted_le(model, i, mid as int);
            }
            assert(values@[mid as int] < key);
            lo = mid + 1;
        } else {
            assert(key <= values@[mid as int]);
            assert forall|i: int| mid as int <= i < values@.len() implies
                key <= values@[i] by {
                if i > mid as int {
                    sorted_le(model, mid as int, i);
                } else {
                    assert(i == mid as int);
                }
            }
            hi = mid;
        }
    }

    lo
}

/// Return an index containing `key`, or prove that it is absent.
fn binary_search(values: &Vec<u64>, key: u64) -> (result: Option<usize>)
    requires
        sorted(values@),
    ensures
        match result {
            Some(index) => index < values.len() && values@[index as int] == key,
            None => forall|i: int| 0 <= i < values@.len() ==> values@[i] != key,
        },
{
    let index = lower_bound(values, key);

    if index < values.len() && values[index] == key {
        Some(index)
    } else {
        None
    }
}

fn main() {
    let values = vec![2u64, 4, 4, 7, 11, 18, 29];

    let first_four = lower_bound(&values, 4);
    assert(first_four == 1);

    let insertion_point = lower_bound(&values, 5);
    assert(insertion_point == 3);

    let found = binary_search(&values, 18);
    assert(found == Some(5));

    let missing = binary_search(&values, 3);
    assert(missing == None);
}

} // verus!
