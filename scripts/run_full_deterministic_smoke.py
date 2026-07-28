"""Full deterministic paper smoke: problem input -> paper -> submission -> audit.

Cross-platform port (and completion) of ``run-deterministic-end-to-end.ps1``:
the PowerShell script stops at the evidence layer and prints the remaining
steps as manual instructions; this script executes the ENTIRE legal DAG chain,
including the paper itself, with zero LLM/API calls:

    create-case -> input_validation -> ingest-problem
    -> register-dataset -> complete-data-registration -> approve(data_registration)
    -> profile-dataset (data_quality gate) -> run-eda
    -> problem_analysis -> validate-model-plan -> approve(model_plan)
    -> run-baseline -> run-model-comparison -> select-model -> run-sensitivity
    -> assess/approve-paper-ready -> promote-figure x4 -> create-claim x7
    -> validate-outline -> approve(paper_outline) -> init-paper-sections
    -> update-section x12 -> complete-paper-draft -> check-paper-consistency
    -> prepare-submission (CUMCM preflight) -> degrade(supplementary_figure,
       refinement_loop) -> final_review -> export-case (audit package)
    -> validate-case, twice (hash-drift check)

Every transition follows the production DAG order -- nothing is bypassed. The
fixture problem/data/plan/outline/sections under examples/ come from the real
2026-07-26 end-to-end run (docs/端到端实跑报告-2026-07-26.md); because the whole
path is deterministic (seed=42 folds), the metric values in the fixture claim
texts and section prose reproduce exactly. Claim/figure/artifact IDs are
regenerated per run, so this script rewrites the outline's and sections' ID
references from the fixture IDs to this run's real IDs before submitting them.

Usage:  python scripts/run_full_deterministic_smoke.py <output_root>
Exit code 0 only if every stage, both validate-case passes, the consistency
gate, and the submission preflight gate all succeed.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mathworkstation.cli import main as cli_main  # noqa: E402

FIXTURES = REPO / "examples" / "fixtures"
SECTIONS = REPO / "examples" / "sections"

#: fixture claim id -> (claim_type, section_hint, evidence artifact TYPE, text)
#: -- texts verbatim from the original real run; deterministic reruns
#: reproduce the same numbers, which check-paper-consistency verifies.
FIXTURE_CLAIMS = {
    "claim-15aae502b368": ("data_fact", "data_analysis", "data_profile",
        "数据集含 442 条观测、10 个基线特征，数据质量门为 PASS 且无缺失值；目标变量 progression 取值 25–346，均值 152.13，中位数 140.5，标准差 77.09。"),
    "claim-6216872e652a": ("data_fact", "data_analysis", "eda_summary",
        "探索性分析显示 s1(总胆固醇) 与 s2(LDL) 之间、s3(HDL) 与 s4(TC/HDL 比值) 之间存在强相关，构成两组明确的多重共线性特征，是选择正则化线性模型的直接依据。"),
    "claim-4de95f663feb": ("data_fact", "data_analysis", "eda_summary",
        "与目标变量相关性最强的三个特征为 bmi(r=0.587)、s5(r=0.566) 与 bp(r=0.442)；共线性最强的两对特征为 s1-s2(r=0.897) 与 s3-s4(r=-0.739)。"),
    "claim-4d802d59f904": ("model_result", "results", "model_comparison",
        "在五折交叉验证下，lasso(α=0.5) 的 RMSE 均值为 54.825、标准差 2.793，为五个候选模型中最优；线性(54.849)与岭回归(54.827)紧随其后，随机森林(56.945)与梯度提升(57.622)明显更差。"),
    "claim-f2277bc077d8": ("model_result", "results", "model_comparison",
        "所选模型 lasso 的五折交叉验证 R² 均值为 0.4793，MAE 均值为 44.352，说明 10 个基线特征仅能解释约 48% 的一年期进展方差。"),
    "claim-b1753f7288e6": ("sensitivity", "sensitivity", "sensitivity_results",
        "在 3 个样本比例(60%/80%/100%) × 3 个随机种子的 9 次重复中，lasso 的留出 RMSE 均值分别为 55.208、54.515、52.763，最大组内相对标准差为 4.07%，最大相对退化为 4.63%，稳健性门为 PASS。"),
    "claim-f186d077beae": ("sensitivity", "sensitivity", "sensitivity_results",
        "样本比例由 60% 增至 100% 时模型性能的变化幅度被记录于敏感性分析结果，用于界定结论的稳健区间。"),
}

#: fixture figure id -> figure title (matched against this run's registry)
FIXTURE_FIGURES = {
    "figure-d4bb4f0d6c70": "目标变量 progression 分布",
    "figure-7bcf583c3d10": "数值变量相关性热力图",
    "figure-8c0270f7257b": "候选模型交叉验证比较",
    "figure-73c2b7cbf33c": "模型样本比例与随机种子敏感性",
}


class Smoke:
    def __init__(self, output_root: str) -> None:
        self.root = output_root

    def cli(self, *args: str) -> dict:
        """Run one real CLI command; raise on non-zero exit; parse JSON stdout."""
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli_main(["--output-root", self.root, *args])
        if code != 0:
            raise SystemExit(f"command failed (exit {code}): {' '.join(args)}\n{out.getvalue()}")
        text = out.getvalue().strip()
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError:
            return {"raw": text}

    def artifact_id(self, case_id: str, artifact_type: str) -> str:
        registry = Path(self.root) / case_id / "artifact_registry.jsonl"
        latest = {}
        for line in registry.read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = json.loads(line)
                latest[a["artifact_id"]] = a
        matches = [a for a in latest.values() if a["artifact_type"] == artifact_type and a["status"] == "ACTIVE"]
        if not matches:
            raise SystemExit(f"artifact not found: {artifact_type}")
        return matches[-1]["artifact_id"]

    def run(self) -> None:
        step = lambda msg: print(f"==> {msg}", flush=True)

        step("case + session")
        case = self.cli("create-case", "--competition", "CUMCM",
                        "--title", "慢性疾病一年期病情进展量化建模与风险分层")["case_id"]
        session = self.cli("create-session", "--case-id", case)["session_id"]
        print(f"    case={case} session={session}")

        step("input_validation + problem ingestion (legal DAG order, nothing bypassed)")
        self.cli("start-node", "--case-id", case, "--node-id", "input_validation")
        self.cli("succeed-node", "--case-id", case, "--node-id", "input_validation")
        self.cli("ingest-problem", "--case-id", case, "--source", str(FIXTURES / "real_case_problem.md"))

        step("data registration + quality gate + EDA")
        dataset = self.cli(
            "register-dataset", "--case-id", case,
            "--source", str(FIXTURES / "diabetes_progression.csv"),
            "--name", "糖尿病一年期进展观测数据", "--kind", "OBSERVED",
            "--license", "public research dataset (Efron et al. 2004)",
            "--description", "442 名患者基线 10 特征与一年后病情进展指数",
        )["dataset_id"]
        self.cli("complete-data-registration", "--case-id", case)
        self.cli("approve-node", "--case-id", case, "--node-id", "data_registration", "--approved-by", "smoke")
        self.cli("profile-dataset", "--case-id", case, "--dataset-id", dataset,
                 "--target-column", "progression", "--session-id", session)
        self.cli("run-eda", "--case-id", case, "--dataset-id", dataset,
                 "--target-column", "progression", "--session-id", session)

        step("problem analysis + model plan")
        self.cli("start-node", "--case-id", case, "--node-id", "problem_analysis")
        self.cli("succeed-node", "--case-id", case, "--node-id", "problem_analysis")
        self.cli("approve-node", "--case-id", case, "--node-id", "problem_analysis", "--approved-by", "smoke")
        self.cli("validate-model-plan", "--case-id", case,
                 "--source", str(FIXTURES / "real_case_model_plan.json"), "--dataset-id", dataset)
        self.cli("approve-node", "--case-id", case, "--node-id", "model_plan", "--approved-by", "smoke")
        plan = self.artifact_id(case, "model_plan_validated")

        step("baseline + model comparison + selection + sensitivity")
        self.cli("run-baseline", "--case-id", case, "--dataset-id", dataset,
                 "--target-column", "progression", "--task-type", "regression", "--session-id", session)
        comparison = self.cli("run-model-comparison", "--case-id", case,
                              "--plan-artifact-id", plan, "--session-id", session)
        experiment = comparison["result"]["experiment_id"]
        best = comparison["result"]["best_model"]
        print(f"    experiment={experiment} best={best}")
        assert best == "lasso", f"deterministic run must select lasso, got {best}"
        self.cli("select-model", "--case-id", case, "--experiment-id", experiment,
                 "--selected-model", best,
                 "--comparison-artifact-id", self.artifact_id(case, "model_comparison"),
                 "--selected-by", "smoke", "--rationale", "交叉验证主指标最优且折间标准差最小")
        self.cli("run-sensitivity", "--case-id", case, "--experiment-id", experiment,
                 "--plan-artifact-id", plan, "--session-id", session)

        step("evidence promotion (paper-ready gate) + figure promotion")
        selection = self.artifact_id(case, "model_selection")
        sensitivity = self.artifact_id(case, "sensitivity_results")
        profile_art = self.artifact_id(case, "data_profile")
        eda_art = self.artifact_id(case, "eda_summary")
        self.cli("assess-paper-ready", "--case-id", case, "--experiment-id", experiment,
                 "--selection-artifact-id", selection, "--sensitivity-artifact-id", sensitivity)
        self.cli("approve-paper-ready", "--case-id", case, "--experiment-id", experiment,
                 "--selection-artifact-id", selection, "--sensitivity-artifact-id", sensitivity,
                 "--approved-by", "smoke",
                 "--note", "证据链完整：比较、诊断、选择、敏感性、数据画像与 EDA 摘要",
                 "--additional-artifact-id", profile_art, "--additional-artifact-id", eda_art)
        approval = self.artifact_id(case, "paper_ready_approval")

        figures = self.cli("list-figures", "--case-id", case)
        figure_map: dict[str, str] = {}  # fixture figure id -> this run's figure id
        for fixture_id, title in FIXTURE_FIGURES.items():
            matches = [f for f in figures if f["title"] == title]
            assert matches, f"figure not found by title: {title}"
            figure_map[fixture_id] = matches[-1]["figure_id"]
            self.cli("promote-figure", "--case-id", case, "--figure-id", matches[-1]["figure_id"],
                     "--approval-artifact-id", approval, "--approved-by", "smoke",
                     "--note", "由确定性脚本生成，与已批准实验证据一致")

        step("claims (same texts as the original run; deterministic numbers reproduce)")
        # evidence-type -> this run's artifact id, resolved once
        evidence_by_type = {
            "data_profile": profile_art,
            "eda_summary": eda_art,
            "model_comparison": self.artifact_id(case, "model_comparison"),
            "sensitivity_results": sensitivity,
        }
        claim_map: dict[str, str] = {}  # fixture claim id -> this run's claim id
        for fixture_id, (claim_type, hint, evidence_type, text) in FIXTURE_CLAIMS.items():
            created = self.cli("create-claim", "--case-id", case, "--text", text,
                               "--claim-type", claim_type,
                               "--evidence-artifact-id", evidence_by_type[evidence_type],
                               "--section-hint", hint, "--created-by", "smoke")
            assert created["status"] == "VERIFIED", f"claim for {fixture_id} not VERIFIED: {created['status']}"
            claim_map[fixture_id] = created["claim_id"]

        def substitute(text: str) -> str:
            for old, new in {**claim_map, **figure_map}.items():
                text = text.replace(old, new)
            return text

        step("outline (fixture IDs rewritten to this run's IDs) + sections + draft")
        with tempfile.TemporaryDirectory() as tmp:
            outline_path = Path(tmp) / "outline.json"
            outline_path.write_text(
                substitute((FIXTURES / "real_case_outline.json").read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            self.cli("validate-outline", "--case-id", case, "--source", str(outline_path))
            self.cli("approve-node", "--case-id", case, "--node-id", "paper_outline", "--approved-by", "smoke")
            self.cli("init-paper-sections", "--case-id", case,
                     "--outline-artifact-id", self.artifact_id(case, "paper_outline"))
            for section_file in sorted(SECTIONS.glob("*.md")):
                section_path = Path(tmp) / section_file.name
                section_path.write_text(substitute(section_file.read_text(encoding="utf-8")), encoding="utf-8")
                self.cli("update-section", "--case-id", case, "--section-id", section_file.stem,
                         "--source", str(section_path), "--created-by", "smoke")
        self.cli("complete-paper-draft", "--case-id", case, "--session-id", session)

        def find_gate(payload) -> str | None:
            """First 'gate' value anywhere in the nested command output."""
            if isinstance(payload, dict):
                if isinstance(payload.get("gate"), str):
                    return payload["gate"]
                for value in payload.values():
                    found = find_gate(value)
                    if found is not None:
                        return found
            elif isinstance(payload, list):
                for value in payload:
                    found = find_gate(value)
                    if found is not None:
                        return found
            return None

        step("consistency gate + submission preflight")
        consistency = self.cli("check-paper-consistency", "--case-id", case)
        gate = find_gate(consistency)
        assert gate == "PASS", f"consistency gate: {gate}\n{json.dumps(consistency, ensure_ascii=False)[:2000]}"
        submission = self.cli("prepare-submission", "--case-id", case, "--profile", "CUMCM")
        sub_gate = find_gate(submission)
        assert sub_gate == "PASS", f"submission preflight gate: {sub_gate}\n{json.dumps(submission, ensure_ascii=False)[:2000]}"

        step("recorded omissions + final review + audit export")
        self.cli("degrade-node", "--case-id", case, "--node-id", "supplementary_figure",
                 "--approved-by", "smoke", "--reason", "冒烟运行不生成补充图")
        self.cli("degrade-node", "--case-id", case, "--node-id", "refinement_loop",
                 "--approved-by", "smoke", "--reason", "确定性冒烟不执行 LLM 精修")
        self.cli("start-node", "--case-id", case, "--node-id", "final_review")
        self.cli("succeed-node", "--case-id", case, "--node-id", "final_review")
        self.cli("approve-node", "--case-id", case, "--node-id", "final_review", "--approved-by", "smoke")
        self.cli("export-case", "--case-id", case, "--session-id", session)

        step("validate-case, twice (hash-drift check)")
        first = self.cli("validate-case", "--case-id", case)
        assert first["valid"], f"validate-case #1 failed: {first}"
        second = self.cli("validate-case", "--case-id", case)
        assert second["valid"], f"validate-case #2 failed: {second}"

        final_md = Path(self.root) / case / "paper" / "final.md"
        assert final_md.is_file() and final_md.stat().st_size > 4000, "final paper missing or implausibly small"
        content = final_md.read_text(encoding="utf-8")
        # The fixture section prose paraphrases metrics ("Lasso 取得最优")
        # rather than quoting raw numbers; the literal figures live in the
        # registry-sourced claims and were already verified attributed by the
        # consistency gate above. So assert on what the final paper itself
        # guarantees: the selected model is named, and every promoted figure
        # was actually embedded (not just cited).
        assert "Lasso" in content, "selected model (Lasso) not named in the final paper"
        assert content.count("![") >= 4, f"expected >=4 embedded figures, got {content.count('![')}"

        print(json.dumps({
            "case_id": case,
            "experiment_id": experiment,
            "best_model": best,
            "claims": claim_map,
            "figures": figure_map,
            "consistency_gate": gate,
            "submission_gate": sub_gate,
            "validate_case": "valid twice, no hash drift",
            "final_paper_bytes": final_md.stat().st_size,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_full_deterministic_smoke.py <output_root>")
    Smoke(sys.argv[1]).run()
