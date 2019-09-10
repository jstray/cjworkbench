Data types for Inter-process and inter-language communications.

See [Thrift documentation](https://thrift.apache.org/tutorial/) for details.

Broad strokes
-------------

Workbench kernels use Linux-kernel processes for sandboxing. We use a
lightweight protocol to pass messages between processes. Most data is passed
using Thrift; dataframes are passed using [Arrow](https://arrow.apache.org)
files with implicit filenames on the filesystem.

Editing
-------

Files in this directory are generated by Thrift. Do not edit them directly.

Instead, edit `cjwkernel/thrift.thrift`. Then run this command to regenerate
the files in this directory:

```
bin/dev thrift --strict --gen py:slots --out . cjwkernel/thrift.thrift
```

Q&A
---

*Why Thrift?*

* We want a cross-language and secure transfer format -- which rules out
  Python pickling.
* We want a smooth upgrade path for when we change the protocol -- which rules
  out JSON.
* We use [Arrow](https://arrow.apache.org) to transfer dataframes; some
  Arrow libraries (including pyarrow) come with Parquet readers; and Parquet
  metadata is Thrift-encoded. So Thrift is likely to be already installed --
  which nudges Thrift ahead of Protobuf.

*How to pass params?*

Module parameter values are passed as JSON-encoded strings. It does not make
sense to encode them as Thrift: we already have JSON validation for params.

*How to convert to/from Python objects?*

Those conversions are in `cjwkernel.pandas.types`.

Notice a wart in the Pandas kernel: after we fork to run the user's code, the
child process cannot be trusted (since the user's code could do _anything_). So
the child serializes its Python objects into Thrift format and stores Thrift
data in a shared memory map; the parent reads and validates the child's message.
(There's an Arrow message in there, too.)