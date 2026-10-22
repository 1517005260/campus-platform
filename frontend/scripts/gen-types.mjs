// 从 contracts/openapi/*.json 生成 TypeScript 类型。后端改了接口并重新导出契约后运行 npm run gen:types。
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const out = fileURLToPath(new URL("../src/api/types/", import.meta.url));
mkdirSync(out, { recursive: true });

for (const svc of ["common", "m1-seat", "m2-room", "m3-repair"]) {
  const spec = JSON.parse(readFileSync(`${root}contracts/openapi/${svc}.json`, "utf8"));
  const ast = await openapiTS(spec, { alphabetize: true });
  writeFileSync(
    `${out}${svc}.d.ts`,
    `// 由 scripts/gen-types.mjs 从 contracts/openapi/${svc}.json 生成，不要手改。\n${astToString(ast)}`,
  );
  console.log(`生成 src/api/types/${svc}.d.ts`);
}
