# Bounded validation

[Русский](../ru/reference/validation.md)

Use the validator to compare a review document with trusted caller expectations.
The caller MUST provide those expectations as a separate protected input.
The CLI opens only the two named inputs and writes its result to stdout or
stderr. The `-B` invocation prevents Python bytecode writes.

```sh
python -B -m agent_review_suite validate --kind report --input report.json \
  --root /absolute/local/staging --expectations expected.json
```

The root MUST be an absolute local directory path with physical components.
The input and expectations paths are relative to the root. Empty, dot,
dot-dot, backslash, colon, and NUL components are refused. Use `--input -`
to read a caller-owned pipe or regular file from stdin. The expectations file
still comes from the controlled root. Both inputs MUST have distinct file
identities where they come from files. A pinned-root helper refuses a repeated
file identity. ARS does not open paths found in the
review document.

The caller MUST control the local staging directory and prevent untrusted
changes to its directory, mount, and device namespace. Use a real local
filesystem. The caller MUST set an external process timeout when it needs
a hard wall-clock bound for a stalled OS operation. ARS checks one
two-second monotonic read deadline across both inputs, including pipe EOF.
The caller MUST give the validator exclusive use of the pipe descriptor
while it reads. ARS restores pipe blocking mode on success and failure.

File and stdin intake require the supported primitives on macOS or Linux.
The validator refuses symbolic or hard links, devices, named pipes reached
by path, and observable identity changes. It refuses file and stdin CLI
intake on Windows. On Windows callers can supply bytes to the portable
[contract API](request-report.md).

| Exit | Meaning |
| --- | --- |
| 0 | Both documents are valid and their expected bindings match |
| 2 | An input or argument is malformed, refused, too large, timed out, or unsupported |
| 3 | Both documents are valid, but one or more expected bindings differ |

For example, a well-formed report with a foreign coverage ID returns 3.
If it also contains a duplicate coverage row, it returns 2. The caller
reads execution state separately from successful validation.
