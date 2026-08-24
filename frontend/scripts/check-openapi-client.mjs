import { execFileSync } from "node:child_process";
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

async function listFiles(directory, prefix = "") {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries.toSorted((left, right) => left.name.localeCompare(right.name))) {
    const relativePath = join(prefix, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFiles(join(directory, entry.name), relativePath)));
    } else {
      files.push(relativePath);
    }
  }
  return files;
}

const projectRoot = resolve(import.meta.dirname, "..");
const committedOutput = resolve(projectRoot, "src/lib/api/generated");
const temporaryRoot = await mkdtemp(join(tmpdir(), "xuemian-openapi-"));
const temporaryOutput = join(temporaryRoot, "generated");

try {
  execFileSync(
    resolve(projectRoot, "node_modules/.bin/openapi-ts"),
    ["-i", resolve(projectRoot, "../openapi/openapi.json"), "-o", temporaryOutput],
    { stdio: "ignore" },
  );
  const [expectedFiles, actualFiles] = await Promise.all([
    listFiles(temporaryOutput),
    listFiles(committedOutput),
  ]);
  if (JSON.stringify(expectedFiles) !== JSON.stringify(actualFiles)) {
    throw new Error("OpenAPI 生成文件清单不一致，请运行 pnpm openapi:generate。 ");
  }
  for (const file of expectedFiles) {
    const [expected, actual] = await Promise.all([
      readFile(join(temporaryOutput, file), "utf8"),
      readFile(join(committedOutput, file), "utf8"),
    ]);
    if (expected !== actual) {
      throw new Error(`OpenAPI 生成文件已过期：${file}`);
    }
  }
} finally {
  await rm(temporaryRoot, { recursive: true, force: true });
}
