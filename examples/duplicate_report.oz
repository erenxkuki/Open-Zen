PROGRAM duplicate_report
  # Task: list sandbox dir, hash each file, group duplicates, summarize.
  LET entries = FS.LIST "."
  LET h1 = FS.HASH_FILE "a.txt"
  LET info = SYS.INFO
  RETURN $entries
END
