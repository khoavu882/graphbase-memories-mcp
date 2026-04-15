/**
 * graphbase-hook.js — Claude Code PreToolUse / PostToolUse hook dispatcher.
 *
 * Pure Node.js, no npm dependencies, no bundler required.
 * Built-ins only: fs, path, child_process, process.
 *
 * Protocol:
 *   - Reads JSON from stdin (Claude Code injects hook event).
 *   - On PreToolUse(Read|Edit|Write|Grep|Glob): surfaces related memories and writes
 *     additionalContext to stdout as a single JSON line.
 *   - On PostToolUse(Bash) with a git mutation: checks for stale entities and writes
 *     an advisory to stdout as a single JSON line.
 *   - All errors are swallowed. Hook MUST always exit 0.
 *
 * Output channel note:
 *   `graphbase surface` writes its human-readable context to STDERR (not stdout),
 *   keeping stdout available for the hook's own JSON protocol line. The hook reads
 *   result.stderr to forward this context as additionalContext.
 *
 * Security constraints (non-negotiable):
 *   - shell: false on every spawnSync call.
 *   - User-controlled query always placed after '--' in args array.
 *   - cwd validated as absolute path before use.
 *   - No string concatenation of user input into any command.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

// ── Input parsing ────────────────────────────────────────────────────────────

function readInput() {
  try {
    const raw = fs.readFileSync(0, "utf-8");
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

// ── Binary resolution ────────────────────────────────────────────────────────

// Module-level cache — the process is short-lived so a null sentinel is safe.
// Avoids spawning `which` twice when both PreToolUse and PostToolUse fire.
let _cachedBin = undefined;

/**
 * Resolve the graphbase binary path (cached after first call).
 * Uses `which` / `where` with a 1000ms cap (budget constraint).
 * No uvx fallback in PreToolUse — cold-start would exceed Claude Code's 10s limit.
 * Returns the binary name string, or null if not found.
 */
function resolveGraphbaseBin() {
  if (_cachedBin !== undefined) return _cachedBin;

  const checker = process.platform === "win32" ? "where" : "which";
  const cmd = process.platform === "win32" ? "graphbase.cmd" : "graphbase";

  const check = spawnSync(checker, [cmd], {
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 1000,
    encoding: "utf-8",
    shell: false,
  });

  _cachedBin = check.status === 0 ? cmd : null;
  return _cachedBin;
}

// ── Query extraction ─────────────────────────────────────────────────────────

/**
 * Extract a search query from the tool name and input.
 * Returns null if no usable query can be extracted (< 3 chars, no cwd, etc.).
 */
function extractQuery(toolName, toolInput) {
  if (!toolInput) return null;

  switch (toolName) {
    case "Read":
    case "Edit":
    case "Write": {
      const filePath = toolInput.file_path || "";
      if (!filePath) return null;
      const base = path.basename(filePath, path.extname(filePath));
      return base.length >= 3 ? base : null;
    }
    case "Grep": {
      const pattern = toolInput.pattern || "";
      return pattern.length >= 3 ? pattern : null;
    }
    case "Glob": {
      const glob = toolInput.pattern || "";
      // Extract the first meaningful word segment (e.g. "HygieneEngine" from "**/HygieneEngine*.py")
      const match = glob.match(/[*/\\]([a-zA-Z][a-zA-Z0-9_]{2,})/);
      if (match) return match[1];
      // Fallback: strip glob metacharacters AND path separators, use if >= 3 alphanum chars
      const clean = glob.replace(/[*?[\]{}/. ]/g, "").trim();
      return clean.length >= 3 ? clean : null;
    }
    default:
      return null;
  }
}

// ── Hook response ────────────────────────────────────────────────────────────

/**
 * Write the hook response to stdout as exactly one JSON line.
 * This is the ONLY allowed stdout write in the entire hook.
 */
function sendHookResponse(eventName, context) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: eventName,
        additionalContext: context,
      },
    }) + "\n"
  );
}

// ── PreToolUse handler ───────────────────────────────────────────────────────

