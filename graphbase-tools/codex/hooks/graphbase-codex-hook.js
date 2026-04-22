/**
 * graphbase-codex-hook.js — Codex hook dispatcher for Graphbase Memories.
 *
 * No npm dependencies. Uses only Node.js built-ins.
 *
 * Supported Codex hook events:
 *   - SessionStart: injects a lightweight project-memory reminder.
 *   - UserPromptSubmit: surfaces Graphbase memories from prompt keywords.
 *   - PostToolUse: after successful git mutations, checks changed file names for stale memory.
 *
 * Security constraints:
 *   - shell: false for subprocesses that receive user-controlled data.
 *   - User prompt text is passed as one argv element after "--".
 *   - Hook errors are swallowed and the process exits 0.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const MAX_QUERY_WORDS = 12;
const MAX_KEYWORDS = 10;
const GIT_MUTATION_RE = /\bgit\s+(commit|merge|rebase|cherry-pick|pull)(\s|$)/;
const TOKEN_RE = /[A-Za-z][A-Za-z0-9_.:/-]{2,}/g;
const STOP_WORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "this",
  "that",
  "from",
  "into",
  "build",
  "make",
  "please",
  "using",
  "about",
  "should",
  "would",
  "could",
]);

function readInput() {
  try {
    return JSON.parse(fs.readFileSync(0, "utf-8"));
  } catch (_) {
    return null;
  }
}

let cachedGraphbaseBin = undefined;

function resolveGraphbaseBin() {
  if (cachedGraphbaseBin !== undefined) return cachedGraphbaseBin;

  const checker = process.platform === "win32" ? "where" : "which";
  const cmd = process.platform === "win32" ? "graphbase.cmd" : "graphbase";
  const result = spawnSync(checker, [cmd], {
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 1000,
    encoding: "utf-8",
    shell: false,
  });

  cachedGraphbaseBin = result.status === 0 ? cmd : null;
  return cachedGraphbaseBin;
}

function extractPromptQuery(prompt) {
  if (!prompt || typeof prompt !== "string") return null;
  const seen = new Set();
  const tokens = [];
  for (const match of prompt.matchAll(TOKEN_RE)) {
    const token = match[0].replace(/^[-_.:/]+|[-_.:/]+$/g, "");
    const key = token.toLowerCase();
    if (token.length < 3 || STOP_WORDS.has(key) || seen.has(key)) continue;
    seen.add(key);
    tokens.push(token);
    if (tokens.length >= MAX_QUERY_WORDS) break;
  }
  return tokens.length ? tokens.join(" ") : null;
}

function extractCommandQuery(command) {
  if (!command || typeof command !== "string") return null;

  const fileMatch = command.match(
    /\b(?:cat|sed|nl|less|head|tail|python|node|pytest|ruff)\s+(?:-[A-Za-z0-9]+\s+)*([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)/
  );
  if (fileMatch) {
    const base = path.basename(fileMatch[1], path.extname(fileMatch[1]));
    if (base.length >= 3) return base;
  }

  const searchMatch = command.match(/\b(?:rg|grep)\s+(?:-[A-Za-z0-9-]+\s+)*['"]?([^'"\s][^'"]{2,80})['"]?/);
  if (searchMatch) {
    return searchMatch[1].trim();
  }

  return null;
}

function sendAdditionalContext(eventName, context) {
  if (!context || !context.trim()) return;
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: eventName,
        additionalContext: context.trim(),
      },
    }) + "\n"
  );
}

function runGraphbaseSurface(cwd, query) {
  if (!cwd || !path.isAbsolute(cwd) || !query || query.length < 3) return null;
  const bin = resolveGraphbaseBin();
  if (!bin) return null;

  const result = spawnSync(bin, ["surface", "--", query], {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 6000,
    encoding: "utf-8",
    shell: false,
  });

  if (result.status !== 0) return null;
  return result.stderr && result.stderr.trim() ? result.stderr.trim() : null;
}

function runGraphbaseKeywords(cwd, keywords) {
  if (!cwd || !path.isAbsolute(cwd) || !keywords.length) return null;
  const bin = resolveGraphbaseBin();
  if (!bin) return null;

  const result = spawnSync(bin, ["surface", "--keywords", keywords.join(",")], {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 6000,
    encoding: "utf-8",
    shell: false,
  });

  if (result.status !== 0) return null;
  return result.stderr && result.stderr.trim() ? result.stderr.trim() : null;
}

function handleSessionStart(input) {
  const source = input.source || "startup";
  sendAdditionalContext(
    "SessionStart",
    `Graphbase memory is available for this ${source} session. Before substantial edits, call retrieve_context(project_id="<project>", scope="project") or use the graphbase-session skill.`
  );
}

function handleUserPromptSubmit(input) {
  const cwd = input.cwd || "";
  const query = extractPromptQuery(input.prompt);
  const context = runGraphbaseSurface(cwd, query);
  if (context) sendAdditionalContext("UserPromptSubmit", context);
}

function handlePostToolUse(input) {
  if (input.tool_name !== "Bash") return;

  const command = input.tool_input?.command || "";
  if (!GIT_MUTATION_RE.test(command)) return;

  const response = input.tool_response;
  if (response && typeof response === "object" && response.exit_code !== undefined && response.exit_code !== 0) {
    return;
  }

  const cwd = input.tool_input?.cwd || input.cwd || "";
  if (!path.isAbsolute(cwd)) return;

  const diff = spawnSync("git", ["diff", "--name-only", "HEAD~1", "HEAD"], {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 3000,
    encoding: "utf-8",
    shell: false,
  });

  if (diff.status !== 0 || !diff.stdout.trim()) return;

  const keywords = [
    ...new Set(
      diff.stdout
        .trim()
        .split("\n")
        .map((filePath) => path.basename(filePath, path.extname(filePath)))
        .filter((item) => item.length >= 3)
    ),
  ].slice(0, MAX_KEYWORDS);

  const context = runGraphbaseKeywords(cwd, keywords);
  if (context) sendAdditionalContext("PostToolUse", context);
}

function main() {
  const input = readInput();
  if (!input) return;

  if (input.hook_event_name === "SessionStart") {
    handleSessionStart(input);
  } else if (input.hook_event_name === "UserPromptSubmit") {
    handleUserPromptSubmit(input);
  } else if (input.hook_event_name === "PostToolUse") {
    handlePostToolUse(input);
  }
}

if (require.main === module) {
  try {
    main();
  } catch (err) {
    if (process.env.GRAPHBASE_DEBUG) {
      process.stderr.write(`Graphbase Codex hook error: ${String(err).slice(0, 200)}\n`);
    }
  }
}

module.exports = {
  GIT_MUTATION_RE,
  extractCommandQuery,
  extractPromptQuery,
  sendAdditionalContext,
};
