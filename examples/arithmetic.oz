PROGRAM arithmetic
  LET a = CORE.ADD 20 22
  LET b = CORE.MUL $a 2
  LET c = CORE.SUB $b 4
  LET ok = CORE.GT $c 70
  RETURN $c
END
