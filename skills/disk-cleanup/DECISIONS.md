# Decisions

- Scan only the home folder, on every OS. Reason: best practice; it never needs admin rights and `clean` refuses
  anything outside it, so it cannot touch system files.
- Size with `du -sk` when it exists, else sum file sizes in Python (Windows). Reason: measured; `du` is much faster, and
  the fallback keeps the script dependency-free.
- One `KNOWN` list for all OSes instead of per-OS lists. Reason: YAGNI; globs that do not exist on this OS match
  nothing, so no OS detection is needed.
