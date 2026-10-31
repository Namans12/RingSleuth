// @vitest-environment node
// Regressions against the original submitted batch; source files are read-only.
import { readFileSync, mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { crossCheckAnswerTrace, crossCheckSummaryAnswers, validateAnswer, validateSummary, validateTrace } from "@/contracts";
import { DataClient } from "@/data/client";
import { buildRows, overviewStats } from "@/data/diagnostics";
import { clone, memoryFetch } from "@/test/fixtures";
const root = fileURLToPath(new URL("../../", import.meta.url));
const ids = Array.from({ length: 20 }, (_, i) => `HHG-${String(i + 1).padStart(3, "0")}`);
const text = (path) => readFileSync(join(root, path), "utf8");
const answers = new Map(ids.map((id) => [id, JSON.parse(text(`cases/${id}.json`))]));
const traces = new Map(ids.map((id) => [id, validateTrace(JSON.parse(text(`runs/latest/traces/${id}.trace.json`)), id).trace]));
const summary = JSON.parse(text("runs/latest/batch_summary.json"));
const customerReports = ["HHG-003", "HHG-004", "HHG-006", "HHG-008", "HHG-009", "HHG-011", "HHG-016", "HHG-018"];
function files() {
  const result = {
    "data-manifest.json": { mode: "official", generated_at: "2026-11-01T00:00:00Z", cases_found: 20, valid_cases: 20, traces_found: 20, summary_found: true, errors: [], warnings: [], case_files: ids, trace_files: ids },
    "batch_summary.json": text("runs/latest/batch_summary.json")
  };
  for (const id of ids) {
    result[`cases/${id}.json`] = text(`cases/${id}.json`);
    result[`traces/${id}.trace.json`] = text(`runs/latest/traces/${id}.trace.json`);
  }
  return result;
}
function modifiedReport() {
  return { answer: clone(answers.get("HHG-004")), trace: clone(traces.get("HHG-004")) };
}
describe("submitted customer reports", () => {
  it.each(customerReports)("accepts %s only with its existing customer-report trace", (id) => {
    const original = JSON.stringify(answers.get(id));
    expect(validateAnswer(answers.get(id), id).contractValid).toBe(false);
    expect(validateAnswer(answers.get(id), id, traces.get(id)).contractValid).toBe(true);
    expect(JSON.stringify(answers.get(id))).toBe(original);
  });
  it("keeps no-follow-up changes invalid for a risk-score trigger or another case's trace", () => {
    const { answer, trace } = modifiedReport();
    trace.trigger.trigger_type = "risk_score";
    expect(validateAnswer(answer, answer.case_id, trace).contractValid).toBe(false);
    expect(validateAnswer(answer, answer.case_id, traces.get("HHG-003")).contractValid).toBe(false);
    trace.trigger.trigger_type = "customer_report";
    trace.trigger.trigger_text = " ";
    expect(validateAnswer(answer, answer.case_id, trace).contractValid).toBe(false);
  });
  it("still rejects an unexplained action change and invalid fraud outcome fields", () => {
    const { answer, trace } = modifiedReport();
    answer.next_best_actions.what_changed = "nothing";
    expect(validateAnswer(answer, answer.case_id, trace).diagnostics.some((d) => /must explain/.test(d.message))).toBe(true);
    answer.case.fraud_probability = 2;
    expect(validateAnswer(answer, answer.case_id, trace).contractValid).toBe(false);
  });
});
describe("submitted batch summary", () => {
  it("reads omitted metadata only from matching traces, preserving the original object", () => {
    const before = JSON.stringify(summary);
    const result = validateSummary(summary, traces);
    expect(result.diagnostics.filter((d) => d.level === "error")).toEqual([]);
    expect(result.diagnostics.filter((d) => d.level === "info")).toHaveLength(20);
    expect(result.summary?.cases.every((row) => row.validation_passed === traces.get(row.case_id)?.validation.passed)).toBe(true);
    expect(JSON.stringify(summary)).toBe(before);
    const views = ids.map((id) => validateAnswer(answers.get(id), id, traces.get(id)).view);
    expect(crossCheckSummaryAnswers(result.summary, views)).toEqual([]);
  });
  it("cannot fill missing fields without a matching trace", () => {
    const missing = new Map(traces);
    missing.delete("HHG-001");
    expect(validateSummary(summary, missing).summary).toBeUndefined();
    missing.set("HHG-001", traces.get("HHG-002"));
    expect(validateSummary(summary, missing).summary).toBeUndefined();
  });
  it("never overwrites explicit conflicts or invalid values with trace values", () => {
    const changed = clone(summary);
    changed.cases[0].card_id = "OTHER-CARD";
    changed.cases[0].validation_passed = false;
    const result = validateSummary(changed, traces);
    expect(result.summary?.cases[0]?.card_id).toBe("OTHER-CARD");
    expect(result.summary?.cases[0]?.validation_passed).toBe(false);
    expect(result.diagnostics.some((d) => /card_id disagrees/.test(d.message))).toBe(true);
    expect(result.diagnostics.some((d) => /validation_passed disagrees/.test(d.message))).toBe(true);
    changed.cases[0].card_id = null;
    expect(validateSummary(changed, traces).summary).toBeUndefined();
  });
  it("checks summary action-change flags against the original answer names", () => {
    const result = validateSummary(summary, traces).summary;
    result.cases[0].actions_changed = !result.cases[0].actions_changed;
    const views = ids.map((id) => validateAnswer(answers.get(id), id, traces.get(id)).view);
    expect(crossCheckSummaryAnswers(result, views).some((d) => /actions_changed/.test(d.message))).toBe(true);
  });
});
describe("browser and sync agreement", () => {
  it("loads all 20 reports, the original summary and all six provenance warnings", async () => {
    const bundle = await new DataClient("./data", memoryFetch(files())).loadBundle();
    expect(bundle.mode).toBe("official");
    expect(bundle.cases.every((entry) => entry.answer?.contractValid)).toBe(true);
    expect(bundle.summaryFile?.text).toBe(text("runs/latest/batch_summary.json"));
    expect(bundle.diagnostics.filter((d) => d.level === "error")).toEqual([]);
    const warnings = bundle.diagnostics.filter((d) => d.level === "warning");
    expect(warnings).toHaveLength(6);
    expect(warnings.every((d) => /cannot be independently cross-checked/.test(d.message))).toBe(true);
    const rows = buildRows(bundle);
    expect(rows.filter((row) => row.changed)).toHaveLength(16);
    expect(overviewStats(bundle, rows)).toMatchObject({ source: "batch_summary", casesTotal: 20, casesValid: 20, contractValid: 20, actionsChanged: 16, totalExposure: 5127.41, sarFiled: 6, verdicts: { fraud: 10, legitimate: 4, uncertain: 6 } });
  });
  it.each(["missing", "wrong case", "malformed", "invalid cutoff"])("does not trust a %s trace to excuse an action change", async (kind) => {
    const input = files();
    const path = "traces/HHG-004.trace.json";
    if (kind === "missing") delete input[path];
    else {
      const trace = clone(traces.get("HHG-004"));
      if (kind === "wrong case") trace.case_id = "HHG-003";
      if (kind === "invalid cutoff") trace.cutoff_ts = "1900-01-01";
      input[path] = kind === "malformed" ? "not JSON" : trace;
    }
    const bundle = await new DataClient("./data", memoryFetch(input)).loadBundle();
    expect(bundle.mode).toBe("partial");
    expect(bundle.cases.find((entry) => entry.caseId === "HHG-004")?.answer?.contractValid).toBe(false);
  });
  it("does not treat contradictory backend validation flags as a trustworthy pass", () => {
    const trace = clone(traces.get("HHG-001"));
    trace.validation.errors = ["a backend error"];
    expect(validateTrace(trace).diagnostics.some((d) => d.level === "error" && /claims a pass/.test(d.message))).toBe(true);
  });
  it.each(["backend validation", "read-back", "graph write"])("downgrades an official claim when the final %s fails", async (kind) => {
    const input = files();
    const trace = clone(traces.get("HHG-001"));
    const batch = clone(summary);
    if (kind === "backend validation") {
      trace.validation.passed = false;
      batch.cases_valid = 19;
    } else if (kind === "read-back") {
      trace.graph_write.read_back_ok = false;
    } else {
      const answer = clone(answers.get("HHG-001"));
      answer.case.written_to_graph = false;
      answer.case.graph_case_id = "";
      input["cases/HHG-001.json"] = answer;
      trace.graph_write.written = false;
      trace.graph_write.graph_case_id = "";
      trace.graph_write.read_back_ok = false;
      batch.cases[0].written_to_graph = false;
      batch.cases_written_to_graph = 19;
    }
    input["traces/HHG-001.trace.json"] = trace;
    input["batch_summary.json"] = batch;
    const bundle = await new DataClient("./data", memoryFetch(input)).loadBundle();
    expect(bundle.mode).toBe("partial");
  });
  it("keeps unknown prior-case citations visible as warnings", () => {
    const id = "HHG-003";
    const answer = clone(answers.get(id));
    answer.case.similar_prior_cases.push("CC-NOT-IN-EVIDENCE");
    const result = crossCheckAnswerTrace(validateAnswer(answer, id, traces.get(id)).view, traces.get(id));
    expect(result.some((d) => d.level === "warning" && /or the answer's graph lookup evidence/.test(d.message))).toBe(true);
  });
  it("strictly syncs the submitted batch without changing any original or copied result bytes", async () => {
    const { runSync } = await import("./lib/sync-core.mjs");
    const originals = new Map([
      "runs/latest/batch_summary.json",
      ...ids.flatMap((id) => [`cases/${id}.json`, `runs/latest/traces/${id}.trace.json`]),
    ].map((path) => [path, text(path)]));
    const tmp = mkdtempSync(join(tmpdir(), "ringsleuth-regression-"));
    const out = join(tmp, "public", "data");
    mkdirSync(out, { recursive: true });
    try {
      const result = await runSync({ kind: "official", sourceRoot: root, outDir: out, strict: true, requireTraces: true, log: () => {
      } });
      expect(result.exitCode).toBe(0);
      expect(result.errors).toEqual([]);
      expect(result.warnings).toHaveLength(6);
      expect(result.manifest).toMatchObject({ mode: "official", cases_found: 20, valid_cases: 20, traces_found: 20 });
      for (const [path, bytes] of originals) expect(text(path)).toBe(bytes);
      expect(readFileSync(join(out, "batch_summary.json"), "utf8")).toBe(originals.get("runs/latest/batch_summary.json"));
      for (const id of ids) {
        expect(readFileSync(join(out, "cases", `${id}.json`), "utf8")).toBe(originals.get(`cases/${id}.json`));
        expect(readFileSync(join(out, "traces", `${id}.trace.json`), "utf8")).toBe(originals.get(`runs/latest/traces/${id}.trace.json`));
      }
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
