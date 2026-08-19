# Monotonic Stacks

The structure that turns a class of nested-loop scans into a single pass.

A monotonic stack converts some nested scans into one pass. Typical cases ask
for the next greater or smaller element, span boundaries, or the largest
region constrained by local minima. Every index is pushed and popped at most
once, so the work is linear and the auxiliary storage is linear in the worst
case.

```go
package monotonic

// NextGreater returns the index of the first strictly greater value to the
// right, or -1. Equal values are deliberately not considered greater.
func NextGreater(values []int64) []int {
	result := make([]int, len(values))
	for i := range result {
		result[i] = -1
	}
	stack := make([]int, 0, len(values))
	for i, value := range values {
		for len(stack) != 0 && value > values[stack[len(stack)-1]] {
			j := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			result[j] = i
		}
		stack = append(stack, i)
	}
	return result
}
```

Specify strict versus non-strict comparison before writing the loop; changing
`>` to `>=` changes duplicate handling. Differential-test the optimized
algorithm against a plainly correct quadratic implementation on small random
inputs. This catches boundary errors more effectively than selected examples.
