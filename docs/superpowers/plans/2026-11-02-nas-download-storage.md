# NAS download storage implementation plan

Goal: Use SSD storage for download staging without moving media libraries, and require DSM Container Manager before Synology setup writes anything.

- [x] Add shell integration tests using temporary host trees and stubbed NAS commands. Cover missing/stopped Container Manager, absent docker shared folder, optional SSD paths, unavailable Unraid pool, existing download protection, and generated mount paths.
- [x] Add an Unraid preparation script that validates a mounted cache pool, creates download staging folders, and installs the matching local Docker template. Keep /data on the user share; mount only complete/incomplete staging on the pool.
- [x] Update both Unraid templates with the two nested staging mounts and preparation instructions. Leave finished torrents and media under /data on the array.
- [x] Gate Synology setup on Container Manager, a working Docker daemon, and the existing docker shared folder before migration/mkdir. Support an optional existing SSD shared folder through DOWNLOAD_CACHE, generating the same two nested mounts.
- [x] Document HDD import copies, SSD capacity, Synology SSD-volume versus SSD-cache behavior, and safe treatment of existing installations. Update translated platform guides.
- [x] Run the shell integration tests, shell syntax checks, XML parsing, generated Compose validation, and focused repository checks. Review the diff without touching unrelated user changes.

Constraints: No automatic drive formatting, DSM package installation, storage-pool reconfiguration, live migration, or changes to the user's running server. Existing populated staging folders must not be hidden by new mounts.

Validation: 18 installer integration tests passed; both shell scripts passed syntax checks; generated HDD and SSD Synology Compose files plus the static Compose file passed Docker Compose validation; both XML templates parsed in the tests. Independent review findings on custom IDs and Unraid template storage changes were fixed and covered by regression tests. NAS shell commands were simulated for installer tests; the installers were not run against a live DSM or Unraid configuration.
