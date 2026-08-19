# Files and Memory Mapping

Pick the file API from the access pattern and the size bound you can defend.
Memory mapping trades explicit I/O for page faults and a portability and safety
contract, so it needs a measurement and an owner.

## Choose a file-reading API

- `os.ReadFile` is clear for a file whose maximum size is trusted and small
  enough to hold in memory. Validate size at a trust boundary rather than
  assuming a configuration file is small.
- `bufio.Scanner` streams bounded tokens.
- `bufio.Reader` or a decoder over `io.Reader` streams structured data.
- `File.ReadAt` supports independent positional reads and is safe for
  concurrent calls. Avoid shared `Seek` plus `Read` across goroutines.
- `io.SectionReader` gives a bounded view over a `ReaderAt` without changing a
  shared file offset.

Whole-file reads and `io.ReadAll` intentionally allocate for the entire input.
Put an explicit byte limit before them for network input or untrusted files.
For sequential large files, buffered streaming is usually the simplest strong
baseline.

## Memory mapping

Mapping replaces explicit read syscalls with page faults and memory accesses.
It is only zero-copy when the algorithm works directly on the mapped bytes. If
those bytes are copied into another buffer, mapping avoided read calls but did
not avoid the copy.

```go
func withMappedFile(path string, use func([]byte) error) (retErr error) {
	// turbo: mmap removes measured read calls for stable large files at the
	// cost of platform-specific fault and lifetime semantics.
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer func() { retErr = errors.Join(retErr, f.Close()) }()

	info, err := f.Stat()
	if err != nil {
		return err
	}
	if info.Size() == 0 {
		return use(nil)
	}
	if info.Size() > int64(maxInt) {
		return fmt.Errorf("file is too large to map: %d", info.Size())
	}

	data, err := unix.Mmap(
		int(f.Fd()),
		0,
		int(info.Size()),
		unix.PROT_READ,
		unix.MAP_PRIVATE,
	)
	if err != nil {
		return err
	}
	defer func() { retErr = errors.Join(retErr, unix.Munmap(data)) }()
	return use(data)
}
```

`maxInt` is a local architecture-sized bound, for example `int(^uint(0) >> 1)`.
Place mapping code in platform-specific files. The callback must not retain the
slice after unmap.

Mapping has failure modes ordinary reads avoid: access can block on a page
fault, and truncating or mutating the mapped file can fault the process or
produce inconsistent observations. Atomic replacement normally leaves an
existing mapping attached to the old file object. Mapping lifetime is outside
normal Go heap accounting. Coordinate writers, bound mapping count and size,
and unmap deterministically. Random access and in-place scans of large, stable
files are plausible use cases; sequential reads need a benchmark before
accepting the added lifecycle and portability cost.

The final check is end-to-end. Fewer syscalls can still lose if batching raises
latency, buffers inflate memory, or a hidden copy remains. Keep the simplest
implementation that meets the measured service objective.

## Version compatibility

The generic batcher requires Go 1.18; `errors.Join` and `context.Cause` require
Go 1.20; and the `clear` built-in requires Go 1.21. On older supported modules,
use a typed batcher, return `ctx.Err()`, preserve multiple cleanup errors
explicitly, and zero pointer-bearing elements with a loop before retaining the
backing array. The mmap example uses
`golang.org/x/sys/unix`; select a dependency version compatible with the
module, keep it platform-tagged, and do not add it merely to avoid ordinary
file reads.
