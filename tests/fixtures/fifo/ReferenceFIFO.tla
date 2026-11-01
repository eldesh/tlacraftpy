------------------------- MODULE ReferenceFIFO -------------------------
EXTENDS InnerFIFO
CONSTANT Capacity

BoundedNext ==
    \/ (\E msg \in Message : SSend(msg))
    \/ (Len(q) < Capacity /\ BufRcv)
    \/ BufSend
    \/ RRcv

BoundedSpec == Init /\ [][BoundedNext]_<<in, out, q>>
=============================================================================
