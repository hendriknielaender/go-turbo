#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const repo = join(dirname(fileURLToPath(import.meta.url)), "..");
const packagePath = join(repo, "package.json");
const lockPath = join(repo, "package-lock.json");
const manifestPaths = [
  join(repo, ".codex-plugin", "plugin.json"),
  join(repo, ".claude-plugin", "plugin.json"),
];
const checkOnly = process.argv.includes("--check");

const { version } = JSON.parse(readFileSync(packagePath, "utf8"));
let drift = false;

for (const manifestPath of manifestPaths) {
  const source = readFileSync(manifestPath, "utf8");
  const manifest = JSON.parse(source);
  const displayPath = relative(repo, manifestPath);

  if (manifest.version === version) {
    console.log(`${displayPath} version is ${version}`);
    continue;
  }

  drift = true;
  if (checkOnly) {
    console.error(
      `${displayPath} version is ${manifest.version}; package.json is ${version}`,
    );
    continue;
  }

  const updated = source.replace(
    /("version"\s*:\s*")[^"]*(")/,
    `$1${version}$2`,
  );
  if (JSON.parse(updated).version !== version) {
    throw new Error(`Could not update version in ${displayPath}`);
  }
  writeFileSync(manifestPath, updated);
  console.log(`${displayPath} version ${manifest.version} -> ${version}`);
}

if (checkOnly && drift) {
  process.exit(1);
}

const lockSource = readFileSync(lockPath, "utf8");
const lock = JSON.parse(lockSource);
const rootLockPackage = lock.packages?.[""];
const lockMatches =
  lock.version === version && rootLockPackage?.version === version;

if (lockMatches) {
  console.log(`package-lock.json version is ${version}`);
} else if (checkOnly) {
  console.error(
    `package-lock.json versions are ${lock.version} and ${rootLockPackage?.version}; package.json is ${version}`,
  );
  process.exit(1);
} else {
  if (!rootLockPackage || typeof rootLockPackage !== "object") {
    throw new Error("package-lock.json has no root package entry");
  }
  lock.version = version;
  rootLockPackage.version = version;
  writeFileSync(lockPath, `${JSON.stringify(lock, null, 2)}\n`);
  console.log(`package-lock.json version -> ${version}`);
}
