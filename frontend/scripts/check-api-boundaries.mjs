import { readFile, readdir } from "node:fs/promises";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = dirname(fileURLToPath(new URL("../package.json", import.meta.url)));
const sourceRoot = join(projectRoot, "src");
const sourceExtensions = new Set([".ts", ".tsx"]);

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(
    entries.map(async (entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? sourceFiles(path) : [path];
    }),
  );
  return files.flat();
}

function canImportGenerated(relativePath) {
  return (
    relativePath.startsWith("lib/api/") ||
    /^features\/[^/]+\/api(?:\.test)?\.ts$/.test(relativePath)
  );
}

function violationsFor(relativePath, source) {
  const fileViolations = [];
  const importsGenerated = /["'](?:@\/lib\/api\/generated|\.{1,2}\/[^"']*lib\/api\/generated)/.test(
    source,
  );
  if (importsGenerated && !canImportGenerated(relativePath)) {
    fileViolations.push(`${relativePath}: 禁止直接导入 OpenAPI 生成目录，请通过 feature api.ts`);
  }
  if (/\bfetch\s*\(/.test(source) && !relativePath.startsWith("lib/api/")) {
    fileViolations.push(`${relativePath}: 禁止直接 fetch 业务接口，请通过 feature api.ts`);
  }
  return fileViolations;
}

const policyCases = [
  ["features/interview/api.ts", 'import { getInterview } from "@/lib/api/generated"', 0],
  ["features/interview/queries.ts", 'import { getInterview } from "@/lib/api/generated"', 1],
  ["features/interview/panel.tsx", 'fetch("/api/backend/interviews")', 1],
];
for (const [relativePath, source, expectedViolations] of policyCases) {
  if (violationsFor(relativePath, source).length !== expectedViolations) {
    throw new Error(`API 边界检查器自检失败：${relativePath}`);
  }
}

const violations = [];
for (const file of await sourceFiles(sourceRoot)) {
  if (!sourceExtensions.has(extname(file))) continue;
  const relativePath = relative(sourceRoot, file);
  if (relativePath.startsWith("lib/api/generated/")) continue;

  const source = await readFile(file, "utf8");
  violations.push(...violationsFor(relativePath, source));
}

if (violations.length > 0) {
  throw new Error(`API 边界检查失败：\n${violations.join("\n")}`);
}

console.log("API 边界检查通过");
