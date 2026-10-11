PROGRAM control_flow
  LET x = 12
  LET label = "small"
  IF CORE.GT $x 10 THEN
    LET big = CORE.CONCAT $label "-confirmed-big"
  ELSE
    LET big = $label
  END
  RETURN $label
END
