#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import semanticRelease from "semantic-release";

const VERSION_PATTERN = /^\d{1,3}\.\d{1,3}\.\d{1,3}(?:-[0-9A-Za-z.-]+)?$/;

export function validateVersion(version) {
    if (!VERSION_PATTERN.test(version)) {
        throw new Error(`Invalid release version: ${version}`);
    }
    return version;
}

export async function applyCandidateFiles(repoRoot, nextRelease) {
    const version = validateVersion(String(nextRelease.version || ""));
    const notes = String(nextRelease.notes || "").trim();
    if (!notes) {
        throw new Error("semantic-release returned empty release notes");
    }

    const versionPath = path.join(repoRoot, "VERSION");
    const changelogPath = path.join(repoRoot, "CHANGELOG.md");
    const currentChangelog = await fs.readFile(changelogPath, "utf8");
    const releaseHeading = new RegExp(`^#{1,2} \\[?${version.replaceAll(".", "\\.")}(?:\\]|\\b)`);
    if (releaseHeading.test(currentChangelog)) {
        throw new Error(`CHANGELOG.md already starts with release ${version}`);
    }

    await fs.writeFile(versionPath, `${version}\n`, "utf8");
    await fs.writeFile(changelogPath, `${notes}\n\n${currentChangelog.replace(/^\s+/, "")}`, "utf8");
}

function parseArguments(argv) {
    const options = {};
    for (let index = 0; index < argv.length; index += 2) {
        const key = argv[index];
        const value = argv[index + 1];
        if (!key?.startsWith("--") || value === undefined) {
            throw new Error(`Invalid argument list near ${key || "<end>"}`);
        }
        options[key.slice(2)] = value;
    }
    if (!options["repo-root"] || !options.output) {
        throw new Error("Usage: prepare-candidate.mjs --repo-root PATH --output PATH");
    }
    return options;
}

export async function prepareCandidate({ repoRoot, outputPath, semanticReleaseRunner = semanticRelease }) {
    const releaseBranch = process.env.RELEASE_BRANCH || "master";
    const result = await semanticReleaseRunner(
        {
            branches: [releaseBranch],
            tagFormat: "v${version}",
            plugins: ["@semantic-release/commit-analyzer", "@semantic-release/release-notes-generator"],
            dryRun: true,
            ci: false,
        },
        {
            cwd: repoRoot,
            env: process.env,
        },
    );

    const outputDirectory = path.dirname(outputPath);
    await fs.mkdir(outputDirectory, { recursive: true });
    if (!result) {
        const metadata = { release_created: false };
        await fs.writeFile(outputPath, `${JSON.stringify(metadata, null, 2)}\n`, "utf8");
        return metadata;
    }

    await applyCandidateFiles(repoRoot, result.nextRelease);
    const notesPath = path.join(outputDirectory, "release-notes.md");
    await fs.writeFile(notesPath, `${String(result.nextRelease.notes).trim()}\n`, "utf8");

    const metadata = {
        release_created: true,
        version: validateVersion(result.nextRelease.version),
        tag: `v${result.nextRelease.version}`,
        notes_path: notesPath,
    };
    await fs.writeFile(outputPath, `${JSON.stringify(metadata, null, 2)}\n`, "utf8");
    return metadata;
}

async function main() {
    const options = parseArguments(process.argv.slice(2));
    const repoRoot = path.resolve(options["repo-root"]);
    const outputPath = path.resolve(options.output);
    const metadata = await prepareCandidate({ repoRoot, outputPath });
    process.stdout.write(`${JSON.stringify(metadata)}\n`);
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
if (isMain) {
    main().catch((error) => {
        process.stderr.write(`${error.stack || error}\n`);
        process.exitCode = 1;
    });
}
