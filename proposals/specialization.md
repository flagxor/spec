# Specialization of WebAssembly Modules

## Motivation

Implementations of WebAssembly can use a variety of approaches to code
generation. However, largely by design, the format has a small number of
optimum implementation approaches on each architecture + host OS.
On 32-bit systems, WebAssembly's approach to linear memory typically requires
explicit bounds checks. However, on 64-bit systems with hardware
fault interception (signals), a "trick" can be used to save the cost of
bounds checks. Unfortunately, this technique relies on a potentially scarce
resource: address space. The current WebAssembly JS API prevents good use of
this scarce resource (particularly for dynamic linking and loading).
This proposal attempts to address that.

The 64-bit OOB trick involves laying out a region of 4-GB reserved memory
(or larger depending on the addressing mode used by generated code).
Code can then be structured to assume that accesses to regions outside
the current size of a `WebAssembly.Memory` will fault. This fault is then
intercepted and an exception triggered. As most normal applications avoid
accessing out of bounds memory, this trades making the common case fast for
slowing the exceptional case.

Unfortunately, the availability of 64-bit addresses at a point where most
of the address space is typically unused has prompted the use of
the empty space to achieve *Address Space Layout Randomization*.
This technique attempts to introduce a partial stochastic security barrier
by hiding the relative layout of memory regions. It's utility is directly tied
to how much of the address space is under attacker control.
Current CPUs can only use 48-bits of address in practice
(47-bit on most OSes), which means that
4GB+ allocations of address space, constrain large chunks of this spaces.
If several of these 4GB+ area are used, they can easily fill most of
the address space with immovable dead zones, undermining address randomization.

Both browsers and operating systems do / may want to impose limits on
the number of such large allocations allowed.
How many to allow is subjective. Reasonable (and existing) implementations
might have limits as small as 1-2 large address space reservations.
Implementations that support a small number of these "fast memories"
most likely will need to support a fallback mode in which "slow memories"
are allocated. The performance difference is on the order of 20%.

A non-obvious ramification is that because `new WebAssembly.Module`,
`WebAssembly.compile`, and `WebAssembly.compileStreaming` do not know
whether they will be provided with a "fast" or "slow" memory,
they are forced to either double compilation work (and code memory),
or to conservatively choose to generate "slow" code which can be used
regardless of the memory they are instantiated with.

Another, non-obvious issue with large address spaces being tied to a memory
is that this mixes memory and non-memory resources with a garbage collector.
Address space can be exhausted before memory and vice-versa.
Recovery of address space might require a full collect.

## Proposal

### Approach

To correct this limitation in the current design, we propose allowing
`WebAssembly.Module` objects to be "specialized" for particular memories.
Optional arguments to compilation methods and an explicit `specialize`
method allow applications to request the type of compilation they want
abstractly.

Note, this is both more and less general than the underlying
implementation restrictions. In principle, code generated for a "fast" memory
could work with any such memory. However, specializing
on a particular memory also allows for the possibility of specializing
on the address of that memory (a potential 32-bit performance win).
Applications wishing to re-use a single module on several "fast" memories
can do so abstractly by specializing for each of them (which should be
a no-op if the underlying implementation can reuse the code for multiple
fast memories).

To mitigate the problem of address space exhaustion, we propose the option
to explicitly release `WebAssembly.Memory` objects.

### API Changes

Compilation methods are expanded to add an optional `object importObject`
parameter. When provided, compilation will be specialized to assume that
any provided objects will also be passed to instantiation methods with
the resulting module.
Implementations will otherwise throw a `TypeError` if instantiated with
other objects.

<pre>
[LegacyNamespace=WebAssembly, Constructor(
    BufferSource bytes<b>, optional object importObject</b>),
Exposed=(Window,Worker,Worklet)]
interface Module {
  static sequence&lt;ModuleExportDescriptor&gt; exports(Module module);
  static sequence&lt;ModuleImportDescriptor&gt; imports(Module module);
  static sequence&lt;ArrayBuffer&gt; customSections(Module module, DOMString sectionName);
};
</pre>

<pre>
partial namespace WebAssembly {
  Promise&lt;Module&gt; compileStreaming(
      Promise&lt;Response&gt; source<b>, optional object importObject</b>);
  Promise&lt;WebAssemblyInstantiatedSource&gt; instantiateStreaming(
      Promise&lt;Response&gt; source, optional InstanceImportsMap importObject);
};
</pre>

<pre>
namespace WebAssembly {
    boolean validate(BufferSource bytes);
    Promise&lt;Module&gt; compile(
        BufferSource bytes<b>, optional object importObject</b>);

    Promise&lt;WebAssemblyInstantiatedSource&gt; instantiate(
        BufferSource bytes, optional object importObject);

    Promise&lt;Instance&gt; instantiate(
        Module moduleObject, optional object importObject);
};
</pre>

Additionally, a `specialize` method is provided to re-compile a module
for a different set of import objects.
This is useful for example in the case in which a Module has been serialized
and de-serialized, in which case it's specialization state is unspecified.

<pre>
[LegacyNamespace=WebAssembly, Constructor(BufferSource bytes),
Exposed=(Window,Worker,Worklet)]
interface Module {
  static sequence&lt;ModuleExportDescriptor&gt; exports(Module module);
  static sequence&lt;ModuleImportDescriptor&gt; imports(Module module);
  static sequence&lt;ArrayBuffer&gt; customSections(Module module, DOMString
sectionName);
  <b>static Promise&lt;Module&gt; specialize(
       Module module, object importObject);</b>
};
</pre>

We also provide the option to explicitly release a `WebAssembly.Memory` object.
If an exported method from a `WebAssembly.Instance` bound to this memory is
called, a RangeError should be thrown.

Question: How should this work with a shared memory?
   * Immediately halt all active calls through memories bound through this
     memory.
   * Failure if a memory is still in-use (method with access on the stack).
   * <b>As a hint to release the memory when this next becomes possible.</b>

<pre>
[LegacyNamespace=WebAssembly, Constructor(MemoryDescriptor descriptor),
Exposed=(Window,Worker,Worklet)]
interface Memory {
  void grow([EnforceRange] unsigned long delta);
  readonly attribute ArrayBuffer buffer;
  <b>void release();</b>
};
</pre>
