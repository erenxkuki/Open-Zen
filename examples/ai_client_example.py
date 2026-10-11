"""SDK example: convert model output into validated Open Zen instructions.

Never executes raw model output: parse -> validate -> capability check -> execute.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen import OpenZenClient
from openzen.ai_adapter import MockAdapter, run_task

MODEL_OUTPUT = """PROGRAM hello_math
  LET total = CORE.ADD 20 22
  RETURN $total
END
"""

client = OpenZenClient.local()
stages = run_task("Add 20 and 22.", MockAdapter(program_text=MODEL_OUTPUT), client)
print("status:", stages["execution"]["status"])
print("result:", stages["execution"]["result"])
assert stages["execution"]["result"] == 42
