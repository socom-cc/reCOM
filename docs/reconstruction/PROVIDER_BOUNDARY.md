# Provider boundary and ABI closure

A provider is code or data whose implementation originates outside authored
game translation units: compiler runtime, C/C++ library, PlayStation 2 SDK, or
middleware. Classification is an ownership result, not a waiver of evidence.

Before a provider edge can be treated as closed, record:

- exact imported/static identity and symbol aliases;
- caller-visible R5900 contract, including return, parameters, structure
  return, register class, stack layout, and clobbers;
- version/library provenance;
- relocation and ordering contribution;
- global data, initialization, vtable/RTTI, or allocation effects;
- whether exact library bytes are available for final linking.

If the library is unavailable, keep the dependency as a blocker. Do not
implement guessed internals, substitute a modern library, or create an ABI shim
and call it equivalent. A source-faithful declaration may be useful while its
physical provider contribution remains unresolved.

Provider conclusions belong in tracker evidence and durable notes. The
`socom-provider-boundary` skill and `socom-provider-data-classifier` role
separate classification from source implementation and final acceptance.
