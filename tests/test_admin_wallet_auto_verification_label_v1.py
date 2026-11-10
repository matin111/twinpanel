"""Admin-only automatic verification labels for wallet top-ups.

The ledger must continue using `approved`; the display derives its label from
the durable automatic credit source recorded in review_note.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components/payments-review-runtime.tsx"


def _run_status_cases():
    source = COMPONENT.read_text(encoding="utf-8")
    start = source.index("function adminPaymentDisplayStatus(")
    end = source.index("\n}\n", start) + 2
    body = source[start:end]
    body = body.replace(
        "kind:PaymentKind,status:string,reviewNote:unknown):string",
        "kind,status,reviewNote)",
    )
    assert "displayStatus:adminPaymentDisplayStatus(\"wallet\",status,row.review_note)" in source
    assert "statusLabel(row.displayStatus,pick)" in source
    script = body + """
const tests=[
  ["wallet","approved","auto-credit:sms-reader:122;target=customer","auto_verified"],
  ["wallet","approved","auto-credit:crypto:usdt_bep20;target=customer","auto_verified"],
  ["wallet","approved","auto-credit:admin;target=customer","approved"],
  ["wallet","approved","", "approved"],
  ["wallet","approved","auto-chain-check: pending","approved"],
  ["wallet","pending_payment","auto-credit:sms-reader:122;target=customer","pending_payment"],
  ["purchase","approved","auto-credit:sms-reader:122;target=customer","approved"],
  ["purchase","auto_verified","", "auto_verified"],
];
for(const [kind,status,note,expected] of tests) {
  const actual=adminPaymentDisplayStatus(kind,status,note);
  if(actual!==expected)throw new Error(kind+" "+status+" returned "+actual+" expected "+expected);
}
console.log("PASS",tests.length,"admin payment display status cases");
"""
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_admin_only_auto_payment_labels():
    output = _run_status_cases()
    assert "PASS 8" in output


def test_financial_status_and_review_controls_unchanged():
    source = COMPONENT.read_text(encoding="utf-8")
    assert "status:s(row.status)" in source
    assert "        status,\n        displayStatus:adminPaymentDisplayStatus" in source
    assert "const status=row.status.toLowerCase()" in source
    assert "const reviewable=needsPaymentReview(row)" in source
    assert "finalStatuses" in source
