"use strict";

const { describe, test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  GIT_MUTATION_RE,
  extractCommandQuery,
  extractPromptQuery,
} = require("./graphbase-codex-hook");

describe("extractPromptQuery", () => {
  test("keeps meaningful unique tokens", () => {
    assert.equal(
      extractPromptQuery("Please check auth-service topology and JWT rotation impact"),
      "check auth-service topology JWT rotation impact"
    );
  });

  test("returns null when prompt has no useful tokens", () => {
    assert.equal(extractPromptQuery("do it"), null);
  });

  test("caps long prompts", () => {
    const query = extractPromptQuery(
      "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"
    );
    assert.equal(query.split(" ").length, 12);
  });
});

describe("extractCommandQuery", () => {
  test("extracts a file basename from a read-like command", () => {
    assert.equal(extractCommandQuery("sed -n 1,120p src/engines/hygiene.py"), "hygiene");
  });

  test("extracts rg search text", () => {
    assert.equal(extractCommandQuery("rg \"GraphbaseMemory\" src"), "GraphbaseMemory");
  });

  test("returns null for unrelated command", () => {
    assert.equal(extractCommandQuery("git status --short"), null);
  });
});

describe("GIT_MUTATION_RE", () => {
  test("matches local history mutations", () => {
    assert.ok(GIT_MUTATION_RE.test("git commit -m docs"));
    assert.ok(GIT_MUTATION_RE.test("git merge main"));
    assert.ok(GIT_MUTATION_RE.test("git rebase origin/main"));
    assert.ok(GIT_MUTATION_RE.test("git cherry-pick abc123"));
    assert.ok(GIT_MUTATION_RE.test("git pull"));
  });

  test("does not match read-only git commands", () => {
    assert.equal(GIT_MUTATION_RE.test("git status"), false);
    assert.equal(GIT_MUTATION_RE.test("git diff HEAD"), false);
    assert.equal(GIT_MUTATION_RE.test("git log --oneline"), false);
  });
});

describe("source security contract", () => {
  test("hook never enables shell interpolation for spawnSync", () => {
    const source = fs.readFileSync(path.join(__dirname, "graphbase-codex-hook.js"), "utf-8");
    assert.equal((source.match(/shell:\s*true/g) || []).length, 0);
  });

  test("hook passes prompt query after --", () => {
    const source = fs.readFileSync(path.join(__dirname, "graphbase-codex-hook.js"), "utf-8");
    assert.match(source, /\["surface",\s*"--",\s*query\]/);
  });
});
