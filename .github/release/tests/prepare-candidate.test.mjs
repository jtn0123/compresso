import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { applyCandidateFiles, prepareCandidate, validateVersion } from "../prepare-candidate.mjs";

test("validateVersion accepts release versions and rejects unsafe values", () => {
    assert.equal(validateVersion("1.14.0"), "1.14.0");
    assert.equal(validateVersion("1.14.0-rc.1"), "1.14.0-rc.1");
    assert.throws(() => validateVersion("1.14.0 && echo unsafe"), /Invalid release version/);
});

test("applyCandidateFiles updates VERSION and prepends generated notes", async () => {
    const repoRoot = await fs.mkdtemp(path.join(os.tmpdir(), "compresso-release-"));
    await fs.writeFile(path.join(repoRoot, "VERSION"), "1.13.0\n");
    await fs.writeFile(path.join(repoRoot, "CHANGELOG.md"), "# 1.13.0\n\nOld notes\n");

    await applyCandidateFiles(repoRoot, {
        version: "1.13.1",
        notes: "# 1.13.1\n\nNew notes",
    });

    assert.equal(await fs.readFile(path.join(repoRoot, "VERSION"), "utf8"), "1.13.1\n");
    assert.equal(
        await fs.readFile(path.join(repoRoot, "CHANGELOG.md"), "utf8"),
        "# 1.13.1\n\nNew notes\n\n# 1.13.0\n\nOld notes\n",
    );
});

test("prepareCandidate records a no-release result without touching files", async () => {
    const repoRoot = await fs.mkdtemp(path.join(os.tmpdir(), "compresso-release-"));
    const outputPath = path.join(repoRoot, ".release", "candidate.json");
    const semanticReleaseRunner = async () => false;

    const metadata = await prepareCandidate({ repoRoot, outputPath, semanticReleaseRunner });

    assert.deepEqual(metadata, { release_created: false });
    assert.deepEqual(JSON.parse(await fs.readFile(outputPath, "utf8")), metadata);
});
