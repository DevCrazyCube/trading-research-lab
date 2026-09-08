"""Free, public, unauthenticated data sources.

| module      | endpoint                                              | what it gives | auth |
|-------------|-------------------------------------------------------|---------------|------|
| github_orgs | api.github.com/search/users, /search/repositories, /orgs | the population and the R&D evidence | none |
| peppol      | directory.peppol.eu/search/1.0/json                   | NL legal-entity corroboration (KVK/BTW id) | none |
| tenderned   | www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties | public-sector demand signal (see module note) | none |
| website     | the candidate's own site                              | liveness + careers signal, robots-permitting | none |

Every one of them was probed working on 2026-08-19 from this machine. `tenderned` carries a
measured negative that corrects the survey document; read its module docstring.
"""