function handlePreToolUse(input) {
  // cwd must be an absolute path — relative paths could be attacker-controlled
  const cwd = input.tool_input?.cwd || input.cwd || "";
  if (!path.isAbsolute(cwd)) return;

  const query = extractQuery(input.tool_name, input.tool_input);
  if (!query || query.length < 3) return;

  const bin = resolveGraphbaseBin();
  if (!bin) return; // silent exit — binary not installed

  // '--' prevents query values starting with '-' from being parsed as flags
  const result = spawnSync(bin, ["surface", "--", query], {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 6000,
    encoding: "utf-8",
    shell: false, // always false — security requirement
  });

  // Only read stderr on clean exit — non-zero may carry Python tracebacks
  if (result.status === 0 && result.stderr && result.stderr.trim()) {
    sendHookResponse("PreToolUse", result.stderr.trim());
  }
}

// ── PostToolUse handler ──────────────────────────────────────────────────────

/**
 * Regex for git mutations that should trigger a staleness check.
 * Matches: git commit, git merge, git rebase, git cherry-pick, git pull
 *
 * `git push` is intentionally excluded — it does not mutate local history,
 * so there are no new local commits to inspect for stale entity context.
 */
const GIT_MUTATION_RE = /\bgit\s+(commit|merge|rebase|cherry-pick|pull)(\s|$)/;

function handlePostToolUse(input) {
  // Stage 1: only intercept Bash tool calls
  if (input.tool_name !== "Bash") return;

  // Stage 2: command must be a git mutation
  const command = input.tool_input?.command || "";
  if (!GIT_MUTATION_RE.test(command)) return;

  // Stage 3: tool must have succeeded (exit_code 0 or absent = success)
  const exitCode = input.tool_response?.exit_code;
  if (exitCode !== undefined && exitCode !== 0) return;

  // Stage 4: cwd must be absolute
  const cwd = input.tool_input?.cwd || input.cwd || "";
  if (!path.isAbsolute(cwd)) return;

  // Get changed file names from HEAD (graceful on first commit — no HEAD~1)
  const diffResult = spawnSync(
    "git",
    ["diff", "--name-only", "HEAD~1", "HEAD"],
    {
      cwd,
      stdio: ["pipe", "pipe", "pipe"],
      timeout: 3000,
      encoding: "utf-8",
      shell: false,
    }
  );

  if (diffResult.status !== 0 || !diffResult.stdout.trim()) return;

  // Extract base names (no extension) as keyword candidates
  const changedFiles = diffResult.stdout.trim().split("\n");
  const keywords = [
    ...new Set(
      changedFiles
        .map((f) => path.basename(f, path.extname(f)))
        .filter((k) => k.length >= 3)
    ),
  ].slice(0, 10); // cap: avoid massive queries

  if (keywords.length === 0) return;

  const bin = resolveGraphbaseBin();
  if (!bin) return;

  const result = spawnSync(bin, ["surface", "--keywords", keywords.join(",")], {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 5000,
    encoding: "utf-8",
    shell: false,
  });

  if (result.status === 0 && result.stderr && result.stderr.trim()) {
    sendHookResponse("PostToolUse", result.stderr.trim());
  }
}

// ── Dispatch ─────────────────────────────────────────────────────────────────

function main() {
  const input = readInput();
  if (!input) return; // malformed JSON — silent exit

  const handlers = {
    PreToolUse: handlePreToolUse,
    PostToolUse: handlePostToolUse,
  };

  const handler = handlers[input.hook_event_name];
  if (handler) handler(input);
  // Unrecognized event → exit 0, no output (required behavior)
}

// Only execute when run directly (not when require()'d for testing)
if (require.main === module) {
  try {
    main();
  } catch (err) {
    // Always exit 0 — hook must never crash Claude Code
    if (process.env.GRAPHBASE_DEBUG) {
      process.stderr.write(
        "Graphbase hook error: " + String(err).slice(0, 200) + "\n"
      );
    }
  }
}

// ── Exports (pure functions only — for unit testing without subprocess mocking) ──
if (typeof module !== "undefined") {
  module.exports = { extractQuery, GIT_MUTATION_RE };
}
