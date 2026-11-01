# FIFO reference specifications

`Channel.tla` and `InnerFIFO.tla` come from `tlaplus/Examples` at revision
`0e32a039a4286cc3e1b0f70c00eaff3178d49f85`:

- https://github.com/tlaplus/Examples/blob/0e32a039a4286cc3e1b0f70c00eaff3178d49f85/specifications/SpecifyingSystems/FIFO/Channel.tla
- https://github.com/tlaplus/Examples/blob/0e32a039a4286cc3e1b0f70c00eaff3178d49f85/specifications/SpecifyingSystems/FIFO/InnerFIFO.tla

The specifications accompany Leslie Lamport's *Specifying Systems* chapter
“A FIFO”. `LICENSE.md` preserves the upstream MIT license and attribution.

`ReferenceFIFO.tla` adds a capacity guard to `BufRcv` for finite model checking.
`ReferenceFIFO.cfg` chooses two messages and capacity two. The integration test
compares its initial states, reachable states, and transitions against the Python
port after matching the channel fields and the binary handshake values.
