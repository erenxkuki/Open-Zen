PROGRAM inspect_workspace
  LET entries = FS.LIST "."
  LET summary = DATA.SUMMARIZE $entries
  RETURN $summary
END
