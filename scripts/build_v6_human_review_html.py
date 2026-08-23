from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from run_v6_independent_judge import DIMENSIONS


def _escape_text(value: str) -> str:
    return html.escape(value, quote=False)


def _radio_group(name: str) -> str:
    return "".join(
        f'<label><input type="radio" name="{html.escape(name)}" value="{value}"> {label}</label>'
        for value, label in (("LEFT", "Left"), ("TIE", "Tie"), ("RIGHT", "Right"))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a standalone blind-human-review HTML packet.")
    parser.add_argument("--root", default="artifacts/meta_benchmark/judge_v1")
    parser.add_argument("--pair-id", default="m24-real-current-ab")
    args = parser.parse_args()

    root = Path(args.root)
    packet_path = root / "packets" / f"{args.pair_id}.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))

    private_tokens = (
        "REAL_VS_CURRENT",
        "REAL_VS_REAL",
        "CURRENT_VS_OLDER",
        "REAL_EXCELLENT",
        "WORKSTATION_CURRENT",
        "WORKSTATION_OLDER",
        "source_path",
        "case_id",
        "award",
        "origin",
    )
    serialized = json.dumps(packet, ensure_ascii=False)
    leaked = [token for token in private_tokens[:6] if token.lower() in serialized.lower()]
    if leaked:
        raise RuntimeError(f"refusing to build human packet with provenance leakage: {leaked}")

    dimensions_html = "\n".join(
        f"<tr><td>{html.escape(name)}</td><td class='choices'>{_radio_group('dim_' + name)}</td></tr>"
        for name in DIMENSIONS
    )
    left_text = _escape_text(str(packet["left"]["text"]))
    right_text = _escape_text(str(packet["right"]["text"]))
    pair_id = html.escape(str(packet["pair_id"]))

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Blind Modeling Paper Review — {pair_id}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; background: #f5f5f5; color: #222; }}
header {{ position: sticky; top: 0; z-index: 5; background: white; padding: 12px 18px; border-bottom: 1px solid #ddd; }}
header h1 {{ margin: 0 0 6px; font-size: 20px; }}
.notice {{ font-size: 13px; line-height: 1.45; color: #444; }}
.papers {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px; }}
.paper {{ background: white; border: 1px solid #ddd; border-radius: 8px; min-width: 0; }}
.paper h2 {{ margin: 0; padding: 10px 12px; border-bottom: 1px solid #ddd; font-size: 18px; }}
.paper pre {{ white-space: pre-wrap; word-wrap: break-word; max-height: 65vh; overflow: auto; padding: 12px; margin: 0; font: 13px/1.48 ui-monospace, SFMono-Regular, Consolas, monospace; }}
.review {{ margin: 0 12px 24px; background: white; border: 1px solid #ddd; border-radius: 8px; padding: 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #eee; padding: 8px; text-align: left; }}
.choices label {{ margin-right: 18px; white-space: nowrap; }}
textarea {{ width: 100%; min-height: 110px; box-sizing: border-box; }}
input[type=range] {{ width: 260px; }}
button {{ margin-right: 8px; padding: 8px 12px; }}
#status {{ font-size: 13px; color: #444; margin-top: 8px; }}
</style>
</head>
<body>
<header>
  <h1>Blind mathematical-modeling paper review</h1>
  <div class="notice">
    Pair: <code>{pair_id}</code>. The source, award, authorship, and generator identity are intentionally hidden.
    Judge the paper as a competition submission. Do not reward formula/figure/table counts by themselves.
    This packet is text-only: do not claim visual-layout quality from it.
  </div>
</header>
<section class="papers">
  <article class="paper"><h2>LEFT PAPER</h2><pre>{left_text}</pre></article>
  <article class="paper"><h2>RIGHT PAPER</h2><pre>{right_text}</pre></article>
</section>
<section class="review">
  <h2>Rubric</h2>
  <table>
    <thead><tr><th>Dimension</th><th>Preference</th></tr></thead>
    <tbody>{dimensions_html}</tbody>
  </table>
  <h3>Overall preference</h3>
  <div class="choices">{_radio_group('overall')}</div>
  <h3>Confidence</h3>
  <input id="confidence" type="range" min="0" max="100" value="75">
  <span id="confidenceValue">0.75</span>
  <h3>Blind-review attestation</h3>
  <label><input id="blindAttestation" type="checkbox"> I made this judgment from the anonymized contents before revealing or using source/award identity.</label>
  <h3>Concise evidence/rationale</h3>
  <textarea id="rationale" placeholder="Briefly explain the strongest reasons. Do not discuss guessed provenance."></textarea>
  <p>
    <button id="copy">Copy vote JSON</button>
    <button id="download">Download vote JSON</button>
  </p>
  <div id="status"></div>
</section>
<script>
const pairId = {json.dumps(str(packet['pair_id']))};
const dimensions = {json.dumps(DIMENSIONS)};
const confidence = document.getElementById('confidence');
const confidenceValue = document.getElementById('confidenceValue');
confidence.addEventListener('input', () => confidenceValue.textContent = (Number(confidence.value)/100).toFixed(2));
function selected(name) {{
  const node = document.querySelector(`input[name="${{name}}"]:checked`);
  return node ? node.value : null;
}}
function buildVote() {{
  const overall = selected('overall');
  if (!overall) throw new Error('Choose an overall preference first.');
  if (!document.getElementById('blindAttestation').checked) throw new Error('Confirm the blind-review attestation before exporting.');
  const dim = {{}};
  for (const name of dimensions) dim[name] = selected('dim_' + name) || 'TIE';
  return {{
    schema_version: 1,
    pair_id: pairId,
    decision: overall,
    confidence: Number(confidence.value)/100,
    dimensions: dim,
    rationale: document.getElementById('rationale').value.trim(),
    blind_verified: true,
    blindness_attestation: 'content_only_before_provenance_reveal',
    visual_dimension: 'UNVERIFIED_TEXT_ONLY'
  }};
}}
async function copyVote() {{
  try {{
    const text = JSON.stringify(buildVote(), null, 2);
    await navigator.clipboard.writeText(text);
    document.getElementById('status').textContent = 'Vote JSON copied.';
  }} catch (e) {{ document.getElementById('status').textContent = e.message; }}
}}
function downloadVote() {{
  try {{
    const text = JSON.stringify(buildVote(), null, 2);
    const blob = new Blob([text], {{type: 'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = pairId + '-human-vote.json';
    a.click();
    URL.revokeObjectURL(a.href);
    document.getElementById('status').textContent = 'Vote JSON downloaded.';
  }} catch (e) {{ document.getElementById('status').textContent = e.message; }}
}}
document.getElementById('copy').addEventListener('click', copyVote);
document.getElementById('download').addEventListener('click', downloadVote);
</script>
</body>
</html>
"""

    output_dir = root / "human_review"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{args.pair_id}.html"
    output.write_text(document, encoding="utf-8")
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
