//! A bounded binary-search implementation for Hax extraction.

/// Return the first index whose value is greater than or equal to `key`.
///
/// This keeps `lo..hi` as the candidate interval. Every access uses `mid`
/// strictly inside that interval, so the extraction gives F* the proof
/// obligations needed to establish panic-free indexing.
pub fn lower_bound(values: &[u32], key: u32) -> usize {
    let mut lo = 0;
    let mut hi = values.len();

    while lo < hi {
        let mid = lo + (hi - lo) / 2;
        if values[mid] < key {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }

    lo
}

/// Find `key` in a sorted slice, returning its insertion point when absent.
pub fn search_or_insert(values: &[u32], key: u32) -> Result<usize, usize> {
    let index = lower_bound(values, key);
    if index < values.len() && values[index] == key {
        Ok(index)
    } else {
        Err(index)
    }
}

#[cfg(test)]
mod tests {
    use super::{lower_bound, search_or_insert};

    #[test]
    fn preserves_the_first_duplicate_position() {
        let values = [2, 4, 4, 7, 11, 18, 29];
        assert_eq!(lower_bound(&values, 4), 1);
        assert_eq!(search_or_insert(&values, 18), Ok(5));
        assert_eq!(search_or_insert(&values, 5), Err(3));
    }
}
