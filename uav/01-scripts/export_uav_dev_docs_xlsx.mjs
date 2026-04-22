import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..", "..");
const DOC_ROOT = path.join(ROOT, "uav", "20-dev-docs");
const OUT_ROOT = path.join(ROOT, "docs");

async function csvToWorkbook(csvPath, sheetName, outPath) {
  const csvText = await fs.readFile(csvPath, "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outPath);
}

await fs.mkdir(OUT_ROOT, { recursive: true });

await csvToWorkbook(
  path.join(DOC_ROOT, "02-interface-table.csv"),
  "接口总表",
  path.join(OUT_ROOT, "非凸α-接口总表.xlsx"),
);
await csvToWorkbook(
  path.join(DOC_ROOT, "03-feature-deployment-matrix.csv"),
  "功能部署矩阵",
  path.join(OUT_ROOT, "非凸α-功能部署矩阵.xlsx"),
);
await csvToWorkbook(
  path.join(DOC_ROOT, "07-material-gaps.csv"),
  "素材缺口表",
  path.join(OUT_ROOT, "非凸α-素材缺口表.xlsx"),
);

console.log("WROTE", path.join(OUT_ROOT, "非凸α-接口总表.xlsx"));
console.log("WROTE", path.join(OUT_ROOT, "非凸α-功能部署矩阵.xlsx"));
console.log("WROTE", path.join(OUT_ROOT, "非凸α-素材缺口表.xlsx"));
