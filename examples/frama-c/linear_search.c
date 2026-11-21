/*@ requires \valid_read(arr + (0 .. n - 1));
    requires n >= 0;
    assigns \nothing;

    behavior found:
      assumes \exists integer i; 0 <= i < n && arr[i] == target;
      ensures 0 <= \result < n;
      ensures arr[\result] == target;

    behavior not_found:
      assumes \forall integer i; 0 <= i < n ==> arr[i] != target;
      ensures \result == -1;

    complete behaviors;
    disjoint behaviors;
*/
int linear_search(const int *arr, int n, int target) {
    /*@ loop invariant 0 <= i <= n;
        loop invariant \forall integer j; 0 <= j < i ==> arr[j] != target;
        loop assigns i;
        loop variant n - i;
    */
    for (int i = 0; i < n; i++) {
        if (arr[i] == target) {
            return i;
        }
    }
    return -1;
}

int main(void) {
    int arr[5] = {10, 20, 30, 40, 50};
    int res = linear_search(arr, 5, 30);
    return res;
}
