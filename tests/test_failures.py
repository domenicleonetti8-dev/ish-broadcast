import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eira_inventor_holographic_lab.contracts import validate_assembly,ContractError
bad=[{"assembly_id":"x","name":"x","parts":[{"part_id":"p","name":"p","geometry":{"kind":"banana"},"transform":{"location":[0,0,0],"rotation_deg":[0,0,0],"scale":[1,1,1]},"source":{"provenance":"inferred","confidence":.5}}]}]
for x in bad:
 try: validate_assembly(x); raise SystemExit("FAIL: malformed accepted")
 except ContractError: pass
print("FAILURE REJECTION PASS")
