PROGRAM premium_tour
  # Core: regex extraction + base64 round-trip (computation only).
  LET text = "order 42 ships on 2026-10-12"
  LET nums = CORE.REGEX_MATCH "[0-9]+" $text
  LET enc = CORE.BASE64_ENCODE $text
  LET back = CORE.BASE64_DECODE $enc
  # Data: JSON path lookup + CSV parsing, all from strings.
  LET uid = DATA.JSON_GET "{\"user\": {\"id\": 7}}" "user.id"
  LET csv = DATA.CSV_PARSE "name,age\namy,30\nbo,25\n"
  LET grown = DATA.FILTER_EQ $csv "name" "amy"
  # System: time + fresh UUID (non-deterministic by design).
  LET now = TIME.NOW
  LET id = CORE.UUID4
  RETURN $nums
END
