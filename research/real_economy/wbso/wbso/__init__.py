"""WBSO candidate scanner and evidence-backed Dutch briefing generator.

Built under T27. Scope discipline, restated here because it is the whole point:

* This package **finds** and **describes**. It never sends, never registers, never spends.
* Every claim it puts in front of a company must carry a public URL the company can open.
* A briefing may say *u komt mogelijk in aanmerking* and never *u komt in aanmerking*.

`wbso.ethics` enforces the third rule mechanically, and `wbso.cli dryrun` fails if it trips.
"""

__version__ = "0.1.0"
